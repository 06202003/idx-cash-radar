"""Peringatan risiko struktural per saham: rentetan ARA/ARB kemarin & biaya tick (titik impas).

Sumber angka: research/2026-11-22-biaya-tick-dan-ara-arb.md (data harian 442 saham, s.d.
2026-11-20; saham likuid >= Rp1 M/hari). Semua dari data LAMA — dicatat sebagai ide I1-I3 di
HIPOTESIS.md, belum lolos forward test.

Hanya membaca cache harian di disk (data/daily/KODE.json) — TIDAK ada request jaringan, jadi
aman dipanggil dari loop polling. Kalau bar kemarin belum ada di cache, peringatan kunci dilewati.

Hari terkunci = open = high = low = close dengan gerak >= 5% (dideteksi dari data, karena batas
auto-reject BEI berubah-ubah).
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime
from zoneinfo import ZoneInfo

from papertrade import tick

WIB = ZoneInfo("Asia/Jakarta")
FEES = 0.004  # 0,15% beli + 0,25% jual
NOT_SCALPABLE = 0.5  # titik impas >= separuh gerak harian = tidak layak scalping

_cache: dict[tuple, dict] = {}


def _bars(data_dir: str, sym: str, today: str) -> list:
    try:
        with open(os.path.join(data_dir, "daily", f"{sym}.json"), encoding="utf-8") as f:
            return [b for b in json.load(f) if b[0] < today]  # hanya bar yang sudah jadi
    except (OSError, json.JSONDecodeError):
        return []


def _lock(b: list, i: int) -> int:
    o, h, l, c = b[i][1:5]
    p = b[i - 1][4]
    if p <= 0 or not (o == h == l == c):
        return 0
    r = c / p - 1
    return 1 if r >= 0.05 else -1 if r <= -0.05 else 0


def assess(data_dir: str, sym: str, price: float) -> dict:
    """{'lock': 'ARA'|'ARB'|None, 'lock_days': n, 'be': titik impas, 'be_ratio': impas/range, ...}"""
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    try:  # file harian diperbarui (mis. oleh fetch teknikal) -> hitung ulang
        mtime = os.path.getmtime(os.path.join(data_dir, "daily", f"{sym}.json"))
    except OSError:
        mtime = 0
    key = (sym, today, mtime)
    base = _cache.get(key)
    if base is None:
        b = _bars(data_dir, sym, today)
        base = {"lock": None, "lock_days": 0, "range": None, "run20": None, "last_day": b[-1][0] if b else None}
        if len(b) >= 2:
            last = _lock(b, len(b) - 1)
            if last:
                n, i = 0, len(b) - 1
                while i >= 1 and _lock(b, i) == last:
                    n += 1
                    i -= 1
                base["lock"], base["lock_days"] = ("ARA" if last > 0 else "ARB"), n
        recent = b[-60:]
        rng = [(x[2] - x[3]) / x[4] for x in recent if x[4] > 0]
        if len(rng) >= 20:
            base["range"] = statistics.median(rng)
        if len(b) >= 21 and b[-21][4] > 0:
            base["run20"] = b[-1][4] / b[-21][4] - 1
        _cache[key] = base
    out = dict(base)
    if price > 0:
        out["be"] = tick(price) / price + FEES
        out["be_ratio"] = out["be"] / base["range"] if base["range"] else None
    return out


def lock_line(r: dict) -> str:
    if r.get("lock") == "ARA":
        n = r["lock_days"]
        return (f"⛔ <b>SESUDAH ARA</b> — terkunci ARA {n} hari s.d. kemarin. Historis beli besoknya "
                f"{'−4%' if n >= 2 else '−2%'} di hari itu, untung cuma 7–13% (jangan dikejar)")
    if r.get("lock") == "ARB":
        n = r["lock_days"]
        loss = {1: "−12,9%", 2: "−25%"}.get(n, "−31%")
        return (f"🔻 <b>RENTETAN ARB</b> — terkunci ARB {n} hari s.d. kemarin. Historis 45% terkunci lagi; "
                f"rugi s.d. bisa jual median {loss} dari sebelum ARB")
    return ""


def cost_line(r: dict, always: bool = False) -> str:
    be, ratio, rng = r.get("be"), r.get("be_ratio"), r.get("range")
    if be is None:
        return ""
    bad = ratio is not None and ratio >= NOT_SCALPABLE
    if not always and not bad:
        return ""
    txt = f"impas scalping {be * 100:.2f}% (1 tick + fee)".replace(".", ",")
    if rng:
        txt += f" vs gerak harian {rng * 100:.1f}%".replace(".", ",")
    if bad:
        return f"💸 <b>TIDAK LAYAK SCALPING</b> — {txt}"
    return f"💸 {txt}"


# ---------- gap pembukaan hari ini (research/2026-11-22-gap-pembukaan.md, ide I4) ----------
GAP_BIG = 0.05
GAP_PATH = "/company-price-feed/v2/orderbook/companies/{code}"  # field open & previous
_gap: dict[tuple[str, str], float | None] = {}
_gap_quota = {"day": "", "n": 0}
GAP_MAX_REQ = 400  # per hari


def fetch_gap(auth, sym: str) -> float | None:
    """open hari ini / close kemarin − 1, dari endpoint orderbook (sekali per saham per hari).
    Blocking (panggil lewat thread). None kalau belum buka / gagal / kuota habis."""
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    key = (sym, today)
    if key in _gap:
        return _gap[key]
    if now.strftime("%H:%M") < "09:00" or auth is None:
        return None  # open resmi baru ada setelah pre-opening
    if _gap_quota["day"] != today:
        _gap_quota.update(day=today, n=0)
    if _gap_quota["n"] >= GAP_MAX_REQ:
        return None
    _gap_quota["n"] += 1
    try:
        r = auth._get(GAP_PATH.format(code=sym), auth.token.access_token)
        d = (r.json().get("data") or {}) if r.status_code == 200 else {}
        o, p = float(d.get("open") or 0), float(d.get("previous") or 0)
        gap = (o / p - 1) if o > 0 and p > 0 else None
    except Exception:  # noqa: BLE001
        gap = None
    if gap is not None:
        _gap[key] = gap
    return gap


def gap_cached(sym: str) -> float | None:
    return _gap.get((sym, datetime.now(WIB).strftime("%Y-%m-%d")))


def gap_line(gap: float | None) -> str:
    if gap is None or gap < GAP_BIG:
        return ""
    return (f"⚠️ <b>GAP NAIK BESAR</b> — buka +{gap * 100:.1f}% dari close kemarin. Historis median "
            f"−2% dari open s.d. close, cuma 34% naik (jangan beli di open; pemegang: jual di open "
            f"historis lebih baik)").replace(".", ",", 1)
