"""
Deterministic Indonesian Number and Financial Formatter.
Strictly formats numbers into standard Indonesian accounting formats.
"""

from __future__ import annotations

from decimal import Decimal


def format_idr_nominal(val: Decimal | int | float | None) -> str:
    """Formats exact number into Indonesian thousand dot notation: 1.000.000.000."""
    if val is None:
        return "N/A"
    dec = Decimal(str(val))
    is_negative = dec < 0
    abs_dec = abs(dec)

    # Format integer part with dots
    parts = f"{abs_dec:.0f}"
    # Insert dots from right
    s = parts[::-1]
    groups = [s[i:i + 3] for i in range(0, len(s), 3)]
    formatted = ".".join(groups)[::-1]

    if is_negative:
        return f"({formatted})"
    return formatted


def format_decimal_id(val: Decimal | float | None, places: int = 2) -> str:
    """Formats decimal with Indonesian comma: 0,15 or 1,25."""
    if val is None:
        return "N/A"
    dec = Decimal(str(val))
    sign = "-" if dec < 0 else ""
    abs_dec = abs(dec)
    fmt_str = f"{{:.{places}f}}"
    res = fmt_str.format(abs_dec).replace(".", ",")
    return f"{sign}{res}"


def format_percentage_id(val: Decimal | float | None, places: int = 1) -> str:
    """Formats percentage ratio: 0.65 -> 65,0%."""
    if val is None:
        return "N/A"
    dec = Decimal(str(val)) * Decimal("100")
    return f"{format_decimal_id(dec, places)}%"


def format_bps(val: Decimal | float | None) -> str:
    """Formats basis points: +500 bps or -300 bps."""
    if val is None:
        return "N/A"
    dec = Decimal(str(val))
    sign = "+" if dec > 0 else ""
    return f"{sign}{dec:.0f} bps"


def format_progress_bar(val: Decimal | float | None, total_blocks: int = 8) -> str:
    """Creates visual gauge bar: e.g. [██████░░]."""
    if val is None:
        return "[────────]"
    try:
        fval = float(val)
        clamped = max(0.0, min(1.0, fval))
        filled = int(round(clamped * total_blocks))
        empty = total_blocks - filled
        return f"[{'█' * filled}{'░' * empty}]"
    except Exception:
        return "[────────]"


