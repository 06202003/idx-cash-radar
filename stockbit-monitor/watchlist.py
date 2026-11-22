"""Watchlist OTOMATIS dari running trade: bot sendiri yang milih saham mana yang perlu
dipantau lebih dekat, lalu ngabarin kalau kondisinya berubah.

Alur per saham, per hari (reset tiap ganti hari WIB):
1. MASUK pantauan kalau sejak pagi (atau sejak terakhir keluar) saham itu kena alert
   lonjakan BELI berulang (>= WATCH_MIN_BUY_ALERTS), arahnya konsisten (porsi alert beli
   >= WATCH_MIN_BUY_SHARE), likuid, dan alert pemicunya bukan KNIFE / ILLIQ_BUY.
2. Selama dipantau, tiap transaksi saham itu dilacak: arus beli vs jual (nilai Rp) dalam
   WATCH_FLOW_WINDOW_MIN menit terakhir, harga tertinggi sejak masuk.
3. Kabar yang dikirim:
   - 📈 naik tiap kelipatan WATCH_STEP_PCT dari harga masuk
   - ⚠️ ada lonjakan JUAL (HAKI) di saham yang lagi dipantau
   - 🚪 KELUAR kalau harga turun WATCH_STOP_PCT dari harga masuk, turun WATCH_TRAIL_PCT dari
     puncak sejak masuk, atau arus berbalik (porsi jual >= WATCH_FLIP_SELL_SHARE)
4. Rekap semua saham yang dipantau hari itu dikirim setelah tutup.

PENTING: uji kasar di 16-20 Nov 2026 (5 hari, 6.704 alert) menunjukkan saham yang berulang
kena alert beli rata-rata TIDAK naik sampai tutup (-0,2% s.d. -0,6%). Jadi ini daftar fokus
+ peringatan keluar, BUKAN sinyal beli. Semua kejadian dicatat ke data/watch-YYYY-MM.jsonl
supaya aturannya bisa dievaluasi ulang setelah datanya cukup.
"""
from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("watchlist")

EXCLUDED_ENTRY_CODES = {"KNIFE", "ILLIQ_BUY"}
FLIP_MIN_WATCH_SEC = 10 * 60  # arus berbalik baru dinilai setelah dipantau segini lama
FLIP_MIN_TRADES = 15  # ...dan minimal segini transaksi dalam window arus


def _rp(v: float) -> str:
    return f"Rp{v:,.0f}".replace(",", ".")


def _pct(v: float) -> str:
    return f"{v:+.1f}%".replace(".", ",")


def _hm(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=WIB).strftime("%H:%M")


