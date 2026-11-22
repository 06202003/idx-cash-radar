"""Penarik data riset malam hari (riset 1 = pita transaksi, riset 6 = broksum mundur).

Jalan di dalam proses bot (satu sesi Stockbit, tidak rebutan refresh token), HANYA di jendela
malam (RESEARCH_WINDOW, default 19:00-06:30 WIB), maksimal RESEARCH_MAX_REQ request per malam
(default 5000), ±1 request per 2 detik, dua pekerjaan digilir bergantian. Progres disimpan terus,
jadi kalau berhenti tinggal lanjut.

Rencana DIKUNCI di data/research/plan.json saat pertama jalan (aturan di build_plan):
- Riset 6 (broksum): saham universe × hari di periode IHSG tren naik dalam jangkauan data
  (± 1 tahun) + 10 hari bursa pemanasan sebelum tiap periode. Disimpan ke cache broksum biasa
  (data/broksum/HARI.json) — hari yang sudah ada dilewati.
- Riset 1 (pita): 10 saham × 40 hari (20 hari IHSG tren naik + 20 hari tren turun, tersebar
  merata). Saham: universe, harga >= Rp100, median nilai harian >= Rp5 M di KEDUA periode,
  diurutkan nilai dan dibuang yang median nilainya > Rp40 M (BRPT ±Rp100 M = >200 request/hari), ambil 10 teratas.
  Disimpan ke data/research/tapes/KODE/HARI.jsonl.gz.

Berhenti sendiri + kabar Telegram kalau error beruntun / sesi habis / kena batas.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import random
import statistics
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import broksum
from stockbit_auth import COMMON_HEADERS, ManualReloginRequired, StockbitAuthClient
from stockbit_running_trade import URL as RT_URL

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("research_collect")

MAX_ERR = 10
TAPE_FIELDS = ("time", "action", "price", "lot", "buyer", "seller", "trade_number", "market_board")


def _num(x) -> float:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


class ResearchCollector:
    def __init__(self, data_dir: str, token_cache_path: str, is_trading_day, universe: list[str],
                 max_req: int = 5000, window: tuple[str, str] = ("19:00", "06:30"),
                 store: broksum.BroksumStore | None = None):
        self.data_dir = data_dir
        self.dir = os.path.join(data_dir, "research")
        os.makedirs(os.path.join(self.dir, "tapes"), exist_ok=True)
        self.plan_path = os.path.join(self.dir, "plan.json")
        self.state_path = os.path.join(self.dir, "state.json")
        self.token_cache_path = token_cache_path
        self.is_trading_day = is_trading_day
        self.universe = universe
        self.max_req = max_req
        self.window = window
        self.store = store or broksum.BroksumStore(data_dir)  # pakai cache yang sama dengan bot
        self.state = self._load_json(self.state_path, {"night": "", "used": 0, "tapes": {}, "stopped": "",
                                                       "total_req": 0, "reported": ""})
        self.plan = None
        self._auth = None

    # ---------- util ----------
    @staticmethod
    def _load_json(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    def _save_state(self) -> None:
        tmp = f"{self.state_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.state_path)

    def _night(self, now: datetime) -> str:
        """Malam dihitung dari tanggal mulai jendela (06:00 pagi masih 'malam kemarin')."""
        d = now if now.strftime("%H:%M") >= self.window[0] else now - timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def in_window(self, now: datetime) -> bool:
        hm = now.strftime("%H:%M")
        return hm >= self.window[0] or hm < self.window[1]

    # ---------- rencana (dikunci) ----------
    def _ihsg_trend(self) -> dict:
        bars = self._load_json(os.path.join(self.data_dir, "daily", "_JKSE.json"), [])
        out = {}
        closes = [c for _, c in bars]
        for i in range(50, len(bars)):
            c, m20, m50 = closes[i], sum(closes[i - 19:i + 1]) / 20, sum(closes[i - 49:i + 1]) / 50
            out[bars[i][0]] = "up" if c > m20 > m50 else "down" if c < m20 < m50 else "side"
        return out

    def build_plan(self) -> dict:
        tr = self._ihsg_trend()
        days = sorted(tr)
        # periode IHSG tren naik >= 5 hari berturut-turut
        runs, cur = [], None
        for d in days:
            if tr[d] == "up":
                cur = [d, d] if cur is None else [cur[0], d]
            elif cur:
                runs.append(cur)
                cur = None
        if cur:
            runs.append(cur)
        runs = [r for r in runs if sum(1 for d in days if r[0] <= d <= r[1]) >= 5]
        bk_days = set()
        for a, b in runs:
            bk_days |= {d for d in days if a <= d <= b}
            bk_days |= set(broksum.prior_trading_days(a, 10, self.is_trading_day))
        up_days = sorted(d for d in days if tr[d] == "up")
        down_days = sorted(d for d in days if tr[d] == "down" and d >= "2026-10-01")
        pick = lambda xs, n: [xs[round(i * (len(xs) - 1) / (n - 1))] for i in range(n)] if len(xs) >= n else xs
        # bagian pita: periode naik terbaru (jendela retensi ±1 tahun) + periode turun terbaru
        last_up = runs[-1] if runs else None
        up_pool = [d for d in up_days if last_up and last_up[0] <= d <= last_up[1]]
        t_days = pick(up_pool, 20) + pick(down_days, 20)

        def med_val(sym, lo, hi):
            b = self._load_json(os.path.join(self.data_dir, "daily", f"{sym}.json"), [])
            v = [x[4] * x[5] for x in b if lo <= x[0] <= hi]
            return (statistics.median(v) if len(v) >= 10 else 0), (b[-1][4] if b else 0)
        cands = []
        if up_pool and down_days:
            for s in self.universe:
                v1, px = med_val(s, up_pool[0], up_pool[-1])
                v2, _ = med_val(s, down_days[0], down_days[-1])
                if px >= 100 and min(v1, v2) >= 5e9 and max(v1, v2) <= 40e9:  # >Rp40 M/hari = pita terlalu mahal
                    cands.append((min(v1, v2), s))
        t_syms = [s for _, s in sorted(cands, reverse=True)[:10]]
        plan = {"created": datetime.now(WIB).isoformat(timespec="seconds"),
                "ihsg_up_runs": runs, "broksum_days": sorted(bk_days), "broksum_syms": list(self.universe),
                "tape_syms": t_syms, "tape_days": t_days}
        with open(self.plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        return plan

    def load_plan(self) -> dict:
        if self.plan is None:
            self.plan = self._load_json(self.plan_path, None) or self.build_plan()
        return self.plan

    # ---------- antrean pekerjaan ----------
    def _next_broksum(self):
        p = self.load_plan()
        for d in p["broksum_days"]:
            for s in p["broksum_syms"]:
                if not self.store.has(s, d):
                    return s, d
        return None

    def _next_tape(self):
        p = self.load_plan()
        for s in p["tape_syms"]:
            for d in p["tape_days"]:
                if not self.state["tapes"].get(f"{s}|{d}", {}).get("done"):
                    return s, d
        return None

    def progress(self) -> dict:
        p = self.load_plan()
        bk_total = len(p["broksum_days"]) * len(p["broksum_syms"])
        bk_done = sum(1 for d in p["broksum_days"] for s in p["broksum_syms"] if self.store.has(s, d))
        t_total = len(p["tape_syms"]) * len(p["tape_days"])
        t_done = sum(1 for v in self.state["tapes"].values() if v.get("done"))
        return {"bk_done": bk_done, "bk_total": bk_total, "t_done": t_done, "t_total": t_total,
                "trades": sum(v.get("n", 0) for v in self.state["tapes"].values())}

    # ---------- 1 request ----------
    def _auth_client(self) -> StockbitAuthClient:
        if self._auth is None:
            a = StockbitAuthClient(token_cache_path=self.token_cache_path)
            a.load_token_cache(self.token_cache_path)
            self._auth = a
        return self._auth

    def step_broksum(self, s: str, d: str) -> None:
        self.store.fetch(self._auth_client(), s, d)  # _authed_get: refresh otomatis kalau 401

    def step_tape(self, s: str, d: str) -> None:
        key = f"{s}|{d}"
        st = self.state["tapes"].setdefault(key, {"cursor": None, "n": 0, "done": False})
        a = self._auth_client()
        params = {"sort": "DESC", "order_by": "RUNNING_TRADE_ORDER_BY_TIME", "limit": 100, "symbols": s, "date": d}
        if st["cursor"]:
            params["trade_number"] = st["cursor"]
        headers = dict(COMMON_HEADERS)
        headers["Authorization"] = f"Bearer {a.ensure_valid_token()}"
        r = requests.get(RT_URL, headers=headers, params=params, timeout=20)
        if r.status_code == 401:
            a.refresh()
            headers["Authorization"] = f"Bearer {a.token.access_token}"
            r = requests.get(RT_URL, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json().get("data") or {}
        if data.get("date") and data["date"] != d:
            raise RuntimeError(f"tanggal respons {data.get('date')} != {d}")
        trades = data.get("running_trade") or []
        if trades:
            out_dir = os.path.join(self.dir, "tapes", s)
            os.makedirs(out_dir, exist_ok=True)
            with gzip.open(os.path.join(out_dir, f"{d}.jsonl.gz"), "at", encoding="utf-8") as f:
                for t in trades:
                    f.write(json.dumps([t.get(k) for k in TAPE_FIELDS], separators=(",", ":")) + "\n")
            st["n"] += len(trades)
            st["cursor"] = int(min(_num(t.get("trade_number")) for t in trades))
        if len(trades) < 100:
            st["done"] = True

    # ---------- loop malam ----------
    async def run_forever(self, notify) -> None:
        self.load_plan()
        log.info("Penarik riset aktif (maks %d request/malam, jendela %s-%s).", self.max_req, *self.window)
        turn = 0
        errors = 0
        while True:
            now = datetime.now(WIB)
            if not self.in_window(now):
                await asyncio.sleep(300)
                continue
            night = self._night(now)
            if self.state["night"] != night:
                prev = self.state["night"]
                if prev and self.state["reported"] != prev:
                    self._report(notify, prev)
                self.state.update(night=night, used=0, stopped="")
                self._auth = None  # muat ulang token cache tiap malam
                errors = 0
                self._save_state()
            if self.state["stopped"] or self.state["used"] >= self.max_req:
                await asyncio.sleep(300)
                continue
            jobs = [("t", self._next_tape()), ("b", self._next_broksum())]
            jobs = [(k, j) for k, j in jobs if j]
            if not jobs:
                if self.state.get("all_done_reported") != "1":
                    self.state["all_done_reported"] = "1"
                    self._save_state()
                    pr = self.progress()
                    notify(f"✅ <b>Data riset lengkap</b> — broksum {pr['bk_done']}/{pr['bk_total']}, "
                           f"pita {pr['t_done']}/{pr['t_total']} ({pr['trades']:,} transaksi).".replace(",", ".")
                           + " Buka sesi Claude untuk analisa.")
                await asyncio.sleep(1800)
                continue
            kind, (s, d) = jobs[turn % len(jobs)]
            turn += 1
            try:
                await asyncio.to_thread(self.step_tape if kind == "t" else self.step_broksum, s, d)
                errors = 0
            except ManualReloginRequired as e:
                self._stop(notify, f"sesi Stockbit habis ({e}). Kirim /settoken, lanjut malam berikutnya")
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                errors += 1
                if code == 429:
                    self._stop(notify, "kena batas request Stockbit (429)")
                elif errors >= MAX_ERR:
                    self._stop(notify, f"{errors} error beruntun (terakhir HTTP {code})")
                else:
                    await asyncio.sleep(30 * errors)
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.warning("Riset %s %s %s gagal: %s", kind, s, d, e)
                if errors >= MAX_ERR:
                    self._stop(notify, f"{errors} error beruntun (terakhir: {e})")
                else:
                    await asyncio.sleep(30 * errors)
            self.state["used"] += 1
            self.state["total_req"] = self.state.get("total_req", 0) + 1
            if self.state["used"] % 50 == 0:
                self._save_state()
            await asyncio.sleep(random.uniform(1.6, 2.4))

    def _stop(self, notify, why: str) -> None:
        self.state["stopped"] = why
        self._save_state()
        log.warning("Penarik riset berhenti malam ini: %s", why)
        notify(f"⏸️ <b>Penarik riset berhenti</b> malam ini: {why}. Progres tersimpan, lanjut otomatis malam berikutnya.")

    def _report(self, notify, night: str) -> None:
        pr = self.progress()
        self.state["reported"] = night
        left_req = (pr["bk_total"] - pr["bk_done"]) + max(0, pr["t_total"] - pr["t_done"]) * 66  # pita ±66 req
        eta = max(1, round(left_req / self.max_req))
        notify(f"🌙 <b>Penarik riset</b> malam {night}: {self.state['used']} request"
               + (f" · berhenti: {self.state['stopped']}" if self.state["stopped"] else "")
               + f"\nBroksum {pr['bk_done']}/{pr['bk_total']} · pita {pr['t_done']}/{pr['t_total']} "
               f"({pr['trades']:,} transaksi)".replace(",", ".")
               + f"\nPerkiraan sisa ±{eta} malam.")
        self._save_state()

    def status_text(self) -> str:
        pr = self.progress()
        p = self.load_plan()
        return (f"🔬 <b>Penarik riset</b> · maks {self.max_req}/malam · jendela {self.window[0]}–{self.window[1]}\n"
                f"Malam ini: {self.state['used']} request" + (f" · berhenti: {self.state['stopped']}" if self.state["stopped"] else "")
                + f"\nBroksum mundur: {pr['bk_done']}/{pr['bk_total']} saham-hari ({len(p['broksum_days'])} hari)"
                + f"\nPita transaksi: {pr['t_done']}/{pr['t_total']} saham-hari · {pr['trades']:,} transaksi".replace(",", ".")
                + f"\nSaham pita: {', '.join(p['tape_syms'])}")
