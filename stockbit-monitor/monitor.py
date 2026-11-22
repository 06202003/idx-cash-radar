"""Monitor running trade seluruh IHSG (via Stockbit, API tidak resmi, REST polling)
dan kirim alert ke Telegram kalau ada lonjakan aktivitas nggak wajar per saham
(Z-score, threshold otomatis beda-beda tiap saham -- bukan angka rupiah tetap).

PERINGATAN: memakai endpoint internal Stockbit yang tidak didokumentasikan
secara resmi. Pemakaian di luar aplikasi resmi berisiko melanggar ToS Stockbit.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import random
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import broksum
import broksum_adaptive
import market
import market_context
import measure
import obdetect
import orderbook
import technical
import watchlist
from notify_telegram import TelegramNotifier
from stockbit_auth import ManualReloginRequired, StockbitAuthClient, StockbitAuthError
from stockbit_running_trade import fetch_running_trade
from telegram_listener import TelegramCommandListener

TOKEN_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_cache.json")
SURGE_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "surge_state.json")
SURGE_STATE_SAVE_INTERVAL_SEC = 30
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
EOD_STATE_PATH = os.path.join(DATA_DIR, "eod_state.json")
UNIVERSE_PATH = os.path.join(DATA_DIR, "universe.json")  # daftar saham likuid buat screening sore
NON_REGULAR_BOARDS = {"NG", "TN"}  # pasar nego & tunai -- bukan transaksi pasar reguler
NEGO_ALERT_COOLDOWN_SEC = 60

# sesi Stockbit yang lagi dipakai polling (kalau ada) -- dipakai bareng sama rekap broksum
# & perintah Telegram, biar nggak ada 2 client yang rebutan refresh token.
_live_auth: dict = {"auth": None}
# pendeteksi pola orderbook/algo (diisi di main kalau watchlist nyala) -- dipakai _poll_loop
_pattern: dict = {"det": None}
# pengukuran kelengkapan running trade (lihat measure.py)
_meter: dict = {"m": None}
# konteks IHSG (lihat market.py)
_market: dict = {"m": None}


def get_auth() -> StockbitAuthClient:
    if _live_auth["auth"] is not None:
        return _live_auth["auth"]
    auth = StockbitAuthClient(token_cache_path=TOKEN_CACHE_PATH)
    auth.load_token_cache(TOKEN_CACHE_PATH)
    return auth


def _num(x) -> float:
    """Angka dari API datang sebagai teks berpemisah ribuan ("3,042", "11,404").
    float() polos gagal di situ -- dulu akibatnya semua transaksi dengan harga >= Rp1.000
    ATAU >= 1.000 lot dibuang diam-diam (bot buta ke BBCA/BBRI/dst dan ke order besar)."""
    if isinstance(x, (int, float)):
        return float(x)
    return float(str(x or 0).replace(",", "").strip() or 0)

WIB = ZoneInfo("Asia/Jakarta")
POLL_INTERVAL_SEC = 5  # rata-rata; interval aslinya di-jitter, lihat _poll_delay()
POLL_JITTER_SEC = 1.5  # variasi +/- biar nggak persis 5.000 detik terus-menerus (pola robotik)
SEEN_TTL_SEC = 300  # buang catatan trade_number yang sudah lama biar dict-nya nggak numpuk


def _poll_delay() -> float:
    return max(1.0, random.uniform(POLL_INTERVAL_SEC - POLL_JITTER_SEC, POLL_INTERVAL_SEC + POLL_JITTER_SEC))


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("monitor")


def load_config() -> dict:
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    cfg = {
        "tg_token": os.environ["TELEGRAM_BOT_TOKEN"],
        "tg_chat_id": os.environ["TELEGRAM_CHAT_ID"],
        # deteksi lonjakan aktivitas per saham (Z-score)
        "surge_short_window_sec": int(os.environ.get("SURGE_SHORT_WINDOW_SEC", "180")),
        "surge_long_window_sec": int(os.environ.get("SURGE_LONG_WINDOW_SEC", "1800")),
        "surge_min_buckets": int(os.environ.get("SURGE_MIN_BUCKETS", "5")),
        "surge_z_threshold": float(os.environ.get("SURGE_Z_THRESHOLD", "3.0")),
        "surge_floor_idr": int(os.environ.get("SURGE_FLOOR_IDR", "20000000")),
        "surge_cooldown_sec": int(os.environ.get("SURGE_COOLDOWN_SEC", "240")),
        "surge_min_relative_stddev": float(os.environ.get("SURGE_MIN_RELATIVE_STDDEV", "0.3")),
        # digest ringkasan buy/sell per saham (diadopsi dari bot referensi "Power Buy/Sell")
        "power_bucket_minutes": int(os.environ.get("POWER_BUCKET_MINUTES", "10")),
        "power_digest_every": int(os.environ.get("POWER_DIGEST_EVERY", "5")),
        # konteks harga + penilaian di tiap alert (lihat market_context.py). ALERT_MUTE_CODES:
        # kode penilaian yang TIDAK dikirim ke Telegram (tetap dicatat di log), pisah koma.
        "alert_mute_codes": {c.strip().upper() for c in os.environ.get("ALERT_MUTE_CODES", "").split(",") if c.strip()},
        # alert transaksi pasar nego/crossing tunggal >= sekian rupiah (0 = matikan)
        "nego_alert_idr": float(os.environ.get("NEGO_ALERT_IDR", "10000000000")),
        # rekap broksum sore (lihat broksum.py)
        "eod_recap": os.environ.get("EOD_RECAP", "1") == "1",
        "eod_recap_time": os.environ.get("EOD_RECAP_TIME", "18:00"),
        # screening "dijaga & sepi" ikut dikirim bareng rekap sore (narik broksum semua saham
        # di data/universe.json, ~5 menit). 0 = matikan, tetap bisa manual lewat /akumulasi.
        "acc_screen": os.environ.get("ACC_SCREEN", "1") == "1",
        # baris teknikal harian di tiap alert (harga harian dari Yahoo Finance)
        "alert_technical": os.environ.get("ALERT_TECHNICAL", "1") == "1",
        "eod_recap_min_alerts": int(os.environ.get("EOD_RECAP_MIN_ALERTS", "3")),
        "eod_recap_max_stocks": int(os.environ.get("EOD_RECAP_MAX_STOCKS", "25")),
        # watchlist otomatis dari running trade (lihat watchlist.py). 0 = matikan.
        "watch_auto": os.environ.get("WATCH_AUTO", "1") == "1",
        "watch_min_buy_alerts": int(os.environ.get("WATCH_MIN_BUY_ALERTS", "3")),
        "watch_min_buy_share": float(os.environ.get("WATCH_MIN_BUY_SHARE", "0.7")),
        "watch_max_active": int(os.environ.get("WATCH_MAX_ACTIVE", "10")),
        "watch_stop_pct": float(os.environ.get("WATCH_STOP_PCT", "3")),
        "watch_trail_pct": float(os.environ.get("WATCH_TRAIL_PCT", "3")),
        "watch_step_pct": float(os.environ.get("WATCH_STEP_PCT", "2")),
        "watch_flow_window_min": int(os.environ.get("WATCH_FLOW_WINDOW_MIN", "15")),
        "watch_flip_sell_share": float(os.environ.get("WATCH_FLIP_SELL_SHARE", "0.65")),
        "watch_idle_min": int(os.environ.get("WATCH_IDLE_MIN", "60")),
        "watch_max_sell_alerts": int(os.environ.get("WATCH_MAX_SELL_ALERTS", "2")),
        # pengumpul orderbook saham pantauan (lihat orderbook.py). Kosong = mati.
        "orderbook_path": os.environ.get("ORDERBOOK_PATH", ""),
        "orderbook_interval_sec": float(os.environ.get("ORDERBOOK_INTERVAL_SEC", "10")),
        "orderbook_levels": int(os.environ.get("ORDERBOOK_LEVELS", "10")),
        "orderbook_max_mb_per_day": float(os.environ.get("ORDERBOOK_MAX_MB_PER_DAY", "50")),
        "market_open": os.environ.get("MARKET_OPEN", "08:55"),
        "market_close": os.environ.get("MARKET_CLOSE", "16:00"),
        "active_days": {0, 1, 2, 3, 4},  # Senin=0 .. Jumat=4
    }
    return cfg


# Kalender libur Bursa Efek Indonesia 2026 (sumber: pengumuman resmi IDX No. Peng-00171/BEI.POP/09-2025,
# dicek silang ke berita independen). CATATAN: daftar ini per-tahun -- perlu diupdate tiap
# pergantian tahun. Kalau tanggal sekarang nggak ada di daftar (mis. sudah masuk 2027 dan
# belum diupdate), sistem otomatis fallback ke cek hari kerja biasa (Senin-Jumat) tanpa error.
IDX_HOLIDAYS_2026 = {
    "2026-01-01",  # Tahun Baru 2026 Masehi
    "2026-01-16",  # Isra Mi'raj Nabi Muhammad SAW
    "2026-02-16",  # Cuti Bersama Tahun Baru Imlek
    "2026-02-17",  # Tahun Baru Imlek 2577 Kongzili
    "2026-03-18",  # Cuti Bersama Hari Suci Nyepi
    "2026-03-19",  # Hari Suci Nyepi Tahun Baru Saka 1948
    "2026-03-20",  # Cuti Bersama Idul Fitri
    "2026-03-23",  # Cuti Bersama Idul Fitri
    "2026-03-24",  # Cuti Bersama Idul Fitri
    "2026-04-03",  # Wafat Isa Almasih (Good Friday)
    "2026-05-01",  # Hari Buruh Internasional
    "2026-05-14",  # Kenaikan Yesus Kristus
    "2026-05-15",  # Cuti Bersama Kenaikan Yesus Kristus
    "2026-05-27",  # Iduladha 1447 Hijriah
    "2026-05-28",  # Cuti Bersama Iduladha
    "2026-06-01",  # Hari Lahir Pancasila
    "2026-06-16",  # 1 Muharam Tahun Baru Islam 1448 Hijriah
    "2026-08-17",  # Proklamasi Kemerdekaan RI
    "2026-08-25",  # Maulid Nabi Muhammad SAW
    "2026-12-24",  # Cuti Bersama Natal
    "2026-12-25",  # Kelahiran Yesus Kristus (Natal)
    "2026-12-31",  # Libur Bursa (akhir tahun)
}


def _is_idx_holiday(date_obj) -> bool:
    return date_obj.strftime("%Y-%m-%d") in IDX_HOLIDAYS_2026


def is_trading_day(date_obj) -> bool:
    return date_obj.weekday() < 5 and not _is_idx_holiday(date_obj)


# Jeda istirahat siang resmi IDX per hari kerja (Senin=0 .. Jumat=4).
# Jumat lebih panjang karena jeda sholat Jumat.
LUNCH_BREAK = {
    0: ("12:00", "13:30"),
    1: ("12:00", "13:30"),
    2: ("12:00", "13:30"),
    3: ("12:00", "13:30"),
    4: ("11:30", "14:00"),
}


def _session_starts(cfg: dict, weekday: int) -> list[str]:
    """Daftar jam mulai sesi perdagangan hari itu -- 2 kalau ada jeda istirahat siang."""
    brk = LUNCH_BREAK.get(weekday)
    if not brk:
        return [cfg["market_open"]]
    return [cfg["market_open"], brk[1]]


def is_market_hours(cfg: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(WIB)
    if now.weekday() not in cfg["active_days"]:
        return False
    if _is_idx_holiday(now):
        return False
    open_h, open_m = map(int, cfg["market_open"].split(":"))
    close_h, close_m = map(int, cfg["market_close"].split(":"))
    open_t = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    close_t = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    if not (open_t <= now <= close_t):
        return False
    brk = LUNCH_BREAK.get(now.weekday())
    if brk:
        bh1, bm1 = map(int, brk[0].split(":"))
        bh2, bm2 = map(int, brk[1].split(":"))
        break_start = now.replace(hour=bh1, minute=bm1, second=0, microsecond=0)
        break_end = now.replace(hour=bh2, minute=bm2, second=0, microsecond=0)
        if break_start <= now < break_end:
            return False
    return True


def seconds_until_next_open(cfg: dict, now: datetime | None = None) -> float:
    now = now or datetime.now(WIB)
    for add_days in range(0, 14):  # cukup lebar buat lompatin blok libur panjang (mis. Lebaran)
        candidate_date = now
        if add_days:
            candidate_date = now.fromordinal(now.toordinal() + add_days)
        if candidate_date.weekday() not in cfg["active_days"]:
            continue
        if _is_idx_holiday(candidate_date):
            continue
        for start_str in _session_starts(cfg, candidate_date.weekday()):
            h, m = map(int, start_str.split(":"))
            candidate = candidate_date.replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=WIB)
            if candidate > now:
                return (candidate - now).total_seconds()
    return 3600.0


def _action_label(action: str) -> str:
    if action == "buy":
        return "🟢 BUY (haka)"
    if action == "sell":
        return "🔴 SELL (haki)"
    return "⚪ ?"


def classify_pattern(volumes: list[float]) -> str:
    """Heuristik doang, BUKAN kepastian -- data running trade nggak ada ID
    trader/broker sama sekali, jadi nggak bisa tahu pasti siapa di balik tiap
    transaksi. Cuma bisa nebak dari pola ukurannya:
    - ukuran tiap transaksi mirip-mirip -> ciri khas order 1 aktor yang dipecah
      otomatis oleh algoritma/bot (tiap potongan besarnya seragam)
    - ukuran bervariasi -> lebih mirip aktivitas organik banyak investor beda-beda
    """
    n = len(volumes)
    if n < 2:
        return "belum cukup data"
    mean = sum(volumes) / n
    if mean == 0:
        return "belum cukup data"
    variance = sum((v - mean) ** 2 for v in volumes) / n
    cv = (variance ** 0.5) / mean
    if cv < 0.2:
        return "kemungkinan 1 order terpecah (ukuran tiap transaksi seragam)"
    return "kemungkinan campuran banyak investor (ukuran transaksi bervariasi)"


def _id_num(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def format_surge_alert(stock: str, dominant_action: str, current_sum: float, mean: float, z: float,
                        count: int, short_window_sec: int, volumes: list[float],
                        price: float, change_str: str, repeat_buy: int, repeat_sell: int,
                        verdict: str = "", context: str = "", tech: str = "") -> str:
    """Urutan: saham + arah + harga, lalu penilaian (yang paling perlu dibaca), baru angka pendukung."""
    dot, word = {"buy": ("🟢", "HAKA"), "sell": ("🔴", "HAKI")}.get(dominant_action, ("⚪", "?"))
    mins = short_window_sec // 60
    lines = [f"{dot} <b>{stock}</b>  ·  {word}  ·  Rp{price:,.0f}".replace(",", ".")
             + f" ({change_str.replace('.', ',')})"]
    if verdict:
        lines.append(market_context.bold_label(verdict))
    lines.append("")
    size = f"💰 {market_context._rp_short(current_sum)} dalam {mins} mnt"
    if mean > 0:
        size += f" · {_id_num(current_sum / mean)}x biasanya"
    size += f" · {count} transaksi"
    if "1 order" in classify_pattern(volumes):
        size += " · ukuran seragam (kemungkinan 1 pihak)"
    lines.append(size)
    if context:
        lines.append(f"📍 {context}")
    if tech:
        lines.append(f"📐 {tech}")
    total_repeat = repeat_buy + repeat_sell
    if total_repeat > 1:
        lines.append(f"🔁 Alert ke-{total_repeat} hari ini: {repeat_buy} beli · {repeat_sell} jual")
    return "\n".join(lines)


def format_nego_alert(item: dict, stock: str, price: float, lot: float, value_idr: float) -> str:
    buyer, seller = item.get("buyer") or "?", item.get("seller") or "?"
    return (
        f"🤝 <b>{stock}</b>  ·  NEGO {market_context._rp_short(value_idr)}\n"
        + f"{lot:,.0f} lot @ Rp{price:,.0f}\n".replace(",", ".")
        + f"{buyer} → {seller}\n"
        f"<i>Pasar nego, tidak ikut hitungan lonjakan.</i>"
    )


def log_alert(record: dict) -> None:
    """Catat tiap alert ke data/alerts-YYYY-MM.jsonl (buat evaluasi/riset belakangan)."""
    if _market["m"] is not None:
        record = {**_market["m"].snapshot(), **record}
    try:
        path = os.path.join(DATA_DIR, f"alerts-{datetime.now(WIB).strftime('%Y-%m')}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("Gagal catat alert ke file: %s", e)


class ActivitySurgeDetector:
    """Deteksi 'lonjakan' aktivitas per saham pakai Z-score: bandingkan total nilai
    transaksi window PENDEK saat ini ke distribusi (rata-rata + deviasi standar) dari
    window-window pendek serupa di masa lalu (dalam window PANJANG). Otomatis lebih
    toleran ke saham yang naturalnya naik-turun tajam, lebih sensitif ke saham yang
    biasanya stabil -- nggak perlu data market cap dari luar, dan otomatis nangkep
    order yang dipecah jadi banyak transaksi kecil (karena yang dihitung itu TOTAL
    aktivitas, bukan satu transaksi)."""

    def __init__(self, short_window_sec: int, long_window_sec: int, min_buckets: int,
                 z_threshold: float, floor_value: float, cooldown_sec: int, min_relative_stddev: float = 0.3):
        self.short_window_sec = short_window_sec
        self.long_window_sec = long_window_sec
        self.min_buckets = min_buckets
        self.z_threshold = z_threshold
        self.floor_value = floor_value
        # regularisasi: stddev historis nggak boleh dianggap lebih kecil dari sekian
        # persen rata-ratanya. Tanpa ini, saham yang histori-nya kebetulan SANGAT
        # stabil (variasi hampir nol) bisa dapat Z-score meledak (puluhan-ratusan)
        # cuma dari kenaikan kecil yang sama sekali bukan anomali beneran.
        self.min_relative_stddev = min_relative_stddev
        self.cooldown_sec = cooldown_sec
        # tiap saham: deque[(ts, value, action, volume_lot)]
        self.history: dict[str, deque] = defaultdict(deque)
        self.last_alert: dict[str, float] = {}
        # penghitung berapa kali tiap saham udah alert HARI INI, dipecah per arah (buy/sell)
        # (reset otomatis tiap ganti hari WIB) -- buat nandain saham yang berulang kali
        # muncul DAN apa polanya konsisten satu arah (lebih meyakinkan) atau gonta-ganti.
        self.alert_count: dict[str, dict[str, int]] = {}  # stock -> {"buy": n, "sell": n}
        self.alert_count_date: str = ""

    def _bump_alert_count(self, stock: str, action: str, ts: float) -> dict[str, int]:
        today = datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d")
        if today != self.alert_count_date:
            self.alert_count = {}
            self.alert_count_date = today
        counts = self.alert_count.setdefault(stock, {"buy": 0, "sell": 0})
        counts[action] = counts.get(action, 0) + 1
        return counts
        return self.alert_count[stock]

    def save_state(self, path: str) -> None:
        """Simpan histori ke file supaya baseline nggak hilang total kalau proses
        di-restart (mis. update kode, crash lalu auto-restart systemd)."""
        data = {
            "history": {stock: list(dq) for stock, dq in self.history.items()},
            "last_alert": self.last_alert,
            "alert_count": self.alert_count,
            "alert_count_date": self.alert_count_date,
        }
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)

    def load_state(self, path: str) -> None:
        """Muat balik histori dari file, buang entri yang sudah lebih tua dari
        long_window_sec (biar nggak dianggap 'baru' padahal sudah basi)."""
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Gagal muat surge_state.json, mulai dari kosong: %s", e)
            return

        now = time.time()
        cutoff = now - self.long_window_sec
        restored_stocks = 0
        for stock, entries in data.get("history", {}).items():
            dq = deque(
                (ts, value, action, volume) for ts, value, action, volume in entries if ts >= cutoff
            )
            if dq:
                self.history[stock] = dq
                restored_stocks += 1
        self.last_alert = {k: v for k, v in data.get("last_alert", {}).items() if v >= cutoff}
        # alert_count: dimuat apa adanya -- _bump_alert_count otomatis reset sendiri
        # kalau tanggalnya ternyata bukan hari ini lagi (mis. dimuat pas start pagi hari).
        self.alert_count = data.get("alert_count", {})
        self.alert_count_date = data.get("alert_count_date", "")
        log.info("Baseline lonjakan dimuat balik dari file: %d saham punya histori relevan.", restored_stocks)

    def add_and_check(self, stock: str, value_idr: float, action: str, volume_lot: float, ts: float) -> dict:
        """Selalu return dict berisi minimal {'warmed_up': bool, 'is_anomaly': bool}.
        'warmed_up' False artinya saham ini belum punya cukup histori (~SURGE_MIN_BUCKETS
        x SURGE_SHORT_WINDOW_SEC sejak saham itu mulai diamati) buat dinilai -- belum ada
        alert sama sekali buat saham itu selama masih dalam masa pengumpulan data ini."""
        dq = self.history[stock]
        cutoff = ts - self.long_window_sec
        while dq and dq[0][0] < cutoff:
            dq.popleft()

        # pecah histori (SEBELUM trade ini) jadi bucket non-overlap selebar short_window_sec
        current_bucket = []  # trade dalam short_window_sec paling akhir
        past_bucket_sums: dict[int, float] = defaultdict(float)
        for item_ts, item_val, _a, _v in dq:
            age = ts - item_ts
            bucket_idx = int(age // self.short_window_sec)
            if bucket_idx == 0:
                current_bucket.append((item_ts, item_val, _a, _v))
            else:
                past_bucket_sums[bucket_idx] += item_val

        dq.append((ts, value_idr, action, volume_lot))
        current_bucket.append((ts, value_idr, action, volume_lot))
        current_sum = sum(v for _, v, _, _ in current_bucket)

        past_buckets = list(past_bucket_sums.values())
        if len(past_buckets) < self.min_buckets:
            return {"warmed_up": False, "is_anomaly": False}

        mean = sum(past_buckets) / len(past_buckets)
        variance = sum((b - mean) ** 2 for b in past_buckets) / len(past_buckets)
        stddev = max(variance ** 0.5, mean * self.min_relative_stddev)

        if stddev > 0:
            z = (current_sum - mean) / stddev
        elif current_sum > mean:
            z = float("inf")  # histori bener2 nol total, tiba-tiba muncul aktivitas -> jelas anomali
        else:
            z = 0.0

        if z < self.z_threshold or current_sum < self.floor_value:
            return {"warmed_up": True, "is_anomaly": False}
        if ts - self.last_alert.get(stock, 0.0) < self.cooldown_sec:
            return {"warmed_up": True, "is_anomaly": False}
        self.last_alert[stock] = ts

        buy_val = sum(v for _, v, a, _ in current_bucket if a == "buy")
        sell_val = sum(v for _, v, a, _ in current_bucket if a == "sell")
        dominant_action = "buy" if buy_val >= sell_val else "sell"
        repeat_counts = self._bump_alert_count(stock, dominant_action, ts)

        return {
            "warmed_up": True,
            "is_anomaly": True,
            "current_sum": current_sum,
            "mean": mean,
            "z": z,
            "count": len(current_bucket),
            "volumes": [v for _, _, _, v in current_bucket],
            "dominant_action": dominant_action,
            "repeat_buy": repeat_counts["buy"],
            "repeat_sell": repeat_counts["sell"],
        }


class PowerBuySellTracker:
    """Lacak volume buy vs sell (lot) per saham per bucket waktu (default 10 menit)
    SEPANJANG HARI (reset tiap ganti hari WIB) -- pelengkap ActivitySurgeDetector.
    Detektor lonjakan nangkep TITIK anomali; ini kasih gambaran TREN buy/sell
    sepanjang hari buat saham yang udah cukup sering nongol di alert, mirip fitur
    "Power Buy/Sell" yang diadopsi dari bot referensi (Riaki Trade)."""

    def __init__(self, bucket_minutes: int = 10, digest_every: int = 5):
        self.bucket_minutes = bucket_minutes
        self.digest_every = digest_every
        self.day: str = ""
        self.data: dict[str, dict[str, list[float]]] = {}  # stock -> {bucket_label: [buy_lot, sell_lot]}
        self.last_digest_repeat: dict[str, int] = {}  # stock -> total repeat count terakhir kirim digest

    def _bucket_label(self, ts: float) -> str:
        dt = datetime.fromtimestamp(ts, tz=WIB)
        start_min = (dt.minute // self.bucket_minutes) * self.bucket_minutes
        bucket_start = dt.replace(minute=start_min, second=0, microsecond=0)
        bucket_end = bucket_start + timedelta(minutes=self.bucket_minutes - 1)
        return f"{bucket_start.strftime('%H:%M')}-{bucket_end.strftime('%H:%M')}"

    def add(self, stock: str, action: str, volume_lot: float, ts: float) -> None:
        today = datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d")
        if today != self.day:
            self.data = {}
            self.last_digest_repeat = {}
            self.day = today
        buckets = self.data.setdefault(stock, {})
        label = self._bucket_label(ts)
        buy_sell = buckets.setdefault(label, [0.0, 0.0])
        if action == "buy":
            buy_sell[0] += volume_lot
        elif action == "sell":
            buy_sell[1] += volume_lot

    def should_send_digest(self, stock: str, total_repeat: int) -> bool:
        """Kirim digest tiap kelipatan digest_every alert (5, 10, 15, ...) buat saham itu,
        sekali per kelipatan."""
        if total_repeat < self.digest_every or total_repeat % self.digest_every != 0:
            return False
        if self.last_digest_repeat.get(stock) == total_repeat:
            return False
        self.last_digest_repeat[stock] = total_repeat
        return True

    @staticmethod
    def _lot_short(v: float) -> str:
        if v >= 1e6:
            return f"{v / 1e6:.1f}jt".replace(".", ",")
        if v >= 1e3:
            return f"{v / 1e3:.0f}rb"
        return f"{v:.0f}"

    def format_digest(self, stock: str) -> str:
        """Tabel sempit (muat di layar HP tanpa terlipat): jam, batang porsi beli, % beli, total lot."""
        def row(label: str, buy: float, total: float) -> str:
            filled = round(buy / total * 10)
            return f"{label:<5} {'█' * filled}{'░' * (10 - filled)} {buy / total * 100:3.0f}% {self._lot_short(total):>6}"

        buckets = self.data.get(stock, {})
        rows = []
        total_buy = total_sell = 0.0
        for label in sorted(buckets):
            buy, sell = buckets[label]
            if buy + sell <= 0:
                continue
            rows.append(row(label[:5], buy, buy + sell))
            total_buy += buy
            total_sell += sell
        grand = total_buy + total_sell
        if grand <= 0:
            return f"📊 <b>{stock}</b>  ·  arus beli/jual hari ini\nBelum ada data."
        buy_pct = total_buy / grand * 100
        verdict = f"🟢 Beli dominan ({buy_pct:.0f}%)" if total_buy >= total_sell else f"🔴 Jual dominan ({100 - buy_pct:.0f}%)"
        body = "\n".join(["jam   █beli ░jual beli    lot", *rows, row("total", total_buy, grand)])
        return f"📊 <b>{stock}</b>  ·  arus beli/jual hari ini\n<pre>{body}</pre>\n{verdict}"


async def run_session(cfg: dict, notifier: TelegramNotifier, on_connected, surge: ActivitySurgeDetector,
                       power: "PowerBuySellTracker", prices: market_context.PriceContext,
                       store: broksum.BroksumStore, bars: technical.DailyBars,
                       watch: "watchlist.AutoWatchlist | None" = None) -> None:
    auth = StockbitAuthClient(token_cache_path=TOKEN_CACHE_PATH)
    auth.load_token_cache(TOKEN_CACHE_PATH)  # lempar ManualReloginRequired kalau belum ada/invalid
    _live_auth["auth"] = auth
    try:
        await _poll_loop(cfg, notifier, on_connected, surge, power, prices, store, bars, auth, watch)
    finally:
        _live_auth["auth"] = None


def technical_line(bars: technical.DailyBars, stock: str) -> str:
    """1 baris teknikal dari bar harian yang SUDAH jadi (sampai kemarin). "" kalau nggak ada data."""
    ind = technical.indicators(bars.completed(stock, datetime.now(WIB).strftime("%Y-%m-%d")))
    return technical.one_line(ind) if ind else ""


async def _poll_loop(cfg, notifier, on_connected, surge, power, prices, store, bars, auth, watch=None) -> None:
    token = auth.ensure_valid_token()
    log.info("Token valid, mulai polling running trade.")
    on_connected()

    short_window_sec = cfg["surge_short_window_sec"]
    seen: dict[str, float] = {}
    last_nego_alert: dict[str, float] = {}

    while True:
        token = auth.ensure_valid_token()
        try:
            trades, is_open = await asyncio.to_thread(fetch_running_trade, token)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 401:
                try:
                    auth.refresh()
                except StockbitAuthError as refresh_err:
                    raise ManualReloginRequired(
                        f"Token ditolak (401) dan refresh gagal: {refresh_err}. "
                        "Login manual lewat browser lalu kirim /settoken atau jalankan set_token.py."
                    ) from refresh_err
                trades, is_open = await asyncio.to_thread(fetch_running_trade, auth.token.access_token)
            else:
                raise

        if not is_open:
            if not is_market_hours(cfg):
                # Sudah lewat jam tutup / lagi jeda istirahat siang terjadwal / hari libur
                # (is_market_hours sekarang tahu jadwal istirahat & kalender libur) -- balik
                # ke loop luar di main(), biar tidur penuh sampai sesi berikutnya, bukan
                # tetap nge-ping.
                log.info("Di luar jam sesi perdagangan, keluar dari sesi polling.")
                return
            # Kasus nggak terjadwal: masih dalam jam sesi menurut kalender kita, tapi API
            # bilang market_open=false (mis. trading halt mendadak) -- jangan berhenti total,
            # tapi kurangin drastis frekuensi hit sampai buka lagi.
            log.info("Market_open=false di luar jadwal istirahat (kemungkinan halt), polling diperlambat.")
            await asyncio.sleep(random.uniform(50, 70))
            continue

        now = time.time()
        cutoff = now - SEEN_TTL_SEC
        for k in [k for k, t in seen.items() if t < cutoff]:
            del seen[k]

        meter = _meter["m"]
        if meter is not None:
            n_new = sum(1 for it in trades if f"{it.get('code')}|{it.get('trade_number')}" not in seen)
            meter.on_poll(len(trades), n_new)

        # urutkan dari yang paling lama ke paling baru biar kronologis wajar
        for item in reversed(trades):
            trade_key = f"{item.get('code')}|{item.get('trade_number')}"
            if trade_key in seen:
                continue
            seen[trade_key] = now
            if meter is not None:
                meter.on_trade(item)

            action = item.get("action", "")
            try:
                price = _num(item.get("price"))
                lot = _num(item.get("lot"))
                value_idr = _num((item.get("value") or {}).get("raw"))
            except (TypeError, ValueError):
                continue
            stock = item.get("code", "?")

            if item.get("market_board") in NON_REGULAR_BOARDS:
                # harga nego bisa jauh dari pasar reguler & arah buy/sell-nya nggak bermakna,
                # jadi jangan dicampur ke baseline lonjakan / jejak harga.
                if (cfg["nego_alert_idr"] > 0 and value_idr >= cfg["nego_alert_idr"]
                        and now - last_nego_alert.get(stock, 0.0) >= NEGO_ALERT_COOLDOWN_SEC):
                    last_nego_alert[stock] = now
                    log.info("ALERT NEGO %s total=%.0f", stock, value_idr)
                    notifier.send(format_nego_alert(item, stock, price, lot, value_idr))
                continue

            prices.update(stock, price, market_context.parse_pct(item.get("change")), now)
            power.add(stock, action, lot, now)
            if watch is not None:
                det = _pattern["det"]
                if det is not None and stock in watch.active:
                    try:
                        det.on_trade(stock, now, price, lot, action, item.get("buyer"), item.get("seller"))
                    except Exception as e:  # noqa: BLE001
                        log.warning("Pendeteksi pola (trade) %s gagal: %s", stock, e)
                for m in watch.on_trade(stock, price, action, value_idr, now):
                    log.info("WATCH %s: %s", stock, m.splitlines()[0])
                    notifier.send(m)
            surge_result = surge.add_and_check(stock, value_idr, action, lot, now)

            if surge_result["is_anomaly"]:
                change_str = str(item.get("change", "") or "-")
                snap = prices.snapshot(stock, price, now)
                adv = store.adv.get(stock)
                liquid = market_context.is_liquid(price, adv)
                code, verdict = market_context.assess(
                    surge_result["dominant_action"], snap, liquid,
                    surge_result["repeat_buy"], surge_result["repeat_sell"],
                )
                muted = code in cfg["alert_mute_codes"]
                log_alert({
                    "ts": round(now), "stock": stock, "action": surge_result["dominant_action"],
                    "price": price, "change": snap["change"], "sum": surge_result["current_sum"],
                    "mean": surge_result["mean"], "z": None if surge_result["z"] == float("inf") else round(surge_result["z"], 2),
                    "count": surge_result["count"], "repeat_buy": surge_result["repeat_buy"],
                    "repeat_sell": surge_result["repeat_sell"], "pre15": snap["pre15"],
                    "at_high": snap["at_high"], "at_low": snap["at_low"], "liquid": liquid,
                    "code": code, "muted": muted,
                })
                # watchlist ikut menilai SEMUA alert (termasuk yang dibisukan)
                watch_msgs = (watch.on_surge(stock, surge_result["dominant_action"], price, code, liquid, now)
                              if watch is not None else [])
                if muted:
                    log.info("ALERT LONJAKAN %s [%s] dibisukan (ALERT_MUTE_CODES)", stock, code)
                    for m in watch_msgs:
                        notifier.send(m)
                    continue
                tech = ""
                if cfg["alert_technical"]:
                    try:
                        tech = await asyncio.to_thread(technical_line, bars, stock)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Teknikal %s gagal: %s", stock, e)
                msg = format_surge_alert(
                    stock, surge_result["dominant_action"], surge_result["current_sum"],
                    surge_result["mean"], surge_result["z"], surge_result["count"],
                    short_window_sec, surge_result["volumes"],
                    price, change_str, surge_result["repeat_buy"], surge_result["repeat_sell"],
                    verdict, market_context.format_context(snap, liquid, adv), tech,
                )
                log.info("ALERT LONJAKAN %s [%s] action=%s total=%.0f z=%s count=%d", stock, code,
                          surge_result["dominant_action"], surge_result["current_sum"],
                          surge_result["z"], surge_result["count"])
                if _market["m"] is not None:
                    ihsg = _market["m"].line()
                    if ihsg:
                        msg += "\n" + ihsg
                notifier.send(msg)
                for m in watch_msgs:
                    log.info("WATCH %s: %s", stock, m.splitlines()[0])
                    notifier.send(m)

                total_repeat = surge_result["repeat_buy"] + surge_result["repeat_sell"]
                if power.should_send_digest(stock, total_repeat):
                    notifier.send(power.format_digest(stock))
                    log.info("DIGEST BUY/SELL %s (alert ke-%d hari ini)", stock, total_repeat)
            elif not surge_result["warmed_up"]:
                # saham ini belum punya baseline Z-score yang cukup -- diamkan dulu,
                # nggak ada alert sampai datanya cukup buat dinilai.
                log.debug("%s masih masa pengumpulan data, belum ada baseline.", stock)

        await asyncio.sleep(_poll_delay())


async def main():
    cfg = load_config()
    notifier = TelegramNotifier(cfg["tg_token"], cfg["tg_chat_id"])

    notifier.send("🚀 Stockbit running-trade monitor start (mode REST polling). Kirim /settoken kapan saja "
                  "buat isi/perbarui sesi, /help buat daftar perintah.")

    surge = ActivitySurgeDetector(
        short_window_sec=cfg["surge_short_window_sec"],
        long_window_sec=cfg["surge_long_window_sec"],
        min_buckets=cfg["surge_min_buckets"],
        z_threshold=cfg["surge_z_threshold"],
        floor_value=cfg["surge_floor_idr"],
        cooldown_sec=cfg["surge_cooldown_sec"],
        min_relative_stddev=cfg["surge_min_relative_stddev"],
    )
    surge.load_state(SURGE_STATE_PATH)

    power = PowerBuySellTracker(
        bucket_minutes=cfg["power_bucket_minutes"],
        digest_every=cfg["power_digest_every"],
    )

    os.makedirs(DATA_DIR, exist_ok=True)
    mkt = market.MarketContext(DATA_DIR)
    _market["m"] = mkt

    async def market_poll_loop():
        """IHSG tiap ~5 menit, hanya selama sesi polling aktif (pakai sesi yang sama)."""
        while True:
            await asyncio.sleep(random.uniform(270, 330))
            auth = _live_auth["auth"]
            if auth is None:
                continue
            try:
                await asyncio.to_thread(mkt.poll, auth)
            except Exception as e:  # noqa: BLE001
                log.warning("Ambil IHSG gagal: %s", e)

    asyncio.create_task(market_poll_loop())
    watch = None
    if cfg["watch_auto"]:
        watch = watchlist.AutoWatchlist(
            DATA_DIR,
            min_buy_alerts=cfg["watch_min_buy_alerts"],
            min_buy_share=cfg["watch_min_buy_share"],
            max_active=cfg["watch_max_active"],
            stop_pct=cfg["watch_stop_pct"],
            trail_pct=cfg["watch_trail_pct"],
            step_pct=cfg["watch_step_pct"],
            flow_window_min=cfg["watch_flow_window_min"],
            flip_sell_share=cfg["watch_flip_sell_share"],
            idle_min=cfg["watch_idle_min"],
            max_sell_alerts=cfg["watch_max_sell_alerts"],
        )
        watch.load_state()
        watch.context_fn = mkt.snapshot
        watch.note_fn = lambda: ("IHSG sedang tren turun (di bawah MA20 & MA50) — sinyal beli historis lebih lemah"
                                 if (mkt.regime() or {}).get("trend") == "down" else "")

    async def periodic_save_state():
        while True:
            await asyncio.sleep(SURGE_STATE_SAVE_INTERVAL_SEC)
            try:
                surge.save_state(SURGE_STATE_PATH)
                if watch is not None:
                    watch.save_state()
            except OSError as e:
                log.warning("Gagal simpan state: %s", e)

    asyncio.create_task(periodic_save_state())

    async def watch_recap_loop():
        """Sekali per hari bursa, setelah MARKET_CLOSE: rekap saham yang masuk pantauan otomatis."""
        while True:
            await asyncio.sleep(60)
            now = datetime.now(WIB)
            today = now.strftime("%Y-%m-%d")
            if (not is_trading_day(now) or now.strftime("%H:%M") < cfg["market_close"]
                    or watch.day != today or watch.recap_sent_day == today):
                continue
            watch.recap_sent_day = today
            text = watch.format_recap()
            if text:
                notifier.send(text)
                log.info("Rekap pantauan otomatis %s terkirim.", today)
            try:
                watch.save_state()
            except OSError as e:
                log.warning("Gagal simpan watch_state.json: %s", e)

    if watch is not None:
        asyncio.create_task(watch_recap_loop())

    if os.environ.get("MEASURE_COVERAGE", "1") == "1":
        meter = measure.CoverageMeter(DATA_DIR)
        meter.context_fn = mkt.snapshot
        _meter["m"] = meter

        async def measure_report_loop():
            """Sekali per hari bursa setelah MARKET_CLOSE: laporan kelengkapan running trade."""
            while True:
                await asyncio.sleep(60)
                now = datetime.now(WIB)
                today = now.strftime("%Y-%m-%d")
                if (not is_trading_day(now) or now.strftime("%H:%M") < cfg["market_close"]
                        or meter.day != today or meter.report_done or meter.polls == 0):
                    continue
                meter.report_done = True
                try:
                    _rep, text = await asyncio.to_thread(
                        meter.build_report, get_auth(), cfg["orderbook_path"], universe, meter.probe_result)
                    notifier.send(text)
                    log.info("Laporan pengukuran %s terkirim.", today)
                except Exception as e:  # noqa: BLE001
                    log.exception("Laporan pengukuran gagal: %s", e)

        asyncio.create_task(measure_report_loop())

    ob = orderbook.OrderbookCollector(
        DATA_DIR, cfg["orderbook_path"], cfg["orderbook_interval_sec"],
        cfg["orderbook_levels"], cfg["orderbook_max_mb_per_day"],
    )
    if watch is not None:
        det = obdetect.PatternDetector(
            DATA_DIR,
            wall_mult=float(os.environ.get("OBD_WALL_MULT", "5")),
            wall_min_idr=float(os.environ.get("OBD_WALL_MIN_IDR", "250000000")),
            pull_frac=float(os.environ.get("OBD_PULL_FRAC", "0.7")),
            algo_min_trades=int(os.environ.get("OBD_ALGO_MIN_TRADES", "6")),
            algo_max_cv=float(os.environ.get("OBD_ALGO_MAX_CV", "0.15")),
        )
        det.context_fn = mkt.snapshot
        _pattern["det"] = det

        def on_snapshot(code: str, ts: float, payload) -> None:
            snap = orderbook.parse_stockbit(payload, max_levels=60)  # semua level, bukan cuma yang disimpan
            if snap is not None:
                det.on_snapshot(code, ts, snap)

        asyncio.create_task(ob.run_forever(lambda: _live_auth["auth"], lambda: list(watch.active), notifier.send,
                                           on_snapshot))

    prices = market_context.PriceContext()
    store = broksum.BroksumStore(DATA_DIR)
    bars = technical.DailyBars(DATA_DIR)
    adaptive = broksum_adaptive.AdaptiveBroksum(
        DATA_DIR, store, bars, is_trading_day,
        max_range_req=int(os.environ.get("BROKSUM_ADAPTIVE_MAX_REQ", "60")),
    ) if os.environ.get("BROKSUM_ADAPTIVE", "1") == "1" else None
    if adaptive is not None:
        adaptive.context_fn = mkt.snapshot
    try:
        with open(UNIVERSE_PATH, encoding="utf-8") as f:
            universe = json.load(f)
    except (OSError, json.JSONDecodeError):
        universe = []

    def evening_tech_line(sym: str) -> str:
        ind = technical.indicators(bars.get(sym, max_age=1800))
        return technical.one_line(ind) if ind else ""
    started_at = time.time()
    state = {"first_connect_done": False, "degraded": False}
    recap_lock = asyncio.Lock()

    def alert_counts_today() -> dict:
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        return dict(surge.alert_count) if surge.alert_count_date == today else {}

    def last_trading_day(now: datetime) -> str:
        d = now
        if now.strftime("%H:%M") < cfg["market_open"]:
            d -= timedelta(days=1)
        while not is_trading_day(d):
            d -= timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def broksum_is_final(day: str, now: datetime) -> bool:
        """Broksum hari berjalan baru lengkap setelah tutup -- sebelum itu jangan disimpan."""
        return day < now.strftime("%Y-%m-%d") or now.strftime("%H:%M") >= cfg["eod_recap_time"]

    async def send_recap(day: str) -> None:
        async with recap_lock:
            screen = []
            if cfg["acc_screen"] and universe:
                # screening dulu: sekalian ngisi cache broksum hari ini buat rekap di bawah
                screen = await asyncio.to_thread(broksum.build_screen, store, get_auth(), day, universe, is_trading_day)
            msgs = await asyncio.to_thread(
                broksum.build_recap, store, get_auth(), day, alert_counts_today(), is_trading_day,
                cfg["eod_recap_min_alerts"], cfg["eod_recap_max_stocks"], evening_tech_line,
            )
            extra = []
            if adaptive is not None:
                counts = alert_counts_today()
                recap_syms = sorted(
                    (s for s, c in counts.items() if c.get("buy", 0) + c.get("sell", 0) >= cfg["eod_recap_min_alerts"]),
                    key=lambda s: -(counts[s].get("buy", 0) + counts[s].get("sell", 0)),
                )[:cfg["eod_recap_max_stocks"]]
                watched = set()
                if watch is not None and watch.day == day:
                    watched = set(watch.active) | {r["stock"] for r in watch.closed}
                cands = [(s, counts.get(s, {}).get("buy", 0), counts.get(s, {}).get("sell", 0), s in watched)
                         for s in dict.fromkeys(recap_syms + sorted(watched))]
                try:
                    extra = await asyncio.to_thread(adaptive.run, get_auth(), day, cands)
                except Exception as e:  # noqa: BLE001
                    log.exception("Broksum adaptif gagal: %s", e)
        try:
            summary = await asyncio.to_thread(mkt.evening_summary)
        except Exception as e:  # noqa: BLE001
            summary = ""
            log.warning("Ringkasan pasar gagal: %s", e)
        for m in ([summary] if summary else []) + msgs + extra + screen:
            notifier.send(m)

    async def eod_recap_loop():
        """Sekali per hari bursa, setelah EOD_RECAP_TIME: rekap broksum saham yang ramai alert."""
        while True:
            await asyncio.sleep(60)
            now = datetime.now(WIB)
            today = now.strftime("%Y-%m-%d")
            if not is_trading_day(now) or now.strftime("%H:%M") < cfg["eod_recap_time"]:
                continue
            try:
                with open(EOD_STATE_PATH, encoding="utf-8") as f:
                    if json.load(f).get("last_recap") == today:
                        continue
            except (OSError, json.JSONDecodeError):
                pass
            # tandai dulu biar kalau gagal nggak diulang-ulang tiap menit (bisa diulang manual: /rekap)
            with open(EOD_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"last_recap": today}, f)
            try:
                await send_recap(today)
                log.info("Rekap broksum %s terkirim.", today)
            except Exception as e:  # noqa: BLE001
                log.exception("Rekap broksum gagal: %s", e)
                notifier.send(f"⚠️ Rekap broksum {today} gagal: {e}. Coba ulang manual dengan /rekap.")

    if cfg["eod_recap"]:
        asyncio.create_task(eod_recap_loop())

    async def cmd_broksum(args: list[str]) -> None:
        if not args:
            notifier.send("Format: <code>/broksum KODE [YYYY-MM-DD]</code> — contoh: <code>/broksum BUMI</code>")
            return
        sym = args[0].upper()
        now = datetime.now(WIB)
        day = args[1] if len(args) > 1 else last_trading_day(now)
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            notifier.send("Tanggal harus format YYYY-MM-DD.")
            return
        if not is_trading_day(datetime.strptime(day, "%Y-%m-%d")):
            notifier.send(f"{day} bukan hari bursa.")
            return
        if not sym.isalnum() or len(sym) > 6:
            notifier.send("Kode saham tidak valid.")
            return
        final = broksum_is_final(day, now)
        counts = alert_counts_today().get(sym, {}) if day == now.strftime("%Y-%m-%d") else {}
        text, _ = await asyncio.to_thread(
            broksum.lookup, store, get_auth(), sym, day, is_trading_day, final,
            counts.get("buy", 0), counts.get("sell", 0), True,
        )
        if not text:
            notifier.send(f"Tidak ada data broksum {sym} untuk {day}.")
            return
        note = "" if final else "\n<i>(hari masih berjalan — broksum belum lengkap)</i>"
        notifier.send(f"📒 <b>Broksum</b> · {day}\n\n{text}{note}")
        if len(args) == 1:
            await cmd_ta([sym])

    async def cmd_ta(args: list[str]) -> None:
        if not args or not args[0].isalnum() or len(args[0]) > 6:
            notifier.send("Format: <code>/ta KODE</code> — contoh: <code>/ta BBRI</code>")
            return
        sym = args[0].upper()
        ind = technical.indicators(await asyncio.to_thread(bars.get, sym, 1800))
        if not ind:
            notifier.send(f"Data harga harian {sym} tidak ada / belum cukup (butuh ≥{technical.MIN_BARS} hari).")
            return
        notifier.send(
            f"📐 <b>{sym}</b>  ·  Rp{ind['c']:,.0f}".replace(",", ".") + f"  ·  bar {ind['day'][8:]}/{ind['day'][5:7]}\n"
            + "\n".join(market_context.bold_label(t) for t in technical.advise(ind))
            + "\n\n<i>Harga harian Yahoo. Angka historis: uji 2 tahun, relatif pasar, sebelum biaya.</i>"
        )

    async def cmd_akumulasi(_args: list[str]) -> None:
        if not universe:
            notifier.send("data/universe.json belum ada, screening tidak bisa jalan.")
            return
        now = datetime.now(WIB)
        day = last_trading_day(now)
        if not broksum_is_final(day, now):  # hari ini belum lengkap -> pakai hari bursa sebelumnya
            day = broksum.prior_trading_days(day, 1, is_trading_day)[0]
        notifier.send(f"⏳ Screening dijaga dan sepi untuk {day} (bisa ~5 menit kalau datanya belum ditarik)…")
        async with recap_lock:
            msgs = await asyncio.to_thread(broksum.build_screen, store, get_auth(), day, universe, is_trading_day)
        for m in msgs:
            notifier.send(m)

    async def cmd_rekap(_args: list[str]) -> None:
        now = datetime.now(WIB)
        today = now.strftime("%Y-%m-%d")
        if not alert_counts_today():
            notifier.send("Belum ada alert hari ini, tidak ada yang direkap.")
            return
        if not broksum_is_final(today, now):
            notifier.send(f"Broksum hari ini baru lengkap setelah tutup — rekap otomatis jam {cfg['eod_recap_time']} WIB.")
            return
        notifier.send("⏳ Menyusun rekap broksum, beberapa menit…")
        await send_recap(today)

    async def cmd_status(_args: list[str]) -> None:
        counts = alert_counts_today()
        n_alerts = sum(c.get("buy", 0) + c.get("sell", 0) for c in counts.values())
        if _live_auth["auth"] is not None:
            sesi = "polling aktif"
        elif state["degraded"]:
            sesi = "BERMASALAH (cek pesan error terakhir)"
        else:
            sesi = "tidur (di luar jam bursa)"
        up_h = (time.time() - started_at) / 3600
        notifier.send(
            f"<b>ℹ️ Status monitor</b>\n"
            f"Sesi: {sesi}\n"
            f"Jalan sejak: {up_h:.1f} jam lalu\n"
            f"Alert hari ini: {n_alerts} di {len(counts)} saham\n"
            f"Saham terpantau (30 menit terakhir): {sum(1 for dq in surge.history.values() if dq)}\n"
            f"Alert dibisukan: {', '.join(sorted(cfg['alert_mute_codes'])) or '-'}\n"
            f"Pantauan otomatis: {len(watch.active) if watch is not None else 'mati'}\n"
            f"Orderbook: {ob.status_line()}\n"
            f"Rekap broksum: {'jam ' + cfg['eod_recap_time'] + ' WIB' if cfg['eod_recap'] else 'mati'}"
        )

    async def cmd_pantau(args: list[str]) -> None:
        if watch is None:
            notifier.send("Watchlist otomatis dimatikan (WATCH_AUTO=0).")
            return
        now = time.time()
        if not args:
            notifier.send(watch.format_list(now))
            return
        sym = args[0].upper()
        if not sym.isalnum() or len(sym) > 6:
            notifier.send("Kode saham tidak valid.")
            return
        trail = prices.trail.get(sym)
        notifier.send(watch.add_manual(sym, trail[-1][1] if trail else None, now))

    async def cmd_lepas(args: list[str]) -> None:
        if watch is None:
            notifier.send("Watchlist otomatis dimatikan (WATCH_AUTO=0).")
            return
        if not args:
            notifier.send("Format: <code>/lepas KODE</code>")
            return
        notifier.send(watch.remove(args[0].upper(), time.time()))

    async def cmd_pola(args: list[str]) -> None:
        det = _pattern["det"]
        if det is None:
            notifier.send("Pendeteksi pola mati (butuh WATCH_AUTO=1 dan ORDERBOOK_PATH).")
            return
        sym = args[0].upper() if args and args[0].isalnum() and len(args[0]) <= 6 else None
        notifier.send(det.format_summary(sym))

    async def cmd_ob(args: list[str]) -> None:
        if not ob.enabled:
            notifier.send("Orderbook belum aktif: ORDERBOOK_PATH di .env belum diisi.")
            return
        if not args or not args[0].isalnum() or len(args[0]) > 6:
            notifier.send("Format: <code>/ob KODE</code>")
            return
        sym = args[0].upper()
        payload, status = await asyncio.to_thread(ob.fetch, get_auth(), sym)
        if status == 401:
            notifier.send("Token ditolak (401). Tunggu polling utama refresh, atau /settoken.")
            return
        parsed = orderbook.parse_levels(payload, 5)
        if parsed is None:
            snippet = json.dumps(payload, ensure_ascii=False)[:600]
            notifier.send(f"⚠️ Format orderbook {sym} belum dikenali. Potongan respons:\n<pre>{html.escape(snippet)}</pre>")
            return
        bids, offers = parsed
        rows = [f"{b[1]:>9,.0f} {b[0]:>7,.0f} | {o[0]:<7,.0f} {o[1]:,.0f}".replace(",", ".")
                for b, o in zip(bids, offers)]
        sm = orderbook.summarize(bids, offers)
        share = f"Porsi bid 5 level: {sm['bid_share'] * 100:.0f}%" if sm["bid_share"] is not None else ""
        notifier.send(f"📚 <b>{sym}</b> orderbook\n<pre>      lot     bid | offer   lot\n" + "\n".join(rows)
                      + f"</pre>{share}")

    async def cmd_help(_args: list[str]) -> None:
        notifier.send(
            "<b>Perintah</b>\n"
            "/status — kondisi monitor\n"
            "/pantau — daftar pantauan otomatis · /pantau KODE — tambah manual\n"
            "/lepas KODE — keluarkan saham dari pantauan\n"
            "/ob KODE — orderbook 5 level (butuh ORDERBOOK_PATH)\n"
            "/pola [KODE] — kandidat tembok dicabut / iceberg / pola algo hari ini\n"
            "/broksum KODE [YYYY-MM-DD] — broker summary, broker penggerak 10 hari + penilaian\n"
            "/ta KODE — teknikal harian (tren, RSI, support/resisten) + saran\n"
            "/akumulasi — screening saham dijaga & masih sepi\n"
            "/rekap — ulang rekap broksum sore ini\n"
            "/settoken ACCESS REFRESH — isi/perbarui sesi Stockbit"
        )

    listener = TelegramCommandListener(
        bot_token=cfg["tg_token"],
        authorized_chat_id=cfg["tg_chat_id"],
        token_cache_path=TOKEN_CACHE_PATH,
        reply_fn=notifier.send,
        commands={"/broksum": cmd_broksum, "/ta": cmd_ta, "/akumulasi": cmd_akumulasi, "/rekap": cmd_rekap,
                  "/status": cmd_status, "/help": cmd_help, "/pantau": cmd_pantau, "/lepas": cmd_lepas, "/ob": cmd_ob, "/pola": cmd_pola},
    )
    asyncio.create_task(listener.poll_forever())

    def on_connected():
        if not state["first_connect_done"]:
            notifier.send("✅ Monitor running trade IHSG aktif (polling tiap %ds)." % POLL_INTERVAL_SEC)
            state["first_connect_done"] = True
        elif state["degraded"]:
            notifier.send("✅ Monitor pulih dan lanjut polling running trade IHSG.")
            state["degraded"] = False

    backoff = 5
    last_relogin_notice = 0.0
    last_disconnect_notice = 0.0

    while True:
        if not is_market_hours(cfg):
            wait_s = min(seconds_until_next_open(cfg), 1800)
            log.info("Di luar jam bursa, tidur %.0f detik.", wait_s)
            await asyncio.sleep(wait_s)
            continue

        try:
            await run_session(cfg, notifier, on_connected, surge, power, prices, store, bars, watch)
        except ManualReloginRequired as e:
            log.error("Butuh login manual: %s", e)
            now = time.time()
            if now - last_relogin_notice > 2 * 3600:  # jangan spam, max tiap 2 jam
                notifier.send(
                    "⚠️ Sesi Stockbit habis/invalid. Login manual lewat browser lalu kirim "
                    "<code>/settoken ACCESS_TOKEN REFRESH_TOKEN</code> ke chat ini, "
                    "atau jalankan <code>python3 set_token.py</code> di server."
                )
                last_relogin_notice = now
            state["degraded"] = True
            await asyncio.sleep(600)
        except Exception as e:  # noqa: BLE001
            log.exception("Polling gagal: %s", e)
            now = time.time()
            if now - last_disconnect_notice > 900:  # jangan spam, max tiap 15 menit
                notifier.send(f"⚠️ Monitor gagal polling berulang kali (terakhir: {e}). Masih dicoba otomatis.")
                last_disconnect_notice = now
            state["degraded"] = True
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


if __name__ == "__main__":
    asyncio.run(main())