class AutoWatchlist:
    def __init__(self, data_dir: str, min_buy_alerts: int = 3, min_buy_share: float = 0.7,
                 max_active: int = 10, stop_pct: float = 3.0, trail_pct: float = 3.0,
                 step_pct: float = 2.0, flow_window_min: int = 15, flip_sell_share: float = 0.65,
                 idle_min: int = 60, max_sell_alerts: int = 2):
        self.data_dir = data_dir
        self.state_path = os.path.join(data_dir, "watch_state.json")
        self.min_buy_alerts = min_buy_alerts
        self.min_buy_share = min_buy_share
        self.max_active = max_active
        self.stop_pct = stop_pct
        self.trail_pct = trail_pct
        self.step_pct = step_pct
        self.flow_window_sec = flow_window_min * 60
        self.flip_sell_share = flip_sell_share
        self.idle_sec = idle_min * 60
        self.max_sell_alerts = max_sell_alerts
        self.day = ""
        self.counts: dict[str, dict[str, int]] = {}  # stock -> {"buy","sell"} sejak pagi / sejak keluar
        self.active: dict[str, dict] = {}  # stock -> posisi pantauan
        self.closed: list[dict] = []  # pantauan yang sudah keluar hari ini (buat rekap)
        self.flow: dict[str, deque] = {}  # stock -> deque[(ts, action, value)] -- hanya saham aktif
        self.recap_sent_day = ""
        self.context_fn = None  # -> dict kondisi IHSG, diisi monitor.py
        self.note_fn = None  # -> str catatan kondisi pasar buat pesan masuk pantauan
        self.extra_fn = None  # (saham, harga) -> list baris risiko (ARA/ARB, titik impas)

    # ---------- siklus hari & persistensi ----------
    def _roll_day(self, ts: float) -> None:
        today = datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self.day = today
            self.counts, self.active, self.closed, self.flow = {}, {}, [], {}

    def save_state(self) -> None:
        data = {"day": self.day, "counts": self.counts, "active": self.active,
                "closed": self.closed, "recap_sent_day": self.recap_sent_day}
        tmp = f"{self.state_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.state_path)

    def load_state(self) -> None:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        self.recap_sent_day = data.get("recap_sent_day", "")
        if data.get("day") != datetime.now(WIB).strftime("%Y-%m-%d"):
            return  # state hari lain: buang, mulai bersih
        self.day = data["day"]
        self.counts = data.get("counts", {})
        self.active = data.get("active", {})
        self.closed = data.get("closed", [])
        self.flow = {s: deque() for s in self.active}
        log.info("Watchlist dimuat balik: %d saham aktif.", len(self.active))

    def _ctx(self) -> dict:
        """Label kondisi pasar (market.MarketContext.snapshot) kalau disambungkan."""
        try:
            return self.context_fn() if self.context_fn else {}
        except Exception:  # noqa: BLE001
            return {}

    def _log(self, event: str, stock: str, ts: float, **extra) -> None:
        extra = {**self._ctx(), **extra}
        try:
            path = os.path.join(self.data_dir, f"watch-{datetime.fromtimestamp(ts, tz=WIB).strftime('%Y-%m')}.jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": round(ts), "event": event, "stock": stock, **extra}, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("Gagal catat watch log: %s", e)

    # ---------- input dari monitor ----------
    def on_surge(self, stock: str, action: str, price: float, code: str, liquid: bool | None,
                 ts: float, manual: bool = False) -> list[str]:
        """Dipanggil tiap alert lonjakan (termasuk yang dibisukan). Return pesan yang perlu dikirim."""
        self._roll_day(ts)
        c = self.counts.setdefault(stock, {"buy": 0, "sell": 0})
        if action in c:
            c[action] += 1

        pos = self.active.get(stock)
        if pos is not None:
            if action == "sell":
                pos["sell_alerts"] += 1
                pos["last"] = price
                self._log("sell_alert", stock, ts, price=price, code=code)
                if pos["sell_alerts"] >= self.max_sell_alerts:
                    return [self._exit(stock, ts, f"{pos['sell_alerts']}× lonjakan jual sejak masuk")]
                if pos["sell_alerts"] == 1:
                    gain = (price / pos["entry_price"] - 1) * 100
                    return [f"⚠️ <b>{stock}</b>  ·  lonjakan JUAL di saham pantauan  ·  {_rp(price)} "
                            f"({_pct(gain)} dari masuk)\n<i>{code} · 1 lagi = keluar pantauan</i>"]
                return []
            pos["buy_alerts"] += 1
            pos["last_buy_ts"] = ts
            return []

        if action != "buy" or code in EXCLUDED_ENTRY_CODES or liquid is not True:
            return []
        total = c["buy"] + c["sell"]
        if c["buy"] < self.min_buy_alerts or c["buy"] / total < self.min_buy_share:
            return []
        if len(self.active) >= self.max_active:
            log.info("Watchlist penuh (%d), %s tidak dimasukkan.", self.max_active, stock)
            return []
        return [self._enter(stock, price, ts, code, c["buy"], c["sell"], manual)]

    def _enter(self, stock: str, price: float, ts: float, code: str, n_buy: int, n_sell: int,
               manual: bool) -> str:
        self.active[stock] = {"entry_ts": ts, "entry_price": price, "peak": price, "last": price,
                              "step": 0, "buy_alerts": 0, "sell_alerts": 0, "manual": manual, "last_buy_ts": ts,
                              "reason": "manual" if manual else f"{n_buy} beli/{n_sell} jual"}
        self.flow[stock] = deque()
        self._log("enter", stock, ts, price=price, code=code, buy=n_buy, sell=n_sell, manual=manual)
        why = ("ditambah manual" if manual else
               f"alert beli berulang hari ini: {n_buy} beli · {n_sell} jual (pemicu: {code})")
        note = ""
        try:
            note = self.note_fn() if self.note_fn else ""
        except Exception:  # noqa: BLE001
            pass
        why = f"{why}\n🌐 {note}" if note else why
        try:
            extra = self.extra_fn(stock, price) if self.extra_fn else []
        except Exception:  # noqa: BLE001
            extra = []
        if extra:
            why += "\n" + "\n".join(extra)
        return (f"👁 <b>{stock}</b>  ·  MASUK PANTAUAN  ·  {_rp(price)}\n{why}\n"
                f"Keluar otomatis: −{self.stop_pct:g}% dari masuk, −{self.trail_pct:g}% dari puncak, "
                f"arus berbalik jual, {self.max_sell_alerts}× lonjakan jual, atau {self.idle_sec // 60} mnt "
                f"tanpa lonjakan beli baru.\n<i>Daftar fokus, bukan sinyal beli.</i>")

    def on_trade(self, stock: str, price: float, action: str, value_idr: float, ts: float) -> list[str]:
        """Dipanggil tiap transaksi pasar reguler. Murah: langsung return kalau saham tidak dipantau."""
        pos = self.active.get(stock)
        if pos is None or price <= 0:
            return []
        self._roll_day(ts)
        if stock not in self.active:  # baru ganti hari
            return []
        dq = self.flow.setdefault(stock, deque())
        dq.append((ts, action, value_idr))
        while dq and dq[0][0] < ts - self.flow_window_sec:
            dq.popleft()

        pos["last"] = price
        pos["peak"] = max(pos["peak"], price)
        entry = pos["entry_price"]
        gain = (price / entry - 1) * 100
        from_peak = (price / pos["peak"] - 1) * 100

        if gain <= -self.stop_pct:
            return [self._exit(stock, ts, f"harga {_pct(gain)} dari harga masuk")]
        if pos["peak"] > entry and from_peak <= -self.trail_pct:
            return [self._exit(stock, ts, f"harga {_pct(from_peak)} dari puncak {_rp(pos['peak'])}")]
        if not pos["manual"] and ts - pos.get("last_buy_ts", pos["entry_ts"]) >= self.idle_sec:
            return [self._exit(stock, ts, f"{self.idle_sec // 60} mnt tanpa lonjakan beli baru")]
        if ts - pos["entry_ts"] >= FLIP_MIN_WATCH_SEC and len(dq) >= FLIP_MIN_TRADES:
            buy_v = sum(v for _, a, v in dq if a == "buy")
            sell_v = sum(v for _, a, v in dq if a == "sell")
            if buy_v + sell_v > 0 and sell_v / (buy_v + sell_v) >= self.flip_sell_share:
                share = sell_v / (buy_v + sell_v) * 100
                return [self._exit(stock, ts, f"arus berbalik: {share:.0f}% nilai transaksi "
                                              f"{self.flow_window_sec // 60} mnt terakhir adalah jual")]

        step = int(gain // self.step_pct) if gain > 0 else 0
        if step > pos["step"]:
            pos["step"] = step
            self._log("step", stock, ts, price=price, gain=round(gain, 2))
            return [f"📈 <b>{stock}</b>  ·  {_pct(gain)} dari masuk  ·  {_rp(price)}\n"
                    f"Masuk {_hm(pos['entry_ts'])} di {_rp(entry)}"]
        return []

    def _exit(self, stock: str, ts: float, reason: str) -> str:
        pos = self.active.pop(stock)
        self.flow.pop(stock, None)
        self.counts[stock] = {"buy": 0, "sell": 0}  # masuk lagi hari ini butuh alert beli baru
        gain = (pos["last"] / pos["entry_price"] - 1) * 100
        peak = (pos["peak"] / pos["entry_price"] - 1) * 100
        rec = {**pos, "stock": stock, "exit_ts": ts, "exit_reason": reason}
        self.closed.append(rec)
        self._log("exit", stock, ts, price=pos["last"], gain=round(gain, 2), peak=round(peak, 2), reason=reason)
        return (f"🚪 <b>{stock}</b>  ·  KELUAR PANTAUAN  ·  {_rp(pos['last'])} ({_pct(gain)})\n"
                f"Alasan: {reason}\n"
                f"Dipantau {_hm(pos['entry_ts'])}–{_hm(ts)} · masuk {_rp(pos['entry_price'])} · "
                f"puncak {_pct(peak)}")

    # ---------- perintah manual ----------
    def add_manual(self, stock: str, price: float | None, ts: float) -> str:
        self._roll_day(ts)
        if stock in self.active:
            return f"{stock} sudah dipantau."
        if not price:
            return f"Belum ada transaksi {stock} yang teramati hari ini, coba lagi saat pasar buka."
        return self._enter(stock, price, ts, "MANUAL", 0, 0, True)

    def remove(self, stock: str, ts: float) -> str:
        if stock not in self.active:
            return f"{stock} tidak ada di pantauan."
        return self._exit(stock, ts, "dihapus manual")

    # ---------- tampilan ----------
    def format_list(self, ts: float) -> str:
        self._roll_day(ts)
        if not self.active:
            lines = ["👁 <b>Pantauan otomatis</b>: kosong saat ini."]
        else:
            lines = [f"👁 <b>Pantauan otomatis</b> ({len(self.active)}/{self.max_active})"]
            for s, p in sorted(self.active.items(), key=lambda kv: kv[1]["entry_ts"]):
                gain = (p["last"] / p["entry_price"] - 1) * 100
                peak = (p["peak"] / p["entry_price"] - 1) * 100
                lines.append(f"• <b>{s}</b> {_rp(p['last'])} {_pct(gain)} · puncak {_pct(peak)} · "
                             f"masuk {_hm(p['entry_ts'])} ({p['reason']})")
        if self.closed:
            lines.append(f"\nSudah keluar hari ini: {len(self.closed)} saham (detail di rekap sore).")
        lines.append(f"\n<i>Syarat masuk: ≥{self.min_buy_alerts} alert beli, porsi beli ≥"
                     f"{self.min_buy_share * 100:.0f}%, likuid. Daftar fokus, bukan sinyal beli.</i>")
        return "\n".join(lines)

    def format_recap(self) -> str | None:
        items = [(r["stock"], r, r.get("exit_reason", "")) for r in self.closed]
        items += [(s, p, "masih dipantau saat tutup") for s, p in self.active.items()]
        if not items:
            return None
        items.sort(key=lambda x: x[1]["entry_ts"])
        lines = [f"📋 <b>Rekap pantauan otomatis</b> · {self.day}"]
        gains = []
        for s, p, why in items:
            gain = (p["last"] / p["entry_price"] - 1) * 100
            peak = (p["peak"] / p["entry_price"] - 1) * 100
            gains.append(gain)
            lines.append(f"• <b>{s}</b> {_hm(p['entry_ts'])} {_rp(p['entry_price'])} → {_rp(p['last'])} "
                         f"{_pct(gain)} (puncak {_pct(peak)}) — {why}")
        avg = sum(gains) / len(gains)
        naik = sum(g > 0 for g in gains)
        lines.append(f"\nRata-rata {_pct(avg)} · {naik}/{len(gains)} berakhir naik (sebelum biaya).")
        return "\n".join(lines)
