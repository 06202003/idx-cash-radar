"""Pengukuran: seberapa lengkap running trade yang tertangkap bot (buat rencana analisa
"gaya main" per saham). Ringan, cuma mencatat; hasil ke data/measure-YYYY-MM-DD.json +
1 ringkasan Telegram setelah tutup.

Tiga pengukuran:
1. Per polling: berapa transaksi baru vs yang sudah pernah dilihat. Polling yang 80 item-nya
   SEMUA baru (tidak ada yang tumpang tindih dengan polling sebelumnya) = ada transaksi
   yang terlewat di antara 2 polling.
2. Global: `trade_number` ternyata BERURUTAN SATU PASAR (dicek 2026-11-22), jadi
   kelengkapan = transaksi unik teramati / (nomor terbesar - terkecil + 1).
3. Per saham: transaksi teramati vs `frequency` (jumlah transaksi harian) dari endpoint
   orderbook, ditarik sekali setelah tutup untuk sampel saham.

Fakta (dicek 2026-11-22): endpoint running trade bisa difilter `symbols=KODE` (ulang
parameternya untuk beberapa saham), limit maks 100, dan paging mundur pakai
`trade_number=<nomor terkecil sebelumnya>`. Pita lengkap MPMX 20 Nov = 728 transaksi,
persis sama dengan frequency & volume resmi -> pita lengkap per saham bisa ditarik
setelah tutup. Probe filter di bawah disimpan buat cek ulang manual saja.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from stockbit_auth import COMMON_HEADERS
from stockbit_running_trade import URL as RT_URL

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("measure")

PROBE_PARAMS = ("code", "symbol", "symbols", "codes", "stock", "stock_code")
SAMPLE_TOP = 15  # saham teramai (menurut bot) yang dicek frequency-nya
SAMPLE_RANDOM = 10  # + sampel acak dari universe


def _num(x) -> float:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


class CoverageMeter:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.context_fn = None  # -> dict kondisi IHSG, diisi monitor.py (jangan di _reset)
        self._reset("")

    def _reset(self, day: str) -> None:
        self.day = day
        self.polls = 0
        self.polls_all_new = 0  # polling tanpa tumpang tindih -> ada yang terlewat
        self.items = 0
        self.new_items = 0
        self.per_stock: dict[str, int] = defaultdict(int)
        self.tn_min = None
        self.tn_max = None
        self.n_unique = 0
        self.probe_done = True  # sudah terjawab 2026-11-22 (symbols=KODE), tidak diprobe otomatis lagi
        self.probe_result = None
        self.report_done = False

    def _roll(self) -> str:
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self._reset(today)
        return today

    # ---------- dipanggil dari loop polling ----------
    def on_poll(self, n_items: int, n_new: int) -> None:
        self._roll()
        self.polls += 1
        self.items += n_items
        self.new_items += n_new
        if n_items > 0 and n_new == n_items:
            self.polls_all_new += 1

    def on_trade(self, item: dict) -> None:
        """Dipanggil sekali per transaksi BARU (sudah di-dedupe di loop polling)."""
        self.per_stock[item.get("code", "?")] += 1
        tn = _num(item.get("trade_number"))
        if tn > 0:
            self.n_unique += 1
            self.tn_min = tn if self.tn_min is None else min(self.tn_min, tn)
            self.tn_max = tn if self.tn_max is None else max(self.tn_max, tn)

    # ---------- probe filter per saham (sekali sehari, tengah sesi) ----------
    def probe_filter(self, token: str, sym: str) -> list[dict]:
        headers = dict(COMMON_HEADERS)
        headers["Authorization"] = f"Bearer {token}"
        out = []
        for p in PROBE_PARAMS:
            params = {"sort": "DESC", "limit": 50, "order_by": "RUNNING_TRADE_ORDER_BY_TIME", p: sym}
            try:
                r = requests.get(RT_URL, headers=headers, params=params, timeout=15)
                trades = (r.json().get("data") or {}).get("running_trade") or [] if r.status_code == 200 else []
                codes = {t.get("code") for t in trades}
                out.append({"param": p, "http": r.status_code, "n": len(trades),
                            "only_sym": bool(trades) and codes == {sym}, "n_codes": len(codes)})
            except Exception as e:  # noqa: BLE001
                out.append({"param": p, "error": str(e)[:200]})
            time.sleep(random.uniform(2, 4))
        self.probe_done = True
        return out

    # ---------- laporan setelah tutup ----------
    def build_report(self, auth, orderbook_path: str, universe: list[str], probe: list[dict] | None) -> tuple[dict, str]:
        ranked = sorted(self.per_stock.items(), key=lambda kv: -kv[1])
        sample = [s for s, _ in ranked[:SAMPLE_TOP]]
        rest = [s for s in universe if s not in sample]
        sample += random.sample(rest, min(SAMPLE_RANDOM, len(rest)))
        rows = []
        for sym in sample:
            freq = None
            if orderbook_path:
                try:
                    r = auth._get(orderbook_path.format(code=sym), auth.token.access_token)
                    if r.status_code == 200:
                        freq = _num((r.json().get("data") or {}).get("frequency"))
                except Exception as e:  # noqa: BLE001
                    log.warning("frequency %s gagal: %s", sym, e)
                time.sleep(random.uniform(1.0, 1.8))
            n = self.per_stock.get(sym, 0)
            rows.append({"sym": sym, "seen": n, "frequency": freq,
                         "cov_freq": round(n / freq, 3) if freq else None})
        covs = sorted(r["cov_freq"] for r in rows if r["cov_freq"] is not None)
        top_covs = sorted(r["cov_freq"] for r in rows[:SAMPLE_TOP] if r["cov_freq"] is not None)
        span = (self.tn_max - self.tn_min + 1) if self.tn_min is not None else None
        rep = {
            "day": self.day, "polls": self.polls, "polls_all_new": self.polls_all_new,
            "gap_poll_frac": round(self.polls_all_new / self.polls, 3) if self.polls else None,
            "items": self.items, "new_items": self.new_items,
            "stocks_seen": len(self.per_stock), "trades_seen": sum(self.per_stock.values()),
            "tn_min": self.tn_min, "tn_max": self.tn_max, "tn_span": span,
            "cov_global": round(self.n_unique / span, 3) if span else None,
            "median_cov": covs[len(covs) // 2] if covs else None,
            "median_cov_top": top_covs[len(top_covs) // 2] if top_covs else None,
            "probe": probe, "sample": rows, "market": self.context_fn() if self.context_fn else {},
        }
        path = os.path.join(self.data_dir, f"measure-{self.day}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        self.report_done = True

        def pct(x):
            return "-" if x is None else f"{x * 100:.0f}%"
        lines = [f"📏 <b>Pengukuran running trade</b> · {self.day}",
                 f"Polling {self.polls}x · {pct(rep['gap_poll_frac'])} polling ada transaksi terlewat",
                 f"Tertangkap {rep['trades_seen']:,} transaksi di {rep['stocks_seen']} saham".replace(",", "."),
                 f"Kelengkapan vs frequency: median {pct(rep['median_cov'])} "
                 f"(saham teramai {pct(rep['median_cov_top'])}, sampel {len(rows)} saham)",
                 f"Kelengkapan global (celah trade_number): {pct(rep['cov_global'])} "
                 f"dari ±{(span or 0):,.0f} transaksi pasar".replace(",", ".")]
        if probe:
            ok = [p["param"] for p in probe if p.get("only_sym")]
            lines.append("Filter per saham: " + (f"BISA lewat parameter <code>{', '.join(ok)}</code>" if ok
                                                 else "tidak ada parameter yang berhasil"))
        lines.append(f"<i>Detail: data/measure-{self.day}.json</i>")
        return rep, "\n".join(lines)
