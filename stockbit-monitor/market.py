"""Konteks IHSG: real-time (Stockbit, tiap ~5 menit selama sesi) + kondisi harian (Yahoo ^JKSE).

Dipakai untuk:
- 1 baris IHSG di tiap alert lonjakan & pesan masuk watchlist
- label kondisi pasar di SEMUA log (alerts, watch, obdetect, broksum-adaptive, measure)
  supaya semua analisa bisa dipisah per kondisi pasar belakangan
- ringkasan kondisi pasar di rekap sore

Endpoint: /company-price-feed/v2/orderbook/companies/IHSG (sama dengan orderbook saham;
isinya lastprice, percentage_change, value = nilai transaksi pasar, fnet = net asing pasar).

Studi kondisi pasar (2026-11-22; harian Feb 2025 - Nov 2026, 216 saham likuid, beli open
besok, relatif rata-rata 216 saham, t-stat per hari, hari ARA/gap >=19% dibuang, sebelum
biaya; universe = saham likuid SEKARANG jadi ada bias survivorship):
  uptrend+RSI>70 (5 hari): IHSG tren naik +2,5% (t 8,3) | samping +2,2% (t 3,5) |
                           IHSG tren turun +1,1% (t 1,2, TIDAK signifikan; mentah -0,1%)
  downtrend saham (5 hari): IHSG naik -1,1% (t -6,7) | IHSG turun -0,2% (t -2,0; mentah -1,2%)
  habis lonjakan volume (besok): IHSG hari hijau -0,5% | merah -1,0% (mentah -1,3%)
Konsisten di paruh 2025 dan 2026.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("market")

IHSG_PATH = "/company-price-feed/v2/orderbook/companies/IHSG"
YAHOO_JKSE = "https://query1.finance.yahoo.com/v8/finance/chart/%5EJKSE?interval=1d&range=1y"
TREND_WORD = {"up": "tren naik", "down": "tren turun", "side": "tren samping"}


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _rp(v: float) -> str:
    a = abs(v)
    s = f"Rp{a / 1e12:.1f} T" if a >= 1e12 else f"Rp{a / 1e9:.0f} M" if a >= 1e9 else f"Rp{a / 1e6:.0f} jt"
    return ("−" if v < 0 else "") + s.replace(".", ",")


def _pct(v: float) -> str:
    return f"{v:+.1f}%".replace(".", ",").replace("-", "−")


class MarketContext:
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "daily", "_JKSE.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.day = ""
        self.series: deque = deque(maxlen=200)  # (ts, last, pct, value, fnet)
        self._regime_day = ""
        self._regime: dict | None = None

    # ---------- kondisi harian (dari bar yang sudah jadi, sampai kemarin) ----------
    def _daily_bars(self) -> list:
        try:
            if time.time() - os.path.getmtime(self.path) < 6 * 3600:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        try:
            r = requests.get(YAHOO_JKSE, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}, timeout=20)
            d = r.json()["chart"]["result"][0]
            q = d["indicators"]["quote"][0]
            bars = [[datetime.fromtimestamp(t, tz=WIB).strftime("%Y-%m-%d"), c]
                    for t, c in zip(d["timestamp"], q["close"]) if c]
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(bars, f)
            os.replace(tmp, self.path)
            return bars
        except Exception as e:  # noqa: BLE001
            log.warning("Gagal ambil IHSG harian: %s", e)
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return []

    def regime(self, before_day: str | None = None) -> dict | None:
        """Tren IHSG dari close sampai SEBELUM `before_day` (default hari ini): up/side/down."""
        day = before_day or datetime.now(WIB).strftime("%Y-%m-%d")
        if self._regime_day == day and self._regime is not None:
            return self._regime
        closes = [c for d, c in self._daily_bars() if d < day]
        if len(closes) < 50:
            return None
        c, ma20, ma50 = closes[-1], sum(closes[-20:]) / 20, sum(closes[-50:]) / 50
        tr = "up" if c > ma20 > ma50 else "down" if c < ma20 < ma50 else "side"
        self._regime_day, self._regime = day, {"trend": tr, "close": c, "ma20": ma20, "ma50": ma50}
        return self._regime

    # ---------- real-time ----------
    def poll(self, auth) -> None:
        r = auth._get(IHSG_PATH, auth.token.access_token)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        d = r.json().get("data") or {}
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self.day = today
            self.series.clear()
        self.series.append((time.time(), _num(d.get("lastprice")), _num(d.get("percentage_change")),
                            _num(d.get("value")), _num(d.get("fnet"))))

    def snapshot(self) -> dict:
        """Label kondisi pasar sekarang, buat ditempel ke log. Selalu dict (bisa sebagian kosong)."""
        out = {}
        reg = self.regime()
        if reg:
            out["ihsg_trend"] = reg["trend"]
        if self.series and self.day == datetime.now(WIB).strftime("%Y-%m-%d"):
            ts, last, pct, value, fnet = self.series[-1]
            out.update({"ihsg_pct": pct, "ihsg_fnet": fnet})
            past = [x for x in self.series if ts - x[0] >= 25 * 60]
            if past and past[-1][1] and last:
                out["ihsg_30m"] = round((last / past[-1][1] - 1) * 100, 2)
        return out

    def line(self) -> str:
        """1 baris buat alert: '🌐 IHSG −0,9% · 30 mnt −0,2% · tren turun · asing −Rp855 M'."""
        s = self.snapshot()
        parts = []
        if s.get("ihsg_pct") is not None:
            parts.append(f"IHSG {_pct(s['ihsg_pct'])}")
        if s.get("ihsg_30m") is not None:
            parts.append(f"30 mnt {_pct(s['ihsg_30m'])}")
        if s.get("ihsg_trend"):
            parts.append(TREND_WORD[s["ihsg_trend"]])
        if s.get("ihsg_fnet") is not None:
            parts.append(f"asing {_rp(s['ihsg_fnet'])}")
        return ("🌐 " + " · ".join(parts)) if parts else ""

    def regime_note(self) -> str:
        """Catatan aturan yang dipengaruhi kondisi pasar (hasil studi di docstring)."""
        reg = self.regime()
        if not reg:
            return ""
        if reg["trend"] == "down":
            return ("IHSG tren turun: sinyal uptrend+RSI>70 historis TIDAK signifikan di kondisi ini "
                    "(mentah −0,1% per 5 hari). Saham downtrend mentah −1,2% per 5 hari.")
        if reg["trend"] == "up":
            return "IHSG tren naik: uptrend+RSI>70 historis paling kuat di kondisi ini (+2,5% vs pasar per 5 hari)."
        return "IHSG tren samping: uptrend+RSI>70 historis +2,2% vs pasar per 5 hari."

    def evening_summary(self) -> str:
        s = self.snapshot()
        reg = self.regime(datetime.now(WIB).strftime("%Y-%m-%d"))
        lines = ["🌐 <b>Kondisi pasar</b>"]
        bits = []
        if s.get("ihsg_pct") is not None:
            color = "merah" if s["ihsg_pct"] < -0.5 else "hijau" if s["ihsg_pct"] > 0.5 else "datar"
            bits.append(f"IHSG {_pct(s['ihsg_pct'])} ({color})")
        if s.get("ihsg_fnet") is not None:
            bits.append(f"asing net {_rp(s['ihsg_fnet'])}")
        if reg:
            bits.append(f"{TREND_WORD[reg['trend']]} (close kemarin vs MA20 {reg['ma20']:,.0f} / MA50 {reg['ma50']:,.0f})"
                        .replace(",", "."))
        lines.append(" · ".join(bits) or "data IHSG belum ada")
        note = self.regime_note()
        if note:
            lines.append(f"<i>{note}</i>")
        return "\n".join(lines)
