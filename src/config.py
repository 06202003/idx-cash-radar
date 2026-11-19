"""Configuration and default IDX ticker universe for idx-alert-bot."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
# Use /tmp on read-only serverless filesystems (e.g., Vercel)
_default_db = ROOT_DIR / "idx_alert_bot.db"
DB_PATH = Path("/tmp/idx_alert_bot.db") if os.getenv("VERCEL") else _default_db

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
STOCKBIT_BEARER_TOKEN = os.getenv("STOCKBIT_BEARER_TOKEN", "").strip()
STOCKBIT_PROFILE_DIR = ROOT_DIR / ".stockbit_browser_profile"
STOCKBIT_TOKEN_FILE = ROOT_DIR / ".stockbit_token"
CASH_RADAR_API_URL = os.getenv("CASH_RADAR_API_URL", "https://idx-cash-radar.vercel.app").rstrip("/")
DEFAULT_CHAT_ID = os.getenv("DEFAULT_CHAT_ID", "").strip()
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
DEFAULT_WATCHLIST_ENV = os.getenv("DEFAULT_WATCHLIST", "").strip()

MORNING_ALERT_HOUR = int(os.getenv("MORNING_ALERT_HOUR", "8"))
MORNING_ALERT_MINUTE = int(os.getenv("MORNING_ALERT_MINUTE", "45"))
EVENING_RECAP_HOUR = int(os.getenv("EVENING_RECAP_HOUR", "18"))
EVENING_RECAP_MINUTE = int(os.getenv("EVENING_RECAP_MINUTE", "0"))
ROUND_TRIP_FEE = float(os.getenv("ROUND_TRIP_FEE", "0.004"))

DEFAULT_UNIVERSE: list[str] = [
    "BBCA", "BBRI", "BMRI", "BBNI", "BRIS",
    "TLKM", "ISAT", "EXCL", "TOWR", "MTEL",
    "ASII", "UNTR", "ADRO", "AADI", "PTBA", "ITMG", "ANTM", "INCO", "MEDC", "PGAS", "AKRA",
    "ICBP", "INDF", "MYOR", "KLBF", "SIDO", "AMRT", "MAPI", "ACES", "UNVR", "HMSP", "CMRY",
    "TOTL", "PTPP", "ADHI", "WIKA", "WSKT", "ACST", "NRCA", "JKON",
]
