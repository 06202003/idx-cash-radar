"""Teknikal harian per saham (MA20/MA50, RSI14, high/low 20 hari, volume, ATR) + saran.

Data harga harian dari Yahoo Finance (KODE.JK, gratis, tanpa login -- BUKAN dari Stockbit),
di-cache di data/daily/ biar nggak ditarik berulang-ulang.

Kalimat saran yang ada angka "historis"-nya sudah diuji di 2 tahun data harian (Feb 2025 -
Nov 2026, 216 saham likuid, beli di open besoknya, return relatif pasar, sebelum biaya).
Yang lolos uji cuma tiga: downtrend lanjut jelek, uptrend + RSI>70 lanjut kuat, dan sehari
setelah lonjakan volume naik malah turun. Yang TIDAK lolos ditulis apa adanya (RSI oversold,
breakout, dekat support) biar nggak dikira sinyal. Level support/resisten/ATR itu deskriptif.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("technical")

WIB = ZoneInfo("Asia/Jakarta")
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}.JK?interval=1d&range=1y"
CACHE_TTL_SEC = 4 * 3600
MIN_BARS = 56  # butuh MA50 + sedikit cadangan


class DailyBars:
    """Cache bar harian: memori + data/daily/KODE.json."""

    def __init__(self, base_dir: str):
        self.dir = os.path.join(base_dir, "daily")
        os.makedirs(self.dir, exist_ok=True)
        self._mem: dict[str, tuple[float, list]] = {}

    def _fetch(self, sym: str) -> list:
        resp = requests.get(YAHOO_URL.format(sym=sym), headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
                            timeout=10)
        resp.raise_for_status()
        res = resp.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        bars = []
        for t, o, h, l, c, v in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]):
            if None in (o, h, l, c, v) or v <= 0 or c <= 0:
                continue
            bars.append([datetime.fromtimestamp(t, tz=WIB).strftime("%Y-%m-%d"), o, h, l, c, v])
        return bars

    def get(self, sym: str, max_age: float = CACHE_TTL_SEC) -> list:
        """Bar harian [tanggal, o, h, l, c, volume] urut lama -> baru. [] kalau gagal/nggak ada.
        max_age kecil = paksa ambil baru (dipakai sore hari, biar bar hari ini sudah final)."""
        now = time.time()
        hit = self._mem.get(sym)
        if hit and now - hit[0] < max_age:
            return hit[1]
        path = os.path.join(self.dir, f"{sym}.json")
        try:
            if now - os.path.getmtime(path) < max_age:
                with open(path, encoding="utf-8") as f:
                    bars = json.load(f)
                self._mem[sym] = (os.path.getmtime(path), bars)
                return bars
        except (OSError, json.JSONDecodeError):
            pass
        try:
            bars = self._fetch(sym)
        except Exception as e:  # noqa: BLE001
            log.warning("Gagal ambil harga harian %s: %s", sym, e)
            bars = hit[1] if hit else []
            self._mem[sym] = (now, bars)  # jangan dicoba ulang tiap alert; tunggu cache basi dulu
            return bars
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(bars, f)
        os.replace(tmp, path)
        self._mem[sym] = (now, bars)
        return bars

    def completed(self, sym: str, before_day: str | None = None) -> list:
        """Bar sampai sebelum `before_day` (buat dipakai saat bursa jalan: bar hari ini belum jadi)."""
        bars = self.get(sym)
        return [b for b in bars if b[0] < before_day] if before_day else bars


def indicators(bars: list) -> dict | None:
    n = len(bars)
    if n < MIN_BARS:
        return None
    close = [b[4] for b in bars]
    value = [b[4] * b[5] for b in bars]
    gain = loss = 0.0
    for i in range(1, n):  # RSI Wilder
        ch = close[i] - close[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if i <= 14:
            gain += g / 14
            loss += l / 14
        else:
            gain = (gain * 13 + g) / 14
            loss = (loss * 13 + l) / 14
    tr = [max(bars[i][2] - bars[i][3], abs(bars[i][2] - close[i - 1]), abs(bars[i][3] - close[i - 1]))
          for i in range(n - 14, n)]
    avg_val20 = sum(value[-21:-1]) / 20
    return {
        "day": bars[-1][0],
        "c": close[-1],
        "ret": close[-1] / close[-2] - 1,
        "ma20": sum(close[-20:]) / 20,
        "ma50": sum(close[-50:]) / 50,
        "rsi": 100 - 100 / (1 + gain / loss) if loss > 0 else 100.0,
        "hh20": max(b[2] for b in bars[-21:-1]),  # high/low 20 hari SEBELUM bar terakhir
        "ll20": min(b[3] for b in bars[-21:-1]),
        "vr": value[-1] / avg_val20 if avg_val20 > 0 else 0.0,
        "atr": sum(tr) / 14,
    }


def trend(ind: dict) -> str:
    if ind["c"] > ind["ma20"] > ind["ma50"]:
        return "up"
    if ind["c"] < ind["ma20"] < ind["ma50"]:
        return "down"
    return "side"


def _rp(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def advise(ind: dict) -> list[str]:
    """Saran teknikal lengkap (buat /ta). Baris "ikon Label — penjelasan" = penilaian."""
    t, rsi = trend(ind), ind["rsi"]
    out = []
    if t == "up" and rsi > 70:
        out.append("🚀 Uptrend kuat — RSI di atas 70. Historis +2,5% vs pasar per 5 hari saat IHSG tren naik, "
                   "tapi TIDAK signifikan saat IHSG tren turun (cek baris IHSG); RSI tinggi bukan sinyal jual")
    elif t == "up":
        out.append("📈 Uptrend — di atas MA20 dan MA50. Historis hanya sedikit di atas pasar (+0,3% per 5 hari)")
    elif t == "down":
        out.append("📉 Downtrend — di bawah MA20 dan MA50. Historis −0,5% vs pasar dalam 5 hari, konsisten 2 tahun")
    else:
        out.append("↔️ Sideways — tidak ada edge teruji")
    if ind["vr"] >= 3 and ind["ret"] >= 0.03:
        out.append("⚠️ Habis lonjakan volume — naik 3%+ dengan volume 3x. Historis −0,9% di hari berikutnya")
    if rsi < 30:
        out.append("💤 Oversold — RSI di bawah 30. Pantulan TIDAK teruji (hasil 2 tahun campur)")
    if ind["c"] > ind["hh20"]:
        out.append("🔺 Breakout — tembus high 20 hari. Kelanjutan TIDAK teruji (historis −0,2% besoknya)")
    elif ind["c"] <= ind["ll20"] * 1.03:
        out.append("🔻 Dekat support — di sekitar low 20 hari. Historis −0,5% vs pasar per 5 hari (sering jebol)")
    atr_pct = f"{ind['atr'] / ind['c'] * 100:.1f}".replace(".", ",")
    out += [
        "",
        f"Support {_rp(ind['ll20'])} · Resisten {_rp(ind['hh20'])}",
        f"MA20 {_rp(ind['ma20'])} · MA50 {_rp(ind['ma50'])}",
        f"RSI {rsi:.0f} · ATR {_rp(ind['atr'])} ({atr_pct}% per hari)",
    ]
    return out


def one_line(ind: dict) -> str:
    """Versi 1 baris buat alert, /broksum dan rekap."""
    t, rsi = trend(ind), ind["rsi"]
    head = "uptrend kuat" if t == "up" and rsi > 70 else {"up": "uptrend", "down": "downtrend"}.get(t, "sideways")
    parts = [head, f"RSI {rsi:.0f}", f"support {_rp(ind['ll20'])}", f"resisten {_rp(ind['hh20'])}"]
    if ind["vr"] >= 3 and ind["ret"] >= 0.03:
        parts.append("habis lonjakan volume")
    return " · ".join(parts)


