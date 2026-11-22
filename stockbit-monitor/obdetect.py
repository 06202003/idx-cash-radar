"""Pendeteksi pola mencurigakan di saham pantauan -- TAHAP 1: CATAT KANDIDAT SAJA, tanpa alert.

Tiga pola, semuanya "mirip", BUKAN bukti (tidak ada ID order / pemilik order di data):

1. WALL_PULLED -- tembok dicabut. Level bid/offer yang jauh lebih tebal dari level di
   sekitarnya hilang/menyusut >= PULL_FRAC padahal harga TIDAK PERNAH menyentuh level itu
   di antara 2 snapshot (antrean cuma bisa dimakan lewat transaksi di harga itu -> kalau
   harga nggak sampai, berarti ditarik). Level teratas (best bid/offer) TIDAK dinilai
   karena ambigu (bisa dimakan). Level yang keluar dari jangkauan snapshot juga tidak.
2. ICEBERG -- antrean di best bid/offer terus dimakan tapi lot-nya nggak berkurang
   (terisi lagi) beberapa snapshot berturut-turut. Transaksi yang teramati bot cuma
   sebagian dari aslinya, jadi angka "termakan" itu BATAS BAWAH -> penilaian konservatif.
3. ALGO_LIKE -- broker yang sama jadi agresor (HAKA/HAKI) berulang dengan ukuran lot
   seragam dalam window pendek (ciri order dipecah otomatis / TWAP). Keteraturan jeda
   dicatat tapi tidak disyaratkan (sampling running trade bikin jedanya kacau).

Batas resolusi: snapshot orderbook tiap ~10 dtk -> order yang hidup < 10 dtk tak terlihat.
Semua kandidat ke data/obdetect-YYYY-MM.jsonl buat dicek manual & diuji ke harga nanti.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from collections import Counter, defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("obdetect")

STALE_SNAP_SEC = 60  # jarak 2 snapshot lebih dari ini -> tidak dibandingkan


def _broker(raw) -> str:
    """'AK [F]' -> 'AK'."""
    return str(raw or "").split("[")[0].strip().upper()


class PatternDetector:
    def __init__(self, data_dir: str, wall_mult: float = 5.0, wall_min_idr: float = 250e6,
                 pull_frac: float = 0.7, iceberg_snaps: int = 3, iceberg_eaten_frac: float = 0.3,
                 algo_window_sec: int = 600, algo_min_trades: int = 6, algo_max_cv: float = 0.15,
                 algo_cooldown_sec: int = 600):
        self.data_dir = data_dir
        self.wall_mult = wall_mult
        self.wall_min_idr = wall_min_idr
        self.pull_frac = pull_frac
        self.iceberg_snaps = iceberg_snaps
        self.iceberg_eaten_frac = iceberg_eaten_frac
        self.algo_window_sec = algo_window_sec
        self.algo_min_trades = algo_min_trades
        self.algo_max_cv = algo_max_cv
        self.algo_cooldown_sec = algo_cooldown_sec
        self.day = ""
        self.prev: dict[str, dict] = {}  # stock -> snapshot terakhir
        self.walls: dict[tuple, dict] = {}  # (stock, side, price) -> info tembok
        self.between: dict[str, dict] = {}  # stock -> transaksi teramati sejak snapshot terakhir
        self.ice: dict[tuple, int] = {}  # (stock, side, price) -> berapa snapshot beruntun terisi lagi
        self.ice_logged: set = set()
        self.agg: dict[tuple, deque] = defaultdict(deque)  # (stock, broker, side) -> (ts, lot, price)
        self.algo_last: dict[tuple, float] = {}
        self.today_counts: Counter = Counter()
        self.recent: deque = deque(maxlen=200)
        self.context_fn = None  # -> dict kondisi IHSG, diisi monitor.py

    # ---------- util ----------
    def _roll_day(self, ts: float) -> None:
        today = datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self.day = today
            self.prev, self.walls, self.between, self.ice = {}, {}, {}, {}
            self.ice_logged, self.agg, self.algo_last = set(), defaultdict(deque), {}
            self.today_counts, self.recent = Counter(), deque(maxlen=200)

    def _emit(self, kind: str, stock: str, ts: float, **info) -> dict:
        ctx = {}
        try:
            ctx = self.context_fn() if self.context_fn else {}
        except Exception:  # noqa: BLE001
            pass
        rec = {"ts": round(ts), "kind": kind, "stock": stock, **ctx, **info}
        self.today_counts[(stock, kind)] += 1
        self.recent.append(rec)
        try:
            path = os.path.join(self.data_dir, f"obdetect-{datetime.fromtimestamp(ts, tz=WIB).strftime('%Y-%m')}.jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("Gagal catat obdetect: %s", e)
        log.info("POLA %s %s %s", kind, stock, info)
        return rec

    # ---------- input: running trade (hanya saham pantauan) ----------
    def on_trade(self, stock: str, ts: float, price: float, lot: float, action: str,
                 buyer, seller) -> list[dict]:
        self._roll_day(ts)
        b = self.between.setdefault(stock, {"lo": price, "hi": price, "at": defaultdict(float)})
        b["lo"], b["hi"] = min(b["lo"], price), max(b["hi"], price)
        b["at"][price] += lot

        if action not in ("buy", "sell"):
            return []
        broker = _broker(buyer if action == "buy" else seller)
        if not broker:
            return []
        key = (stock, broker, action)
        dq = self.agg[key]
        dq.append((ts, lot, price))
        while dq and dq[0][0] < ts - self.algo_window_sec:
            dq.popleft()
        if len(dq) < self.algo_min_trades or ts - self.algo_last.get(key, 0) < self.algo_cooldown_sec:
            return []
        lots = [x[1] for x in dq]
        mean = statistics.fmean(lots)
        if mean <= 0:
            return []
        cv = statistics.pstdev(lots) / mean
        if cv > self.algo_max_cv:
            return []
        self.algo_last[key] = ts
        gaps = [b2[0] - b1[0] for b1, b2 in zip(dq, list(dq)[1:])]
        gap_cv = statistics.pstdev(gaps) / statistics.fmean(gaps) if gaps and statistics.fmean(gaps) > 0 else None
        return [self._emit("ALGO_LIKE", stock, ts, broker=broker, side=action, n=len(dq),
                           lot_mean=round(mean, 1), lot_cv=round(cv, 3),
                           gap_cv=None if gap_cv is None else round(gap_cv, 2),
                           span_sec=round(dq[-1][0] - dq[0][0]), price_first=dq[0][2], price_last=dq[-1][2])]

    # ---------- input: snapshot orderbook (semua level) ----------
    def _is_wall(self, side_levels: list, idx: int) -> bool:
        p, lot = side_levels[idx][0], side_levels[idx][1]
        others = [lv[1] for i, lv in enumerate(side_levels[:10]) if i != idx]
        if len(others) < 3:
            return False
        med = statistics.median(others)
        return lot * p * 100 >= self.wall_min_idr and med > 0 and lot >= self.wall_mult * med

    def on_snapshot(self, stock: str, ts: float, snap: dict) -> list[dict]:
        """snap = orderbook.parse_stockbit(payload, max_levels besar): {"bids","offers","last",...}."""
        self._roll_day(ts)
        out: list[dict] = []
        bids, offers = snap.get("bids") or [], snap.get("offers") or []
        if not bids or not offers:
            return out
        between = self.between.pop(stock, None)
        prev = self.prev.get(stock)
        if prev and ts - prev["ts"] > STALE_SNAP_SEC:
            # snapshot sebelumnya kelamaan (saham sempat keluar pantauan / pengumpul jeda) ->
            # jangan bandingkan, tembok lama juga dibuang biar nggak salah dinilai "dicabut"
            self.forget(stock)
            prev, between = None, None
        last = snap.get("last") or 0

        # harga terendah/tertinggi yang mungkin TERSENTUH sejak snapshot sebelumnya
        lo_candidates = [bids[0][0], last] + ([prev["bids"][0][0], prev.get("last") or bids[0][0]] if prev else [])
        hi_candidates = [offers[0][0], last] + ([prev["offers"][0][0], prev.get("last") or offers[0][0]] if prev else [])
        lo_candidates = [x for x in lo_candidates if x]
        hi_candidates = [x for x in hi_candidates if x]
        touched_lo = min(lo_candidates + ([between["lo"]] if between else []))
        touched_hi = max(hi_candidates + ([between["hi"]] if between else []))

        for side, levels in (("bid", bids), ("offer", offers)):
            now_lot = {lv[0]: lv for lv in levels}
            # 1) catat/perbarui tembok yang terlihat sekarang (bukan level teratas)
            for i in range(1, min(len(levels), 10)):
                if self._is_wall(levels, i):
                    p, lot, que = levels[i][0], levels[i][1], (levels[i][2] if len(levels[i]) > 2 else 0)
                    w = self.walls.setdefault((stock, side, p), {"first": ts, "max_lot": lot, "que": que})
                    if lot >= w["max_lot"]:
                        w["max_lot"], w["que"] = lot, que
                    w["last"] = ts
            # 2) nilai tembok lama yang menyusut / hilang
            edge = levels[-1][0]  # level terjauh yang masih kelihatan
            for key in [k for k in self.walls if k[0] == stock and k[1] == side]:
                p = key[2]
                w = self.walls[key]
                in_range = p >= edge if side == "bid" else p <= edge
                if not in_range:
                    continue  # keluar jangkauan snapshot -> tidak bisa dinilai, biarkan
                lot_now = now_lot[p][1] if p in now_lot else 0.0
                if lot_now > w["max_lot"] * (1 - self.pull_frac):
                    continue
                del self.walls[key]
                untouched = touched_lo > p if side == "bid" else touched_hi < p
                if not untouched:
                    continue  # harga sampai ke level itu -> bisa jadi dimakan, bukan dicabut
                best = levels[0][0]
                out.append(self._emit(
                    "WALL_PULLED", stock, ts, side=side, price=p, lot_max=round(w["max_lot"]),
                    lot_now=round(lot_now), que=w["que"], value_idr=round(w["max_lot"] * p * 100),
                    life_sec=round(w.get("last", ts) - w["first"]), best=best,
                    dist_pct=round(abs(p / best - 1) * 100, 2), last=last,
                ))

        # 3) iceberg di level teratas: dimakan (teramati) tapi lot nggak turun
        if prev and between:
            for side, levels, prev_levels in (("bid", bids, prev["bids"]), ("offer", offers, prev["offers"])):
                p, lot_now = levels[0][0], levels[0][1]
                key = (stock, side, p)
                if prev_levels[0][0] != p:
                    self.ice.pop(key, None)
                    continue
                prev_lot = prev_levels[0][1]
                eaten = between["at"].get(p, 0.0)
                if prev_lot > 0 and eaten >= self.iceberg_eaten_frac * prev_lot and lot_now >= 0.8 * prev_lot:
                    self.ice[key] = self.ice.get(key, 0) + 1
                    if self.ice[key] >= self.iceberg_snaps and key not in self.ice_logged:
                        self.ice_logged.add(key)
                        out.append(self._emit("ICEBERG", stock, ts, side=side, price=p, lot_now=round(lot_now),
                                              eaten_seen=round(eaten), snaps=self.ice[key], last=last))
                else:
                    self.ice.pop(key, None)

        self.prev[stock] = {"ts": ts, "bids": bids[:10], "offers": offers[:10], "last": last}
        return out

    def forget(self, stock: str) -> None:
        """Saham keluar pantauan: buang state-nya biar nggak nilai snapshot yang bolong lama."""
        self.prev.pop(stock, None)
        self.between.pop(stock, None)
        for k in [k for k in self.walls if k[0] == stock]:
            del self.walls[k]

    # ---------- tampilan ----------
    def format_summary(self, stock: str | None = None) -> str:
        names = {"WALL_PULLED": "tembok dicabut", "ICEBERG": "iceberg", "ALGO_LIKE": "pola algo"}
        items = [r for r in self.recent if stock is None or r["stock"] == stock]
        if not items:
            who = stock or "saham pantauan"
            return f"🔍 Belum ada kandidat pola untuk {who} hari ini."
        counts = Counter(r["kind"] for r in items)
        lines = [f"🔍 <b>Kandidat pola</b> {stock or 'hari ini'}: "
                 + ", ".join(f"{names[k]} {v}" for k, v in counts.items())]
        for r in list(items)[-10:]:
            t = datetime.fromtimestamp(r["ts"], tz=WIB).strftime("%H:%M:%S")
            if r["kind"] == "WALL_PULLED":
                d = (f"{r['side']} {r['price']:,.0f} · {r['lot_max']:,} lot ({r['que']} antrean) "
                     f"hidup {r['life_sec']} dtk · ").replace(",", ".") + f"{r['dist_pct']:.2f}".replace(".", ",") + "% dari best"
            elif r["kind"] == "ICEBERG":
                d = f"{r['side']} {r['price']:,.0f} terisi lagi {r['snaps']}x · termakan ≥{r['eaten_seen']:,} lot".replace(",", ".")
            else:
                d = (f"{r['broker']} {'HAKA' if r['side'] == 'buy' else 'HAKI'} {r['n']}x "
                     f"±{r['lot_mean']:,.0f} lot dlm {r['span_sec']} dtk").replace(",", ".")
            lines.append(f"• {t} <b>{r['stock']}</b> {names[r['kind']]}: {d}")
        lines.append("<i>Kandidat = pola mirip, bukan bukti. Belum diuji ke harga.</i>")
        return "\n".join(lines)
