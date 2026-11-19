"""Real-time Orderbook Wall & Big-Lot (low-freq) delta detector for IDX stocks."""

from __future__ import annotations

from typing import Any


def detect_orderbook_wall_deltas(
    prev_ob: dict[str, dict[int, dict[str, int]]],
    curr_ob: dict[str, dict[int, dict[str, int]]],
    min_delta_lot: int = 5000,
    max_delta_freq: int = 2,
) -> list[dict[str, Any]]:
    """
    Compares two orderbook snapshots (bid & offer levels) and flags any price level
    where lot jumped by >= min_delta_lot while frequency increased by <= max_delta_freq
    (e.g., +10,000 lots added at Offer 5,700 with only +1 freq).
    """
    alerts: list[dict[str, Any]] = []
    for side in ("bid", "offer"):
        prev_levels = prev_ob.get(side) or {}
        curr_levels = curr_ob.get(side) or {}
        for price, curr_vals in curr_levels.items():
            prev_vals = prev_levels.get(price) or {"lot": 0, "freq": 0}
            delta_lot = int(curr_vals.get("lot", 0)) - int(prev_vals.get("lot", 0))
            delta_freq = int(curr_vals.get("freq", 0)) - int(prev_vals.get("freq", 0))
            if delta_lot >= min_delta_lot and 0 <= delta_freq <= max_delta_freq:
                alerts.append({
                    "side": side.upper(),
                    "price": int(price),
                    "delta_lot": delta_lot,
                    "delta_freq": delta_freq,
                    "total_lot": int(curr_vals.get("lot", 0)),
                    "total_freq": int(curr_vals.get("freq", 0)),
                })
    return alerts


def format_orderbook_wall_alert(ticker: str, wall: dict[str, Any]) -> str:
    """Formats a crisp 3-second Telegram alert for a sudden Bid/Offer wall."""
    side = wall["side"]
    emoji = "🧱" if side == "OFFER" else "🛡️"
    label = "OFFER WALL (Antrean Jual Besar)" if side == "OFFER" else "BID WALL (Antrean Beli Besar)"
    price_s = f"Rp {wall['price']:,}".replace(",", ".")
    dlot_s = f"+{wall['delta_lot']:,}".replace(",", ".")
    tlot_s = f"{wall['total_lot']:,}".replace(",", ".")
    return (
        f"{emoji} *{label} | {ticker} @ {price_s}*\n"
        f"• Perubahan: `{dlot_s} lot` (Freq: `+{wall['delta_freq']}`)\n"
        f"• Total di level ini: `{tlot_s} lot` (`{wall['total_freq']} freq`)"
    )
