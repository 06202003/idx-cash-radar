"""Pengumpul orderbook untuk saham yang sedang di watchlist otomatis (lihat watchlist.py).

TAHAP 1 = KUMPULKAN DATA SAJA, tanpa alert. Belum ada data historis orderbook sama
sekali, jadi belum bisa tahu sinyal mana (tembok bid ditarik, offer dimakan, imbalance)
yang benar-benar mendahului gerak harga. Setelah 1-2 minggu data terkumpul, baru diuji.

Endpoint (ditemukan & dicek 2026-11-21, HTTP 200):
    ORDERBOOK_PATH=/company-price-feed/v2/orderbook/companies/{code}
Respons: data.bid / data.offer = [{"price","que_num","volume"}], volume dalam LEMBAR
(disimpan sebagai lot = lembar/100). Kosongkan ORDERBOOK_PATH = pengumpul mati.

Penyimpanan (disk VPS sempit -> ringkas & terkompresi):
- data/orderbook/YYYY-MM-DD.jsonl.gz : 1 baris per snapshot yang berhasil diurai,
  {"ts","code","bids":[[harga,lot,antrean],...],"offers":[...],"last","fnet","dvol"} (maks ORDERBOOK_LEVELS level)
- data/orderbook/raw-sample-YYYY-MM-DD.jsonl : beberapa respons MENTAH per hari, buat
  menyesuaikan parse_levels() kalau format respons belum dikenali / berubah.
- batas ukuran per hari ORDERBOOK_MAX_MB_PER_DAY; lewat batas -> berhenti simpan hari itu.

Token: pakai sesi polling running trade yang sedang aktif. Pengumpul TIDAK pernah
me-refresh token sendiri (biar nggak rebutan refresh dengan loop polling utama);
kalau dapat 401, cukup lewati putaran itu -- loop utama yang akan refresh.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("orderbook")

RAW_SAMPLES_PER_DAY = 5
MAX_CONSECUTIVE_ERRORS = 20  # lewat ini -> pengumpul berhenti sampai besok + kabar 1x

# nama field yang umum dipakai API bursa/broker -- dicoba berurutan
BID_KEYS = ("bid", "bids", "buy", "buys")
OFFER_KEYS = ("offer", "offers", "ask", "asks", "sell", "sells")
PRICE_KEYS = ("price", "p", "harga")
LOT_KEYS = ("lot", "volume", "vol", "qty", "quantity", "v")


def _num(x) -> float | None:
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):  # bentuk {"raw": 123, "formatted": "123"}
        return _num(x.get("raw", x.get("value")))
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _level(item) -> tuple[float, float] | None:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        p, v = _num(item[0]), _num(item[1])
    elif isinstance(item, dict):
        low = {k.lower(): v for k, v in item.items()}
        p = next((_num(low[k]) for k in PRICE_KEYS if k in low), None)
        v = next((_num(low[k]) for k in LOT_KEYS if k in low), None)
    else:
        return None
    if p is None or v is None or p <= 0 or v < 0:
        return None
    return p, v


def _levels(seq) -> list[tuple[float, float]] | None:
    if not isinstance(seq, list) or not seq:
        return None
    out = [lv for lv in (_level(x) for x in seq) if lv]
    return out if len(out) >= len(seq) / 2 else None  # mayoritas harus kebaca


def _find_side(obj, keys: tuple[str, ...], depth: int = 0):
    """Cari list level di bawah salah satu nama kunci, menelusuri dict bersarang."""
    if depth > 5 or not isinstance(obj, dict):
        return None
    low = {k.lower(): v for k, v in obj.items()}
    for k in keys:
        if k in low:
            lv = _levels(low[k])
            if lv:
                return lv
    for v in obj.values():
        found = _find_side(v, keys, depth + 1)
        if found:
            return found
    return None


def _stockbit_side(seq, max_levels: int, reverse: bool):
    """Format Stockbit: {"price":"5575","que_num":"123","volume":"3064100"} -- volume = LEMBAR."""
    out = []
    for it in seq or []:
        if not isinstance(it, dict):
            return None
        p, v, q = _num(it.get("price")), _num(it.get("volume")), _num(it.get("que_num"))
        if p is None or v is None or p <= 0:
            continue
        out.append((p, v / 100, int(q or 0)))  # -> (harga, lot, jumlah antrean)
    out.sort(key=lambda x: -x[0] if reverse else x[0])
    return out[:max_levels]


def parse_stockbit(payload, max_levels: int = 10) -> dict | None:
    """Respons /company-price-feed/v2/orderbook/companies/{code} -> ringkas. None kalau bukan format ini."""
    d = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(d, dict) or not isinstance(d.get("bid"), list) or not isinstance(d.get("offer"), list):
        return None
    bids = _stockbit_side(d["bid"], max_levels, reverse=True)
    offers = _stockbit_side(d["offer"], max_levels, reverse=False)
    if bids is None or offers is None or (not bids and not offers):
        return None
    return {"bids": bids, "offers": offers, "last": _num(d.get("lastprice")),
            "fnet": _num(d.get("fnet")), "dvol": _num(d.get("volume"))}


def parse_levels(payload, max_levels: int = 10):
    """Return (bids, offers) -- masing-masing list[(harga, lot, ...)], bid turun & offer naik.
    None kalau format belum dikenali (nanti dicocokkan pakai raw-sample)."""
    sb = parse_stockbit(payload, max_levels)
    if sb is not None:
        return sb["bids"], sb["offers"]
    bids = _find_side(payload, BID_KEYS)
    offers = _find_side(payload, OFFER_KEYS)
    if not bids or not offers:
        return None
    bids = sorted(bids, key=lambda x: -x[0])[:max_levels]
    offers = sorted(offers, key=lambda x: x[0])[:max_levels]
    return bids, offers


def summarize(bids, offers, depth: int = 5) -> dict:
    """Ringkasan sederhana buat /ob dan evaluasi nanti."""
    b = sum(lv[1] for lv in bids[:depth])
    o = sum(lv[1] for lv in offers[:depth])
    spread = (offers[0][0] - bids[0][0]) if bids and offers else None
    return {"bid_lot": b, "offer_lot": o, "bid_share": b / (b + o) if b + o else None, "spread": spread}


class OrderbookCollector:
    def __init__(self, data_dir: str, path_template: str, interval_sec: float = 10,
                 levels: int = 10, max_mb_per_day: float = 50):
        self.dir = os.path.join(data_dir, "orderbook")
        self.path_template = path_template.strip()
        self.interval_sec = max(interval_sec, 3.0)
        self.levels = levels
        self.max_bytes = max_mb_per_day * 1024 * 1024
        self.day = ""
        self.raw_saved = 0
        self.errors = 0
        self.stopped_day = ""  # hari pengumpul dihentikan karena error/batas
        self.stats = {"ok": 0, "unparsed": 0, "error": 0}

    @property
    def enabled(self) -> bool:
        return bool(self.path_template) and "{code}" in self.path_template

    def status_line(self) -> str:
        if not self.enabled:
            return "mati (ORDERBOOK_PATH belum diisi)"
        if self.stopped_day == datetime.now(WIB).strftime("%Y-%m-%d"):
            return f"berhenti hari ini ({self.stats})"
        return f"kumpul data tiap {self.interval_sec:g} dtk · hari ini {self.stats}"

    def _roll_day(self) -> str:
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self.day, self.raw_saved, self.errors = today, 0, 0
            self.stats = {"ok": 0, "unparsed": 0, "error": 0}
        return today

    def fetch(self, auth, code: str):
        """Ambil 1 orderbook. Pakai token sesi yang ada, TANPA refresh (lihat docstring modul)."""
        resp = auth._get(self.path_template.format(code=code), auth.token.access_token)
        if resp.status_code == 401:
            return None, 401
        resp.raise_for_status()
        return resp.json(), 200

    def _save(self, today: str, code: str, ts: float, payload) -> str:
        os.makedirs(self.dir, exist_ok=True)
        parsed = parse_levels(payload, self.levels)
        if parsed is None:
            self.stats["unparsed"] += 1
            if self.raw_saved < RAW_SAMPLES_PER_DAY:
                self.raw_saved += 1
                with open(os.path.join(self.dir, f"raw-sample-{today}.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": round(ts), "code": code, "payload": payload}, ensure_ascii=False)[:200_000] + "\n")
            return "unparsed"
        path = os.path.join(self.dir, f"{today}.jsonl.gz")
        if os.path.exists(path) and os.path.getsize(path) >= self.max_bytes:
            return "full"
        bids, offers = parsed
        rec = {"ts": round(ts, 1), "code": code, "bids": bids, "offers": offers}
        sb = parse_stockbit(payload, self.levels)
        if sb is not None:  # konteks murah: harga terakhir, net asing & volume harian (lembar)
            rec.update({k: sb[k] for k in ("last", "fnet", "dvol") if sb[k] is not None})
        with gzip.open(path, "at", encoding="utf-8") as f:  # member gzip baru tiap append: tetap valid
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        if self.raw_saved < 1:  # simpan 1 contoh mentah tiap hari buat jaga-jaga format berubah
            self.raw_saved += 1
            with open(os.path.join(self.dir, f"raw-sample-{today}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": round(ts), "code": code, "payload": payload}, ensure_ascii=False)[:200_000] + "\n")
        self.stats["ok"] += 1
        return "ok"

    async def run_forever(self, get_live_auth, get_codes, notify, on_snapshot=None) -> None:
        """get_live_auth() -> sesi polling aktif atau None; get_codes() -> saham yang dipantau."""
        if not self.enabled:
            log.info("Pengumpul orderbook mati: ORDERBOOK_PATH belum diisi.")
            return
        log.info("Pengumpul orderbook aktif (tiap %.0f dtk per saham pantauan).", self.interval_sec)
        while True:
            await asyncio.sleep(self.interval_sec * random.uniform(0.85, 1.15))
            today = self._roll_day()
            if self.stopped_day == today:
                continue
            auth = get_live_auth()
            codes = list(get_codes())
            if auth is None or not codes:
                continue
            gap = self.interval_sec / (len(codes) + 1)  # sebar request, jangan sekaligus
            for code in codes:
                ts = time.time()
                try:
                    payload, status = await asyncio.to_thread(self.fetch, auth, code)
                    if status == 401:
                        break  # tunggu loop utama refresh token
                    if on_snapshot is not None:
                        try:
                            on_snapshot(code, ts, payload)
                        except Exception as e:  # noqa: BLE001 -- pendeteksi rusak jangan matikan pengumpul
                            log.warning("Pendeteksi pola %s gagal: %s", code, e)
                    result = await asyncio.to_thread(self._save, today, code, ts, payload)
                    self.errors = 0
                    if result == "full":
                        self.stopped_day = today
                        notify(f"ℹ️ Orderbook: batas simpan {self.max_bytes / 1048576:.0f} MB hari ini tercapai, "
                               "pengumpulan berhenti sampai besok.")
                        break
                except Exception as e:  # noqa: BLE001
                    self.stats["error"] += 1
                    self.errors += 1
                    log.warning("Orderbook %s gagal: %s", code, e)
                    if self.errors >= MAX_CONSECUTIVE_ERRORS:
                        self.stopped_day = today
                        notify(f"⚠️ Orderbook gagal {self.errors}x berturut-turut (terakhir: {e}). "
                               "Pengumpulan dihentikan sampai besok — cek ORDERBOOK_PATH.")
                        break
                await asyncio.sleep(gap)
