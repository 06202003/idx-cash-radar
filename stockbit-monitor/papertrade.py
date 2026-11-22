"""Paper trading (KERTAS SAJA — tidak ada uang, tidak ada order ke broker mana pun).

Forward test semua aturan yang bisa diuji maju. Aturan DIKUNCI per versi (RULES_VERSION,
START_DAY): sinyal hanya dicatat untuk hari >= START_DAY, dan setiap perubahan aturan harus
menaikkan versi (hitungan versi lama berhenti, versi baru mulai dari nol).

Kejujuran pencatatan:
- Sinyal hari t dicatat SORE hari t (dari tabel bukti, data s.d. t) dengan status "pending",
  SEBELUM harga hari t+1 ada. Baru sore-sore berikutnya posisi diisi & ditutup dari harga harian.
- Harga masuk = open t+1 + 1 tick (beli di offer), keluar = close t+h − 1 tick (jual di bid).
  Fee beli 0,15%, jual 0,25% (termasuk PPh 0,1%). Kalau open t+1 >= close t +19% (ARA/gap
  limit) posisi dianggap TIDAK TERISI.
- Aturan "SHORT" = kertas saja untuk mengukur sinyal negatif (ritel praktis tidak bisa short):
  hasil = kebalikan harga, tanpa biaya pinjam.
- Watchlist intraday: masuk di harga saat masuk pantauan + 1 tick, keluar di harga saat keluar
  pantauan − 1 tick (atau close hari itu kalau masih dipantau). Harga dari running trade yang
  teramati, jadi tetap agak optimis.

Aturan v1 (dari HIPOTESIS.md + studi kondisi IHSG di market.py):
  T1   uptrend+RSI>70, bukan habis lonjakan volume, IHSG tren naik/samping   LONG 5 hari
  T1c  (kontrol) uptrend+RSI>70 tanpa syarat IHSG                             LONG 5 hari
  (H1/H1c/H2: hanya saham likuid menurut alert & harga >= Rp50 — klarifikasi sebelum mulai)
  H1   alert beli dominan + dijaga (konsentrasi 10h >= 45%)                   LONG 5 hari
  H1c  (kontrol) alert beli dominan + TIDAK dijaga                            LONG 5 hari
  H2   alert beli dominan (semua) — laporan dipisah per tren IHSG             LONG 1 hari
  H3   masuk watchlist + saham uptrend harian                                 LONG 5 hari
  H3c  (kontrol) masuk watchlist + saham downtrend harian                     LONG 5 hari
  H4   broksum adaptif C (penampung utama membuang)                           SHORT kertas 5 hari
  H5   broksum adaptif D, akumulasi mulai SEBELUM harga gerak                 LONG 5 hari
  H5c  (kontrol) D, akumulasi mulai SESUDAH harga gerak                       LONG 5 hari
  H6   tembok bid dicabut (orderbook) di saham pantauan                       SHORT kertas 1 hari
  W    watchlist intraday (masuk/keluar pantauan otomatis)                    LONG intraday
H7 (dijaga × IHSG merah/hijau) bukan aturan trading -> dinilai dari tabel bukti.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import broksum

WIB = ZoneInfo("Asia/Jakarta")
log = logging.getLogger("papertrade")

RULES_VERSION = "v1"
START_DAY = "2026-11-23"
FEE_BUY = 0.0015
FEE_SELL = 0.0025
LIMIT_GAP = 0.19
MIN_PRICE = 50  # di bawah ini 1 tick >= 2% -> spread makan habis (saham gocap)
NOTIONAL = 10_000_000  # Rp per posisi (kertas), cuma buat angka rupiah di laporan

RULES = {
    "T1": ("LONG", 5, "uptrend+RSI>70, IHSG naik/samping"),
    "T1c": ("LONG", 5, "kontrol: uptrend+RSI>70 semua kondisi IHSG"),
    "H1": ("LONG", 5, "alert beli dominan + dijaga"),
    "H1c": ("LONG", 5, "kontrol: alert beli dominan, tidak dijaga"),
    "H2": ("LONG", 1, "alert beli dominan (dipisah per tren IHSG)"),
    "H3": ("LONG", 5, "masuk watchlist + uptrend"),
    "H3c": ("LONG", 5, "kontrol: masuk watchlist + downtrend"),
    "H4": ("SHORT", 5, "penampung utama membuang (C)"),
    "H5": ("LONG", 5, "akumulasi mulai sebelum harga gerak (D)"),
    "H5c": ("LONG", 5, "kontrol: akumulasi mulai sesudah harga gerak (D)"),
    "H6": ("SHORT", 1, "tembok bid dicabut"),
    "W": ("LONG", 0, "watchlist intraday"),
}


def tick(price: float) -> float:
    """Fraksi harga BEI (saham reguler)."""
    if price < 200:
        return 1
    if price < 500:
        return 2
    if price < 2000:
        return 5
    if price < 5000:
        return 10
    return 25


def net_return(side: str, entry: float, exit_: float) -> float:
    """Return bersih setelah fee. Harga entry/exit sudah termasuk 1 tick slippage."""
    if side == "LONG":
        return (exit_ * (1 - FEE_SELL)) / (entry * (1 + FEE_BUY)) - 1
    return (entry * (1 - FEE_SELL)) / (exit_ * (1 + FEE_BUY)) - 1  # short kertas


def signals_for(row: dict) -> list[str]:
    """Aturan v1 -> daftar kode aturan yang menyala untuk 1 baris tabel bukti."""
    out = []
    tr, rsi, vr, ret = row.get("trend"), row.get("rsi"), row.get("vr"), row.get("ret")
    if tr == "up" and rsi is not None and rsi > 70 and not (vr is not None and ret is not None and vr >= 3 and ret >= 0.03):
        out.append("T1c")
        if row.get("ihsg_trend") in ("up", "side"):
            out.append("T1")
    tradable = (row.get("close") or 0) >= MIN_PRICE
    if row.get("buy_dom") and row.get("liquid") is True and tradable:
        out.append("H2")
        conc = row.get("conc10")
        if conc is not None:
            out.append("H1" if conc >= broksum.CONC_HIGH else "H1c")
    if row.get("watch_enter"):
        if tr == "up":
            out.append("H3")
        elif tr == "down":
            out.append("H3c")
    adapt = row.get("adapt") or []
    if "C" in adapt:
        out.append("H4")
    if "D" in adapt and "d_early" in row:
        out.append("H5" if row["d_early"] else "H5c")
    if row.get("wall_bid"):
        out.append("H6")
    return out


class PaperBook:
    def __init__(self, data_dir: str, bars, is_trading_day):
        self.dir = os.path.join(data_dir, "paper")
        os.makedirs(self.dir, exist_ok=True)
        self.data_dir = data_dir
        self.ledger_path = os.path.join(self.dir, "ledger.jsonl")
        self.bars = bars
        self.is_trading_day = is_trading_day

    # ---------- buku ----------
    def _load(self) -> list[dict]:
        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                return [json.loads(x) for x in f if x.strip()]
        except OSError:
            return []

    def _save(self, rows: list[dict]) -> None:
        tmp = f"{self.ledger_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, self.ledger_path)

    # ---------- 1) catat sinyal hari ini (sebelum hasil diketahui) ----------
    def record_signals(self, day: str, ledger: list[dict]) -> int:
        if day < START_DAY:
            return 0
        have = {(r["day"], r["sym"], r["rule"]) for r in ledger}
        path = os.path.join(self.data_dir, "evidence", f"{day}.jsonl")
        try:
            with open(path, encoding="utf-8") as f:
                rows = [json.loads(x) for x in f if x.strip()]
        except OSError:
            return 0
        n = 0
        now = datetime.now(WIB).isoformat(timespec="seconds")
        for row in rows:
            for rule in signals_for(row):
                if rule == "W" or (day, row["sym"], rule) in have:
                    continue
                side, hold, _ = RULES[rule]
                ledger.append({"v": RULES_VERSION, "rule": rule, "day": day, "sym": row["sym"], "side": side,
                               "hold": hold, "status": "pending", "recorded_at": now,
                               "ihsg_trend": row.get("ihsg_trend"), "signal_close": row.get("close")})
                n += 1
        return n

    # ---------- 2) watchlist intraday ----------
    def record_watch(self, day: str, ledger: list[dict]) -> int:
        if day < START_DAY:
            return 0
        path = os.path.join(self.data_dir, f"watch-{day[:7]}.jsonl")
        try:
            with open(path, encoding="utf-8") as f:
                evs = [json.loads(x) for x in f if x.strip()]
        except OSError:
            return 0
        have = {(r["day"], r["sym"], r.get("entry_ts")) for r in ledger if r["rule"] == "W"}
        opened: dict[str, dict] = {}
        n = 0
        for e in evs:
            if datetime.fromtimestamp(e["ts"], tz=WIB).strftime("%Y-%m-%d") != day:
                continue
            if e["event"] == "enter":
                opened[e["stock"]] = e
            elif e["event"] == "exit" and e["stock"] in opened:
                en = opened.pop(e["stock"])
                if (day, e["stock"], en["ts"]) in have:
                    continue
                ledger.append(self._watch_trade(day, en, e["price"], e["ts"], e.get("reason", "")))
                n += 1
        for sym, en in opened.items():  # masih dipantau saat tutup -> keluar di close hari itu
            if (day, sym, en["ts"]) in have:
                continue
            b = {x[0]: x for x in self._bars(sym)}
            if day not in b:
                continue  # bar harian belum ada; dicoba lagi besok sore
            ledger.append(self._watch_trade(day, en, b[day][4], None, "masih dipantau saat tutup"))
            n += 1
        return n

    def _watch_trade(self, day, en, exit_px, exit_ts, reason) -> dict:
        entry = en["price"] + tick(en["price"])
        exit_ = exit_px - tick(exit_px)
        return {"v": RULES_VERSION, "rule": "W", "day": day, "sym": en["stock"], "side": "LONG", "hold": 0,
                "status": "closed", "entry_ts": en["ts"], "exit_ts": exit_ts, "entry": entry, "exit": exit_,
                "ret": round(net_return("LONG", entry, exit_), 5), "ihsg_trend": en.get("ihsg_trend"),
                "exit_reason": reason[:60], "exit_day": day}

    # ---------- 3) isi & tutup posisi harian ----------
    def _bars(self, sym: str) -> list:
        try:
            return self.bars.get(sym)
        except Exception:  # noqa: BLE001
            return []

    def settle(self, ledger: list[dict]) -> int:
        n = 0
        for r in ledger:
            if r["status"] not in ("pending", "open"):
                continue
            b = self._bars(r["sym"])
            idx = next((i for i, x in enumerate(b) if x[0] == r["day"]), None)
            if idx is None or idx + 1 >= len(b):
                continue
            if r["status"] == "pending":
                o, prev_c = b[idx + 1][1], b[idx][4]
                if o <= 0:
                    continue
                if prev_c and o / prev_c - 1 >= LIMIT_GAP and r["side"] == "LONG":
                    r.update(status="unfilled", note="buka di ARA/gap limit")
                    n += 1
                    continue
                r["entry"] = o + tick(o) if r["side"] == "LONG" else o - tick(o)
                r["entry_day"] = b[idx + 1][0]
                r["status"] = "open"
                n += 1
            j = idx + r["hold"]
            if r["status"] == "open" and j < len(b):
                c = b[j][4]
                r["exit"] = c - tick(c) if r["side"] == "LONG" else c + tick(c)
                r["exit_day"] = b[j][0]
                o_, h_, l_ = b[j][1], b[j][2], b[j][3]
                if r["side"] == "LONG" and o_ == h_ == l_ == c and c < b[j - 1][4]:
                    # ARB terkunci (harga satu titik seharian, turun): jual nyata kemungkinan TIDAK terisi
                    r["note"] = "ARB terkunci saat keluar — hasil nyata bisa lebih buruk"
                r["ret"] = round(net_return(r["side"], r["entry"], r["exit"]), 5)
                r["status"] = "closed"
                n += 1
        return n

    def run_daily(self, day: str) -> str:
        ledger = self._load()
        a = self.record_signals(day, ledger)
        w = self.record_watch(day, ledger)
        s = self.settle(ledger)
        self._save(ledger)
        msg = f"paper {RULES_VERSION}: {a} sinyal baru, {w} trade watchlist, {s} posisi diperbarui"
        log.info(msg)
        return msg

    # ---------- laporan ----------
    def _ihsg_ret(self, entry_day: str, exit_day: str) -> float | None:
        try:
            with open(os.path.join(self.data_dir, "daily", "_JKSE.json"), encoding="utf-8") as f:
                closes = dict((d, c) for d, c in json.load(f))
        except (OSError, json.JSONDecodeError):
            return None
        days = sorted(closes)
        prev = [d for d in days if d < entry_day]
        if not prev or exit_day not in closes:
            return None
        return closes[exit_day] / closes[prev[-1]] - 1  # kasar: close sebelum masuk -> close keluar

    def report(self, version: str = RULES_VERSION) -> str:
        ledger = [r for r in self._load() if r.get("v") == version]
        lines = [f"🧪 <b>Paper trading {version}</b> (kertas, tanpa uang) · mulai {START_DAY}"]
        if not ledger:
            return lines[0] + "\nBelum ada sinyal."
        by = defaultdict(list)
        for r in ledger:
            by[r["rule"]].append(r)
        pend = sum(1 for r in ledger if r["status"] in ("pending", "open"))
        unf = sum(1 for r in ledger if r["status"] == "unfilled")
        locked = sum(1 for r in ledger if r.get("note", "").startswith("ARB terkunci"))
        lines.append(f"{len(ledger)} sinyal · {pend} masih berjalan · {unf} tidak terisi (ARA)"
                     + (f" · {locked} keluar saat ARB terkunci (hasil nyata bisa lebih buruk)" if locked else ""))
        for rule in RULES:
            rs = [r for r in by.get(rule, []) if r["status"] == "closed"]
            if not rs and not by.get(rule):
                continue
            side, hold, desc = RULES[rule]
            head = f"\n<b>{rule}</b> {desc} ({side}{'' if hold == 0 else f' {hold}h'})"
            if not rs:
                lines.append(head + f"\n  belum ada yang selesai ({len(by[rule])} berjalan)")
                continue
            rets = [r["ret"] for r in rs]
            days = defaultdict(list)
            for r in rs:
                days[r["day"]].append(r["ret"])
            dm = [statistics.fmean(v) for v in days.values()]
            t = (statistics.fmean(dm) / (statistics.stdev(dm) / len(dm) ** 0.5)
                 if len(dm) > 2 and statistics.stdev(dm) > 0 else None)
            win = sum(x > 0 for x in rets) / len(rets)
            ih = [x for x in (self._ihsg_ret(r.get("entry_day", r["day"]), r["exit_day"]) for r in rs
                              if r.get("exit_day")) if x is not None]
            line = (f"  {len(rs)} trade / {len(dm)} hari · rata2 bersih {statistics.fmean(rets) * 100:+.2f}% · "
                    f"menang {win * 100:.0f}%" + (f" · t {t:+.1f}" if t is not None else ""))
            if ih and side == "LONG" and hold > 0:
                line += f" · IHSG periode sama {statistics.fmean(ih) * 100:+.2f}%"
            lines.append(head + "\n" + line.replace(".", ","))
            if rule == "H2":
                for reg in ("up", "side", "down"):
                    sub = [r["ret"] for r in rs if r.get("ihsg_trend") == reg]
                    if sub:
                        lines.append(f"  · IHSG {reg}: {len(sub)} trade, {statistics.fmean(sub) * 100:+.2f}%".replace(".", ","))
        lines.append("\n<i>Sesudah fee (0,15% beli, 0,25% jual) & 1 tick slippage. SHORT = kertas saja. "
                     "Nilai lolos/gagal hanya sesuai aturan HIPOTESIS.md (≥20 hari, ≥100 kejadian, |t|≥2, "
                     "konsisten 2 paruh).</i>")
        return "\n".join(lines)
