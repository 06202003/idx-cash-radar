"""Konteks harga per saham + penilaian alert lonjakan.

Alert lonjakan (Z-score) cuma bilang "ada aktivitas nggak biasa". Modul ini nambahin
KONTEKS (harga sudah lari berapa dalam 15 menit, lagi di high/low hari ini, saham
likuid atau nggak) lalu ngasih penilaian berdasar studi 35.305 alert bot ini vs chart
5 menit (16 Sep - 13 Nov 2026, return relatif pasar). Angka di teks penilaian itu
hasil studi tsb -- satu periode (pasar lagi turun), jadi perlakukan sebagai panduan,
bukan kepastian.

Semua harga di sini hasil sampling running trade (bot cuma lihat 80 transaksi terakhir
tiap polling), jadi high/low "hari ini" = yang TERAMATI bot, bisa sedikit beda dari chart.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

PRICE_WINDOW_SEC = 16 * 60  # simpan jejak harga segini lama buat hitung gerak 15 menit
PRE15_MIN_AGE_SEC = 8 * 60  # titik pembanding minimal setua ini, kalau nggak "belum cukup data"
MIN_OBS_FOR_HILO = 10  # high/low baru dianggap bermakna setelah segini transaksi teramati

RUN_PCT = 0.02  # harga dianggap "sudah lari" kalau gerak >= 2% dalam 15 menit
BIG_DAY_PCT = 10.0  # saham sudah naik segini (%) hari ini
KNIFE_DAY_PCT = -5.0  # saham sudah turun segini (%) hari ini

ILLIQUID_ADV_IDR = 1_000_000_000  # rata-rata nilai transaksi harian di bawah ini = tidak likuid
ILLIQUID_PRICE = 50  # harga di bawah ini selalu dianggap tidak likuid


def parse_pct(s) -> float | None:
    """'+2.81%' / '-1,234.50%' -> float persen. None kalau nggak kebaca."""
    try:
        return float(str(s).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def is_liquid(price: float, adv_idr: float | None) -> bool | None:
    """None = belum tahu (belum ada data nilai transaksi harian saham ini)."""
    if 0 < price < ILLIQUID_PRICE:
        return False
    if adv_idr is None:
        return None
    return adv_idr >= ILLIQUID_ADV_IDR


class PriceContext:
    """Jejak harga per saham sepanjang hari (reset tiap ganti hari WIB)."""

    def __init__(self):
        self.day = ""
        self.trail: dict[str, deque] = {}  # stock -> deque[(ts, price)]
        self.hi: dict[str, float] = {}
        self.lo: dict[str, float] = {}
        self.n_obs: dict[str, int] = {}
        self.change: dict[str, float] = {}  # % hari ini, dari transaksi terakhir yang teramati

    def update(self, stock: str, price: float, change_pct: float | None, ts: float) -> None:
        today = datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self.trail, self.hi, self.lo, self.n_obs, self.change = {}, {}, {}, {}, {}
            self.day = today
        if price <= 0:
            return
        dq = self.trail.setdefault(stock, deque())
        while dq and dq[0][0] < ts - PRICE_WINDOW_SEC:
            dq.popleft()
        if not dq or ts - dq[-1][0] >= 10 or dq[-1][1] != price:
            dq.append((ts, price))
        self.hi[stock] = max(self.hi.get(stock, price), price)
        self.lo[stock] = min(self.lo.get(stock, price), price)
        self.n_obs[stock] = self.n_obs.get(stock, 0) + 1
        if change_pct is not None:
            self.change[stock] = change_pct

    def snapshot(self, stock: str, price: float, ts: float) -> dict:
        dq = self.trail.get(stock) or ()
        pre15 = None
        for item_ts, item_px in dq:  # titik tertua yang masih dalam window
            if ts - item_ts <= PRICE_WINDOW_SEC:
                if ts - item_ts >= PRE15_MIN_AGE_SEC and item_px > 0:
                    pre15 = price / item_px - 1
                break
        enough = self.n_obs.get(stock, 0) >= MIN_OBS_FOR_HILO
        hi, lo = self.hi.get(stock), self.lo.get(stock)
        return {
            "pre15": pre15,
            "at_high": bool(enough and hi and price >= hi and hi > lo),
            "at_low": bool(enough and lo and price <= lo and hi > lo),
            "change": self.change.get(stock),
        }


def assess(action: str, snap: dict, liquid: bool | None, repeat_buy: int, repeat_sell: int) -> tuple[str, str]:
    """Return (kode, teks penilaian). Kode dipakai buat log & opsi ALERT_MUTE_CODES."""
    pre, chg = snap.get("pre15"), snap.get("change")
    ran_up = pre is not None and pre >= RUN_PCT
    ran_down = pre is not None and pre <= -RUN_PCT
    illiquid = liquid is False

    if action == "buy":
        if ran_up or snap.get("at_high") or (chg is not None and chg >= BIG_DAY_PCT):
            stat = "−1,1%" if illiquid else "−0,35%"
            return "CHASE", f"⚠️ RAWAN KEJAR — HAKA setelah harga sudah lari. Historis 60 menit kemudian: {stat}"
        if chg is not None and chg <= KNIFE_DAY_PCT and repeat_buy >= 3 and repeat_buy >= 2 * repeat_sell:
            return "KNIFE", "🔪 PISAU JATUH — HAKA berulang di saham yang turun ≥5%. Historis open besok: −1,8%"
        if illiquid:
            return "ILLIQ_BUY", ("🚫 TIDAK LIKUID — lonjakan beli di saham sepi. Historis: −0,5% dalam 60 menit, "
                                 "−2,2% sampai tutup besok")
        return "BUY_PLAIN", "➖ TANPA EDGE — HAKA saja historis tidak berlanjut (−0,1% dalam 60 menit)"

    if ran_up or snap.get("at_high"):
        return "EXIT", "🚪 SINYAL KELUAR — HAKI setelah harga lari. Historis 60 menit kemudian: −0,5% s.d. −0,8%"
    if illiquid:
        return "ILLIQ_SELL", "🚫 TIDAK LIKUID — lonjakan jual di saham sepi. Historis: −0,7% sampai tutup"
    if ran_down or snap.get("at_low"):
        return "SELL_DROP", "➖ TIDAK INFORMATIF — HAKI saat harga turun; pantulan historis ≤0,1% (di bawah biaya)"
    return "SELL_PLAIN", "➖ NETRAL — HAKI tanpa konteks historis ≈ pasar"


def _rp_short(v: float) -> str:
    if v >= 1e12:
        return f"Rp{v / 1e12:.1f} T".replace(".", ",")
    if v >= 1e9:
        return f"Rp{v / 1e9:.1f} M".replace(".", ",")
    if v >= 1e6:
        return f"Rp{v / 1e6:.0f} jt"
    return f"Rp{v / 1e3:.0f} rb"


def format_context(snap: dict, liquid: bool | None, adv_idr: float | None) -> str:
    """Konteks 1 baris: gerak 15 menit, high/low hari ini, likuiditas. "" kalau belum ada data."""
    parts = []
    if snap.get("pre15") is not None:
        parts.append(f"{snap['pre15'] * 100:+.1f}% dlm 15 mnt".replace(".", ","))
    if snap.get("at_high"):
        parts.append("di high hari ini")
    elif snap.get("at_low"):
        parts.append("di low hari ini")
    if liquid is not None:
        if not liquid and adv_idr and adv_idr >= ILLIQUID_ADV_IDR:
            parts.append(f"TIDAK likuid (harga di bawah Rp{ILLIQUID_PRICE})")
        else:
            label = "likuid" if liquid else "TIDAK likuid"
            parts.append(f"{label} {_rp_short(adv_idr)}/hari" if adv_idr else label)
    return " · ".join(parts)


def bold_label(text: str) -> str:
    """'⚠️ RAWAN KEJAR — penjelasan' -> '⚠️ <b>RAWAN KEJAR</b> — penjelasan' (HTML Telegram)."""
    label, sep, desc = text.partition(" — ")
    icon, space, name = label.partition(" ")
    if not sep or not space:
        return text
    return f"{icon} <b>{name}</b> — {desc}"


