"""Broksum ADAPTIF: kalau kesimpulan 10 hari belum kuat, tarik data lebih panjang.

Dijalankan otomatis sesudah rekap sore, untuk saham rekap (>=3 alert) + saham yang
masuk watchlist otomatis hari itu. Lima pemicu (A-E); pemicu yang aktif & hasilnya
dicatat ke data/broksum-adaptive-YYYY-MM.jsonl supaya nanti bisa diuji mana yang berguna.

  A  Data kurang      cache 10 hari < 8 hari (mis. saham di luar universe)  -> query rentang 10 hari
  B  Konsentrasi tipis konsentrasi 10 hari 35-55% (dekat ambang 45%)        -> konsentrasi 20 hari
  C  Penampung buang  penampung utama 10 hari net jual >= 20% barangnya
                      dalam 3 hari terakhir                                  -> 30 hari: penampung lama ikut buang?
  D  Harga sudah lari |gerak 10 hari| >= 10%                                 -> 20 hari SEBELUM jendela: kapan mulai?
  E  Sinyal bentrok   running trade beli dominan / masuk watchlist, tapi
                      broksum distribusi                                     -> 20 hari: penampung masih beli?

Fakta data (dicek 2026-11-22, BBCA/BUMI/PWON):
- Query rentang tanggal: NET PER BROKER = persis jumlah per hari (top-5 identik).
- Tapi field total nilai di query rentang TIDAK = jumlah per hari (52-82%), dan nilai
  Yahoo juga tidak bisa jadi pengganti (rasio 5-88% per saham). Jadi PERSENTASE
  konsentrasi (B) hanya dihitung dari cache per hari. A/C/D/E cukup pakai net per broker,
  sumbernya cache per hari kalau lengkap, kalau tidak query rentang (1 request).

Kalibrasi C (cache 216 saham, 427 saham-hari): "top-3 pembeli berganti" ternyata normal
(37-85% saham, tergantung definisi) -> dibuang. "Penampung utama buang >=20% dalam 3 hari"
cuma 4% -> itu yang dipakai. "Membuang" = jual 10 hari >= 25% akumulasi sebelumnya.

Semua pemicu ini HIPOTESIS, belum diuji. Batas request rentang per hari: MAX_RANGE_REQ.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import broksum

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("broksum_adaptive")

BORDER_LO, BORDER_HI = 0.35, 0.55
MOVE_BIG = 0.10
MIN_COVER = 0.8  # porsi hari yang harus ada di cache biar jendela dihitung dari cache
MAIN_SELL_FRAC = 0.2  # C: penampung utama jual >= sekian dari akumulasi 10 harinya, dalam 3 hari
DUMP_FRAC = 0.25  # "membuang" = jual 10 hari >= sekian dari akumulasi sebelumnya
MAX_FILL_DAYS = 12  # B: maksimal hari bolong yang ditambal per hari (per saham)


def _range_path(frm: str, to: str) -> str:
    return (f"/marketdetectors/{{sym}}?from={frm}&to={to}&transaction_type=TRANSACTION_TYPE_NET"
            "&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25")


def _top(net: dict, n: int = 3, buy: bool = True) -> list[tuple[str, float]]:
    items = sorted(net.items(), key=lambda kv: -kv[1] if buy else kv[1])[:n]
    return [(c, v) for c, v in items if (v > 0 if buy else v < 0)]


def _rp(v: float) -> str:
    return ("−" if v < 0 else "") + broksum._rp(abs(v))


class AdaptiveBroksum:
    def __init__(self, data_dir: str, store: broksum.BroksumStore, bars, is_trading_day,
                 max_range_req: int = 60):
        self.data_dir = data_dir
        self.store = store
        self.bars = bars  # technical.DailyBars
        self.is_trading_day = is_trading_day
        self.max_range_req = max_range_req
        self.range_dir = os.path.join(data_dir, "broksum_range")
        os.makedirs(self.range_dir, exist_ok=True)
        self.req_day = ""
        self.req_count = 0
        self.context_fn = None  # -> dict kondisi IHSG, diisi monitor.py

    # ---------- sumber data ----------
    def _days(self, end: str, n: int) -> list[str]:
        return broksum.prior_trading_days(end, n - 1, self.is_trading_day) + [end]

    def _cache_net(self, sym: str, days: list[str]):
        """Net per broker dijumlah dari cache per hari. None kalau cakupan < MIN_COVER."""
        rows = [r for r in (self.store.get(sym, d) for d in days) if r]
        if len(rows) < MIN_COVER * len(days):
            return None
        net: dict[str, float] = {}
        for r in rows:
            for c, v in r["net"].items():
                net[c] = net.get(c, 0.0) + v
        return net

    def _range_net(self, auth, sym: str, frm: str, to: str):
        """Net per broker dari 1 query rentang (di-cache di disk). None kalau kuota habis / gagal."""
        path = os.path.join(self.range_dir, f"{to}.json")
        try:
            with open(path, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            cache = {}
        key = f"{sym}|{frm}|{to}"
        if key in cache:
            return cache[key]
        if not self._take_quota(1):
            log.info("Kuota request tambahan hari ini habis (%d), %s dilewati.", self.max_range_req, sym)
            return None
        try:
            resp = auth._authed_get(_range_path(frm, to).format(sym=sym))
            resp.raise_for_status()
            row = broksum.parse(resp.json())
        except Exception as e:  # noqa: BLE001
            log.warning("Query rentang %s %s..%s gagal: %s", sym, frm, to, e)
            return None
        finally:
            time.sleep(random.uniform(1.0, 1.8))
        net = row["net"] if row else {}
        cache[key] = net
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, path)
        return net

    def _take_quota(self, n: int) -> bool:
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        if today != self.req_day:
            self.req_day, self.req_count = today, 0
        if self.req_count + n > self.max_range_req:
            return False
        self.req_count += n
        return True

    def _net(self, auth, sym: str, days: list[str]):
        """(net, sumber). Cache per hari dulu (0 request), kalau bolong -> query rentang."""
        net = self._cache_net(sym, days)
        if net is not None:
            return net, "cache"
        net = self._range_net(auth, sym, days[0], days[-1])
        return net, ("rentang" if net is not None else None)

    def _move(self, sym: str, days: list[str]):
        """Gerak harga close (Yahoo) dari hari sebelum jendela sampai akhir jendela."""
        try:
            b = {x[0]: x[4] for x in self.bars.get(sym)}
        except Exception:  # noqa: BLE001
            return None
        prev = broksum.prior_trading_days(days[0], 1, self.is_trading_day)[0]
        if prev in b and days[-1] in b and b[prev] > 0:
            return b[days[-1]] / b[prev] - 1
        return None

    def _close(self, sym: str, day: str):
        try:
            return {x[0]: x[4] for x in self.bars.get(sym)}.get(day)
        except Exception:  # noqa: BLE001
            return None

    # ---------- penilaian 1 saham ----------
    def evaluate(self, auth, sym: str, day: str, n_buy: int = 0, n_sell: int = 0,
                 in_watch: bool = False) -> dict:
        d10 = self._days(day, 10)
        rows10 = [r for r in (self.store.get(sym, d) for d in d10) if r]
        res = {"sym": sym, "day": day, "triggers": [], "findings": [], "close": self._close(sym, day),
               "n_buy": n_buy, "n_sell": n_sell, "in_watch": in_watch, "n_cache10": len(rows10)}

        # --- A: data 10 hari kurang -> query rentang 10 hari
        if len(rows10) < broksum.CONC_MIN_DAYS:
            res["triggers"].append("A")
            net10 = self._range_net(auth, sym, d10[0], d10[-1])
            if net10 is None:
                res["findings"].append("A: data 10 hari tidak bisa ditarik (kuota/gagal)")
                return res
            buyers, sellers = _top(net10), _top(net10, buy=False)
            res["top3_10"] = [c for c, _ in buyers]
            res["findings"].append(
                "A: penampung 10 hari " + (", ".join(f"{c} {_rp(v)}" for c, v in buyers) or "-")
                + " · penjual " + (", ".join(f"{c} {_rp(-v)}" for c, v in sellers) or "-")
                + " <i>(query rentang; % konsentrasi tidak dihitung)</i>")
            conc10 = None
        else:
            conc = broksum.concentration(self.store, sym, d10)
            conc10 = conc["conc"] if conc else None
            net10 = self._cache_net(sym, d10) or {}
            res["conc10"] = conc10
            res["top3_10"] = [c for c, _ in _top(net10)]

        top3 = res.get("top3_10") or []

        # --- B: konsentrasi di garis batas -> 20 hari dari cache per hari
        if conc10 is not None and BORDER_LO <= conc10 <= BORDER_HI:
            res["triggers"].append("B")
            d20 = self._days(day, 20)
            missing = [d for d in d20 if not self.store.has(sym, d)]
            if 0 < len(missing) <= MAX_FILL_DAYS and self._take_quota(len(missing)):
                try:  # % konsentrasi butuh nilai per hari -> tambal pakai tarikan per hari
                    self.store.ensure(auth, sym, missing)
                except Exception as e:  # noqa: BLE001
                    log.warning("Tambal broksum %s gagal: %s", sym, e)
            c20 = broksum.concentration(self.store, sym, d20)
            if c20 and c20["n_days"] >= MIN_COVER * 20:
                res["conc20"] = c20["conc"]
                if c20["conc"] >= broksum.CONC_HIGH:
                    v = "tetap dijaga (kuat)"
                elif c20["conc"] < BORDER_LO:
                    v = "melemah — 10 hari terakhir cuma lonjakan sesaat"
                else:
                    v = "masih di garis batas"
                res["findings"].append(f"B: konsentrasi 10h {conc10 * 100:.0f}% → 20h {c20['conc'] * 100:.0f}%: {v}")
            else:
                res["findings"].append(f"B: konsentrasi 10h {conc10 * 100:.0f}% di garis batas, cache 20 hari belum cukup")

        # --- C: penampung berganti -> 30 hari: penampung lama sedang buang?
        if len(rows10) >= broksum.CONC_MIN_DAYS and top3:
            last3 = self._cache_net(sym, d10[-3:]) or {}
            main, main_acc = top3[0], net10.get(top3[0], 0)
            sold3 = -last3.get(main, 0)
            if main_acc > 0 and sold3 >= MAIN_SELL_FRAC * main_acc:
                res["triggers"].append("C")
                why = f"penampung utama {main} jual {_rp(sold3)} dalam 3 hari ({sold3 / main_acc * 100:.0f}% akumulasinya)"
                net30, src = self._net(auth, sym, self._days(day, 30))
                if net30 is None:
                    res["findings"].append(f"C: {why}; data 30 hari tidak bisa ditarik")
                else:
                    holders = _top(net30)
                    dumping = [(c, net10.get(c, 0)) for c, v30 in holders
                               if net10.get(c, 0) < 0 and -net10.get(c, 0) >= DUMP_FRAC * (v30 - net10.get(c, 0))]
                    res["holders30"] = [c for c, _ in holders]
                    res["dumping"] = [c for c, _ in dumping]
                    if dumping:
                        v = "penampung lama MEMBUANG di 10 hari terakhir: " + ", ".join(f"{c} {_rp(-x)}" for c, x in dumping)
                    else:
                        v = "penampung 30 hari (" + ", ".join(c for c, _ in holders) + ") tidak ikut membuang"
                    res["findings"].append(f"C: {why} → {v} <i>({src})</i>")

        # --- D: harga sudah lari -> 20 hari sebelum jendela: akumulasi mulai kapan?
        mv = self._move(sym, d10)
        res["move10"] = mv
        if mv is not None and abs(mv) >= MOVE_BIG and top3:
            res["triggers"].append("D")
            before = broksum.prior_trading_days(d10[0], 20, self.is_trading_day)
            netb, src = self._net(auth, sym, before)
            if netb is None:
                res["findings"].append(f"D: harga {mv * 100:+.0f}% dalam 10 hari; data sebelumnya tidak bisa ditarik")
            else:
                pre = sum(netb.get(c, 0) for c in top3)
                now = sum(net10.get(c, 0) for c in top3)
                res["pre_net"], res["win_net"] = pre, now
                up = mv > 0
                if pre > 0 and now > 0 and pre >= 0.3 * now:
                    v = ("penampung sekarang SUDAH beli sebelum harga naik (akumulasi lebih awal)" if up else
                         "penampung sekarang sudah beli sejak sebelum harga turun (terus menampung / rata-rata turun)")
                elif pre < 0:
                    v = ("penampung sekarang sebelumnya justru JUAL — baru masuk saat harga sudah naik" if up else
                         "penampung sekarang sebelumnya JUAL — baru menampung setelah harga turun")
                else:
                    v = ("penampung sekarang baru masuk saat harga sudah naik (ikut arus)" if up else
                         "penampung sekarang baru menampung setelah harga turun")
                res["findings"].append(f"D: harga {mv * 100:+.0f}% dlm 10h → {v} "
                                       f"(net mereka 20h sebelumnya {_rp(pre)}) <i>({src})</i>")

        # --- E: running trade beli dominan / watchlist, tapi broksum distribusi
        buy_dom = in_watch or ((n_buy + n_sell) >= 3 and n_buy >= 2 * n_sell)
        today_row = self.store.get(sym, day)
        dist = bool(today_row and (today_row["top5"] <= -10 or today_row["retail"] > 0.05))
        if conc10 is not None and conc10 < broksum.CONC_LOW:
            dist = True
        if buy_dom and dist:
            res["triggers"].append("E")
            net20, src = self._net(auth, sym, self._days(day, 20))
            if net20 is None:
                res["findings"].append("E: beli dominan di running trade tapi broksum distribusi; data 20 hari tidak bisa ditarik")
            else:
                holders = _top(net20)
                last5 = self._cache_net(sym, self._days(day, 5)) or {}
                still = [c for c, _ in holders if last5.get(c, 0) > 0]
                res["holders20"], res["still_buying"] = [c for c, _ in holders], still
                if holders and len(still) >= 2:
                    v = "penampung 20 hari (" + ", ".join(still) + ") masih beli 5 hari terakhir — HAKA mungkin didukung"
                else:
                    v = "penampung 20 hari tidak ikut beli — beli di running trade kemungkinan tidak didukung"
                res["findings"].append(f"E: running trade beli tapi broksum distribusi → {v} <i>({src})</i>")
        return res

    # ---------- jalankan untuk daftar saham ----------
    def run(self, auth, day: str, cands: list[tuple[str, int, int, bool]]) -> list[str]:
        """cands = [(sym, n_buy, n_sell, in_watch)]. Return pesan Telegram (kosong kalau tak ada pemicu)."""
        results = []
        for sym, nb, ns, iw in cands:
            try:
                r = self.evaluate(auth, sym, day, nb, ns, iw)
            except Exception as e:  # noqa: BLE001
                log.warning("Broksum adaptif %s gagal: %s", sym, e)
                continue
            results.append(r)
            self._log(r)
        hit = [r for r in results if r["triggers"]]
        if not hit:
            return []
        lines = [f"🔎 <b>Broksum lanjutan</b> · {day}",
                 f"{len(hit)} dari {len(results)} saham butuh data tambahan "
                 f"({self.req_count} request tambahan dipakai hari ini)"]
        for r in hit:
            lines.append(f"\n<b>{r['sym']}</b>  ·  pemicu {', '.join(r['triggers'])}")
            lines += [f"• {f}" for f in r["findings"]]
        lines.append("\n<i>A data kurang · B konsentrasi di garis batas · C penampung utama membuang · "
                     "D harga sudah lari · E running trade vs broksum bentrok. Pemicu belum teruji.</i>")
        msgs, chunk = [], ""
        for ln in lines:
            if len(chunk) + len(ln) > 3500:
                msgs.append(chunk)
                chunk = ""
            chunk += ("\n" if chunk else "") + ln
        if chunk:
            msgs.append(chunk)
        return msgs

    def _log(self, r: dict) -> None:
        try:
            path = os.path.join(self.data_dir, f"broksum-adaptive-{r['day'][:7]}.jsonl")
            with open(path, "a", encoding="utf-8") as f:
                ctx = self.context_fn() if self.context_fn else {}
                f.write(json.dumps({"ts": round(time.time()), **ctx, **r}, ensure_ascii=False, default=str) + "\n")
        except OSError as e:
            log.warning("Gagal catat broksum adaptif: %s", e)
