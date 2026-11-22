"""Tabel bukti harian: 1 baris per saham per hari, gabungan SEMUA analisa + hasil sesudahnya.

Tujuannya "connecting the dots": kombinasi antar sumber (running trade, watchlist,
orderbook, broksum, teknikal, IHSG) bisa diuji tanpa ngumpulin data baru. Hipotesis yang
dinilai ditetapkan DULUAN di HIPOTESIS.md (biar nggak ngubek-ubek data sampai ketemu yang
kebetulan bagus).

File: data/evidence/YYYY-MM-DD.jsonl. Dibuat otomatis tiap sore (sesudah rekap), kolom hasil
(r1/r5/rel1/rel5) diisi belakangan begitu harga hari-hari berikutnya sudah ada.

Saham yang masuk tabel per hari: universe (216 saham likuid) + saham dengan >=3 alert +
saham watchlist + saham yang punya kandidat pola / broksum adaptif hari itu.

Kolom:
  day, sym
  teknikal (bar harian s.d. hari itu): trend, rsi, vr (nilai transaksi vs rata2 20h), ret, close
  broksum (cache per hari): conc10, acc_today (akumulator 5h hari ini), top5, retail, foreign
  running trade: n_buy, n_sell, buy_dom, codes (penilaian alert)
  watchlist: watch_enter, watch_exit_gain, watch_exit_reason
  orderbook/pola: wall_bid, wall_offer, iceberg, algo_buy, algo_sell
  broksum adaptif: adapt (pemicu), d_early (D: akumulasi sebelum harga gerak)
  IHSG: ihsg_trend (s.d. kemarin), ihsg_day_pct
  hasil: r1, r5, rel1, rel5 (open besok -> close besok / close +5 hari bursa)
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import broksum
import technical

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("evidence")


def _day_of(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d")


def _read_jsonl(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


class EvidenceTable:
    def __init__(self, data_dir: str, store: broksum.BroksumStore, bars: technical.DailyBars,
                 is_trading_day, universe: list[str]):
        self.data_dir = data_dir
        self.dir = os.path.join(data_dir, "evidence")
        os.makedirs(self.dir, exist_ok=True)
        self.store = store
        self.bars = bars
        self.is_trading_day = is_trading_day
        self.universe = universe

    # ---------- sumber per hari ----------
    def _month_files(self, prefix: str, day: str) -> str:
        return os.path.join(self.data_dir, f"{prefix}-{day[:7]}.jsonl")

    def _alerts(self, day: str):
        out = defaultdict(lambda: {"buy": 0, "sell": 0, "codes": Counter()})
        for r in _read_jsonl(self._month_files("alerts", day)):
            if _day_of(r.get("ts", 0)) != day:
                continue
            a = out[r["stock"]]
            if r.get("action") in ("buy", "sell"):
                a[r["action"]] += 1
            a["codes"][r.get("code") or "?"] += 1
        return out

    def _watch(self, day: str):
        out = defaultdict(dict)
        for r in _read_jsonl(self._month_files("watch", day)):
            if _day_of(r.get("ts", 0)) != day:
                continue
            w = out[r["stock"]]
            if r.get("event") == "enter":
                w["watch_enter"] = True
            elif r.get("event") == "exit":
                w["watch_exit_gain"] = r.get("gain")
                w["watch_exit_reason"] = (r.get("reason") or "")[:60]
        return out

    def _patterns(self, day: str):
        out = defaultdict(Counter)
        for r in _read_jsonl(self._month_files("obdetect", day)):
            if _day_of(r.get("ts", 0)) != day:
                continue
            k = r.get("kind")
            if k == "WALL_PULLED":
                out[r["stock"]]["wall_" + r.get("side", "?")] += 1
            elif k == "ICEBERG":
                out[r["stock"]]["iceberg"] += 1
            elif k == "ALGO_LIKE":
                out[r["stock"]]["algo_" + r.get("side", "?")] += 1
        return out

    def _adaptive(self, day: str):
        out = {}
        for r in _read_jsonl(self._month_files("broksum-adaptive", day)):
            if r.get("day") != day:
                continue
            rec = {"adapt": r.get("triggers") or []}
            pre, now = r.get("pre_net"), r.get("win_net")
            if pre is not None and now is not None:
                rec["d_early"] = bool(pre > 0 and now > 0 and pre >= 0.3 * now)
            out[r["sym"]] = rec
        return out

    def _ihsg(self, day: str) -> dict:
        path = os.path.join(self.data_dir, "daily", "_JKSE.json")
        try:
            with open(path, encoding="utf-8") as f:
                bars = json.load(f)  # [[day, close], ...]
        except (OSError, json.JSONDecodeError):
            return {}
        closes = [(d, c) for d, c in bars if d <= day]
        prev = [c for d, c in closes if d < day]
        out = {}
        if len(prev) >= 50:
            c, ma20, ma50 = prev[-1], sum(prev[-20:]) / 20, sum(prev[-50:]) / 50
            out["ihsg_trend"] = "up" if c > ma20 > ma50 else "down" if c < ma20 < ma50 else "side"
        if closes and closes[-1][0] == day and prev:
            out["ihsg_day_pct"] = round((closes[-1][1] / prev[-1] - 1) * 100, 2)
        return out

    # ---------- bangun 1 hari ----------
    def build_day(self, day: str) -> int:
        alerts, watch, pats, adapt = self._alerts(day), self._watch(day), self._patterns(day), self._adaptive(day)
        syms = set(self.universe) | {s for s, a in alerts.items() if a["buy"] + a["sell"] >= 3}
        syms |= set(watch) | set(pats) | set(adapt)
        ihsg = self._ihsg(day)
        d10 = broksum.prior_trading_days(day, 9, self.is_trading_day) + [day]
        rows = []
        for sym in sorted(syms):
            row = {"day": day, "sym": sym, **ihsg}
            try:
                b = [x for x in self.bars.get(sym) if x[0] <= day]
            except Exception:  # noqa: BLE001
                b = []
            if b and b[-1][0] == day:
                ind = technical.indicators(b)
                if ind:
                    row.update({"trend": technical.trend(ind), "rsi": round(ind["rsi"], 1),
                                "vr": round(ind["vr"], 2), "ret": round(ind["ret"], 4), "close": ind["c"]})
            today = self.store.get(sym, day)
            if today:
                row.update({"top5": today["top5"], "retail": round(today["retail"], 4),
                            "foreign": round(today["foreign"], 4)})
                c = broksum.concentration(self.store, sym, d10)
                if c:
                    row["conc10"] = round(c["conc"], 4)
                acc = broksum.accumulators(self.store, sym, d10[-6:-1], today)
                if acc:
                    row["acc_today"] = round(acc["today"], 4)
            a = alerts.get(sym)
            if a:
                row.update({"n_buy": a["buy"], "n_sell": a["sell"], "codes": dict(a["codes"]),
                            "buy_dom": (a["buy"] + a["sell"]) >= 3 and a["buy"] >= 2 * a["sell"]})
            row.update(watch.get(sym, {}))
            row.update(dict(pats.get(sym, {})))
            row.update(adapt.get(sym, {}))
            rows.append(row)
        path = os.path.join(self.dir, f"{day}.jsonl")
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        return len(rows)

    # ---------- isi kolom hasil ----------
    def fill_outcomes(self) -> int:
        """Isi r1/r5/rel1/rel5 untuk hari-hari yang harganya sudah tersedia. Return jumlah hari diperbarui."""
        updated = 0
        for fname in sorted(os.listdir(self.dir)):
            if not fname.endswith(".jsonl"):
                continue
            day = fname[:10]
            path = os.path.join(self.dir, fname)
            rows = list(_read_jsonl(path))
            if not rows or all("r5" in r for r in rows):
                continue
            changed = False
            for r in rows:
                if "r5" in r:
                    continue
                try:
                    b = self.bars.get(r["sym"])
                except Exception:  # noqa: BLE001
                    continue
                idx = next((i for i, x in enumerate(b) if x[0] == day), None)
                if idx is None or idx + 1 >= len(b) or b[idx + 1][1] <= 0:
                    continue
                o = b[idx + 1][1]
                gap = o / b[idx][4] - 1 if b[idx][4] else 0
                if "r1" not in r:
                    r["r1"] = round(b[idx + 1][4] / o - 1, 4)
                    r["gap_limit"] = gap >= 0.19  # buka di ARA -> praktis tidak bisa dibeli
                    changed = True
                if idx + 5 < len(b):
                    r["r5"] = round(b[idx + 5][4] / o - 1, 4)
                    changed = True
            if not changed:
                continue
            for key, rel in (("r1", "rel1"), ("r5", "rel5")):
                mk = [r[key] for r in rows if key in r and r["sym"] in self.universe]
                if len(mk) >= 50:
                    m = sum(mk) / len(mk)
                    for r in rows:
                        if key in r:
                            r[rel] = round(r[key] - m, 4)
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, path)
            updated += 1
        return updated

    def run_daily(self, day: str) -> str:
        """Dipanggil tiap sore: bangun ulang kemarin (bar harian Yahoo kadang telat) + hari ini,
        lalu isi kolom hasil hari-hari sebelumnya."""
        prev = broksum.prior_trading_days(day, 1, self.is_trading_day)[0]
        n_prev = self.build_day(prev) if os.path.exists(os.path.join(self.dir, f"{prev}.jsonl")) else 0
        n = self.build_day(day)
        filled = self.fill_outcomes()
        msg = f"tabel bukti {day}: {n} baris (kemarin dibangun ulang: {n_prev}), hasil terisi untuk {filled} hari"
        log.info(msg)
        return msg
