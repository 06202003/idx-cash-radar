"""Deterministic IDX Risk:Reward ratio & Money Management (position sizing) calculator."""

from __future__ import annotations

import math
from typing import Any


def idx_tick_size(price: float) -> int:
    """Returns official IDX regular market tick size (fraksi harga BEI)."""
    if price < 200:
        return 1
    if price < 500:
        return 2
    if price < 2000:
        return 5
    if price < 5000:
        return 10
    return 25


def round_idx_tick(price: float, direction: str = "nearest") -> int:
    """Rounds a price to the nearest valid IDX tick size."""
    p = max(1.0, float(price))
    tick = idx_tick_size(p)
    if direction == "down":
        return max(1, int(math.floor(p / tick) * tick))
    if direction == "up":
        return max(1, int(math.ceil(p / tick) * tick))
    return max(1, int(round(p / tick) * tick))


def compute_risk_reward_plan(
    entry_price: float,
    support_price: float | None = None,
    resistance_price: float | None = None,
    capital_idr: float = 100_000_000.0,
    risk_pct: float = 0.01,
    max_alloc_pct: float = 0.25,
) -> dict[str, Any] | None:
    """
    Computes deterministic Entry, Stop Loss, Take Profit, Risk:Reward Ratio,
    and Money Management max lot size (1% max capital risk, capped at 25% single-stock allocation).
    """
    if entry_price <= 0:
        return None

    entry = round_idx_tick(entry_price, "nearest")
    tick_entry = idx_tick_size(entry)

    # Stop Loss: 1 tick below support if valid & tighter than 12%; else fallback -3%
    if support_price and 0 < support_price < entry:
        sl_candidate = round_idx_tick(support_price - idx_tick_size(support_price), "down")
        if (entry - sl_candidate) / entry > 0.12:
            sl_candidate = round_idx_tick(entry * 0.95, "down")
    else:
        sl_candidate = round_idx_tick(entry * 0.97, "down")

    if sl_candidate >= entry:
        sl_candidate = max(1, entry - tick_entry)

    # Take Profit: resistance if > entry; else fallback +6%
    if resistance_price and resistance_price > entry:
        tp_candidate = round_idx_tick(resistance_price, "up")
    else:
        tp_candidate = round_idx_tick(entry * 1.06, "up")

    if tp_candidate <= entry:
        tp_candidate = entry + (2 * tick_entry)

    risk_per_share = entry - sl_candidate
    reward_per_share = tp_candidate - entry
    if risk_per_share <= 0:
        return None

    rr_ratio = round(reward_per_share / risk_per_share, 2)
    risk_drop_pct = round((risk_per_share / entry) * 100.0, 2)
    reward_gain_pct = round((reward_per_share / entry) * 100.0, 2)

    cap = max(0.0, float(capital_idr))
    max_risk_idr = cap * risk_pct
    risk_per_lot = risk_per_share * 100
    cost_per_lot = entry * 100

    lots_by_risk = int(max_risk_idr // risk_per_lot) if risk_per_lot > 0 else 0
    lots_by_alloc = int((cap * max_alloc_pct) // cost_per_lot) if cost_per_lot > 0 else 0
    rec_lots = max(0, min(lots_by_risk, lots_by_alloc))

    position_idr = rec_lots * cost_per_lot
    actual_risk_idr = rec_lots * risk_per_lot
    potential_profit_idr = rec_lots * reward_per_share * 100
    is_favorable = rr_ratio >= 1.5

    return {
        "entry": entry,
        "stop_loss": sl_candidate,
        "take_profit": tp_candidate,
        "rr_ratio": rr_ratio,
        "risk_drop_pct": risk_drop_pct,
        "reward_gain_pct": reward_gain_pct,
        "capital_idr": cap,
        "risk_pct": round(risk_pct * 100.0, 1),
        "recommended_lots": rec_lots,
        "position_idr": position_idr,
        "actual_risk_idr": actual_risk_idr,
        "potential_profit_idr": potential_profit_idr,
        "is_favorable": is_favorable,
    }


def _fmt_rp(val: float) -> str:
    return f"Rp {int(round(val)):,}".replace(",", ".")


def _fmt_short_idr(val: float) -> str:
    if abs(val) >= 1e9:
        return f"Rp {val / 1e9:.2f} M"
    if abs(val) >= 1e6:
        return f"Rp {val / 1e6:.1f} Jt"
    return _fmt_rp(val)


def format_risk_reward_block(plan: dict[str, Any]) -> list[str]:
    """Formats full Risk:Reward & Money Management block for /cek and /morning cards."""
    rr_badge = "✅ Layak (≥ 1:1.5)" if plan["is_favorable"] else "⚠️ Sempit (< 1:1.5)"
    lots_s = f"{plan['recommended_lots']:,}".replace(",", ".")
    return [
        "",
        "⚖️ *RISK:REWARD & MONEY MANAGEMENT:*",
        f"• Entry: `{_fmt_rp(plan['entry'])}` | SL: `{_fmt_rp(plan['stop_loss'])}` (`-{plan['risk_drop_pct']}%`) | TP: `{_fmt_rp(plan['take_profit'])}` (`+{plan['reward_gain_pct']}%`)",
        f"• R:R Ratio: `1 : {plan['rr_ratio']}` ({rr_badge})",
        f"• Sizing (Modal `{_fmt_short_idr(plan['capital_idr'])}`, Risk `{plan['risk_pct']}%`): Maks `{lots_s} lot` (`{_fmt_short_idr(plan['position_idr'])}` | Maks Rugi `{_fmt_short_idr(plan['actual_risk_idr'])}`)",
    ]


def format_risk_reward_compact(plan: dict[str, Any]) -> str:
    """Formats 1-line R:R & lot sizing for instant live-alert follow-ups."""
    lots_s = f"{plan['recommended_lots']:,}".replace(",", ".")
    return (
        f"• R:R & Sizing: Entry `{_fmt_rp(plan['entry'])}` | SL `{_fmt_rp(plan['stop_loss'])}` | "
        f"TP `{_fmt_rp(plan['take_profit'])}` (`1:{plan['rr_ratio']}`) → Maks `{lots_s} lot`"
    )
