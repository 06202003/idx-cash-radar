"""IDX (Bursa Efek Indonesia) trading holiday calendar in Asia/Jakarta (WIB)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

# Official Indonesian national holidays & IDX trading holidays (2025 - 2026).
IDX_HOLIDAYS: frozenset[date] = frozenset({
    # 2025
    date(2025, 1, 1),
    date(2025, 1, 27),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 3, 28),
    date(2025, 3, 29),
    date(2025, 3, 31),
    date(2025, 4, 1),
    date(2025, 4, 2),
    date(2025, 4, 3),
    date(2025, 4, 4),
    date(2025, 4, 7),
    date(2025, 4, 18),
    date(2025, 5, 1),
    date(2025, 5, 12),
    date(2025, 5, 13),
    date(2025, 5, 29),
    date(2025, 5, 30),
    date(2025, 6, 6),
    date(2025, 6, 9),
    date(2025, 6, 27),
    date(2025, 9, 5),
    date(2025, 12, 25),
    date(2025, 12, 26),
    # 2026
    date(2026, 1, 1),
    date(2026, 1, 16),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 3, 18),
    date(2026, 3, 19),
    date(2026, 3, 20),
    date(2026, 3, 23),
    date(2026, 3, 24),
    date(2026, 4, 3),
    date(2026, 5, 1),
    date(2026, 5, 14),
    date(2026, 5, 15),
    date(2026, 5, 27),
    date(2026, 5, 28),
    date(2026, 6, 1),
    date(2026, 6, 16),
    date(2026, 8, 17),
    date(2026, 8, 25),
    date(2026, 12, 24),
    date(2026, 12, 25),
})


def now_wib() -> datetime:
    """Returns current datetime in Asia/Jakarta."""
    return datetime.now(WIB)


def is_idx_trading_day(target_date: date | None = None) -> bool:
    """Returns True if target_date (default today WIB) is a weekday and not an IDX holiday."""
    d = target_date or now_wib().date()
    if d.weekday() >= 5:
        return False
    return d not in IDX_HOLIDAYS
