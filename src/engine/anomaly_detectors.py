"""Real-time Stockbit anomaly detectors: Broker Flip (Institusi vs Ritel), Wall Pulled, and 1m HAKA/HAKI Dominance."""

from __future__ import annotations

from typing import Any

from src.data.market_feed import parse_safe_float

# 16 major retail-heavy IDX broker codes
RETAIL_BROKERS: frozenset[str] = frozenset({
    "XL", "YP", "PD", "XC", "KK", "NI", "SQ", "DR",
    "EP", "IF", "LG", "OD", "RO", "SH", "YJ", "GR",
})


def detect_broker_flow_anomaly(
    ticker: str,
    marketdetectors_payload: dict[str, Any],
    min_net_idr: float = 500_000_000.0,
) -> dict[str, Any] | None:
    """
    Classifies net flow between retail brokers vs non-retail/institutional brokers.
    Flags:
      - DISTRIBUSI_KE_RITEL: non-retail net sell > min_net_idr while retail net buy > min_net_idr
      - SERAPAN_NON_RITEL: retail net sell > min_net_idr while non-retail net buy > min_net_idr
    """
    data = marketdetectors_payload.get("data") or {}
    broksum = data.get("broker_summary") or {}
    buyers = broksum.get("brokers_buy") or []
    sellers = broksum.get("brokers_sell") or []

    retail_net = 0.0
    non_retail_net = 0.0
    foreign_net = 0.0
    top_non_retail_sell: list[str] = []
    top_non_retail_buy: list[str] = []
    top_retail_buy: list[str] = []
    top_retail_sell: list[str] = []

    for b in buyers:
        code = str(b.get("netbs_broker_code") or b.get("broker_code") or "").upper()
        val = abs(parse_safe_float(b.get("bval")) or 0.0)
        if str(b.get("type") or "").lower() == "asing":
            foreign_net += val
        if code in RETAIL_BROKERS:
            retail_net += val
            if len(top_retail_buy) < 3:
                top_retail_buy.append(code)
        elif code:
            non_retail_net += val
            if len(top_non_retail_buy) < 3:
                top_non_retail_buy.append(code)

    for s in sellers:
        code = str(s.get("netbs_broker_code") or s.get("broker_code") or "").upper()
        raw_sval = s.get("sval") if s.get("sval") is not None else s.get("bval")
        val = abs(parse_safe_float(raw_sval) or 0.0)
        if str(s.get("type") or "").lower() == "asing":
            foreign_net -= val
        if code in RETAIL_BROKERS:
            retail_net -= val
            if len(top_retail_sell) < 3:
                top_retail_sell.append(code)
        elif code:
            non_retail_net -= val
            if len(top_non_retail_sell) < 3:
                top_non_retail_sell.append(code)

    if non_retail_net <= -min_net_idr and retail_net >= min_net_idr:
        return {
            "ticker": ticker,
            "signal": "DISTRIBUSI_KE_RITEL",
            "retail_net_idr": retail_net,
            "non_retail_net_idr": non_retail_net,
            "foreign_net_idr": foreign_net,
            "non_retail_brokers": top_non_retail_sell,
            "retail_brokers": top_retail_buy,
        }
    if retail_net <= -min_net_idr and non_retail_net >= min_net_idr:
        return {
            "ticker": ticker,
            "signal": "SERAPAN_NON_RITEL",
            "retail_net_idr": retail_net,
            "non_retail_net_idr": non_retail_net,
            "foreign_net_idr": foreign_net,
            "non_retail_brokers": top_non_retail_buy,
            "retail_brokers": top_retail_sell,
        }
    return None


def format_broker_flow_alert(ev: dict[str, Any]) -> str:
    def _fmt_m(v: float) -> str:
        return f"Rp {abs(v) / 1e9:.2f} M" if abs(v) >= 1e9 else f"Rp {abs(v) / 1e6:.0f} Jt"

    f_net = float(ev.get("foreign_net_idr") or 0.0)
    f_line = ""
    if abs(f_net) >= 1e6:
        f_sign = "+" if f_net > 0 else "-"
        f_line = f"\n• Asing Net: `{f_sign}{_fmt_m(f_net)}`"

    if ev["signal"] == "DISTRIBUSI_KE_RITEL":
        return (
            f"🔴 *DISTRIBUSI KE RITEL | {ev['ticker']}*\n"
            f"• Non-Ritel Net Sell: `{_fmt_m(ev['non_retail_net_idr'])}` (`{', '.join(ev['non_retail_brokers'])}`)\n"
            f"• Ritel Menampung: `{_fmt_m(ev['retail_net_idr'])}` (`{', '.join(ev['retail_brokers'])}`)"
            f"{f_line}"
        )
    return (
        f"🟢 *SERAPAN NON-RITEL | {ev['ticker']}*\n"
        f"• Non-Ritel Net Buy: `{_fmt_m(ev['non_retail_net_idr'])}` (`{', '.join(ev['non_retail_brokers'])}`)\n"
        f"• Ritel Net Sell: `{_fmt_m(ev['retail_net_idr'])}` (`{', '.join(ev['retail_brokers'])}`)"
        f"{f_line}"
    )


def detect_wall_pulled(
    prev_ob: dict[str, dict[int, dict[str, int]]],
    curr_ob: dict[str, dict[int, dict[str, int]]],
    min_pulled_lot: int = 5000,
    trade_lots: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Detects sudden large Bid/Offer walls disappearing (delta_lot <= -min_pulled_lot & delta_freq < 0).
    If `trade_lots` (from 1m tradebook) shows >= 40% of the disappeared lot was matched by
    HAKI (for bid) or HAKA (for offer), marks `eaten_by_trade = True` instead of genuine cancel.
    """
    pulled: list[dict[str, Any]] = []
    buy_lot = float((trade_lots or {}).get("buy_lot") or 0.0)
    sell_lot = float((trade_lots or {}).get("sell_lot") or 0.0)

    for side in ("bid", "offer"):
        prev_levels = prev_ob.get(side) or {}
        curr_levels = curr_ob.get(side) or {}
        for price, prev_vals in prev_levels.items():
            curr_vals = curr_levels.get(price) or {"lot": 0, "freq": 0}
            delta_lot = int(curr_vals.get("lot", 0)) - int(prev_vals.get("lot", 0))
            delta_freq = int(curr_vals.get("freq", 0)) - int(prev_vals.get("freq", 0))
            if delta_lot <= -min_pulled_lot and delta_freq < 0:
                pulled_lot = abs(delta_lot)
                matched_lot = sell_lot if side == "bid" else buy_lot
                eaten = bool(trade_lots is not None and matched_lot >= 0.4 * pulled_lot)
                pulled.append({
                    "side": side.upper(),
                    "price": int(price),
                    "pulled_lot": pulled_lot,
                    "delta_freq": delta_freq,
                    "eaten_by_trade": eaten,
                })
    return pulled


def format_wall_pulled_alert(ticker: str, w: dict[str, Any]) -> str:
    price_s = f"Rp {w['price']:,}".replace(",", ".")
    lot_s = f"-{w['pulled_lot']:,}".replace(",", ".")
    return (
        f"🕳️ *WALL DICABUT ({w['side']}) | {ticker} @ {price_s}*\n"
        f"• Perubahan: `{lot_s} lot` (Freq: `{w['delta_freq']}`)"
    )


def _extract_raw_metric(entry: dict[str, Any], field: str) -> float:
    raw_obj = entry.get(field)
    if isinstance(raw_obj, dict):
        return parse_safe_float(raw_obj.get("raw")) or 0.0
    return parse_safe_float(raw_obj) or 0.0


def _latest_cumulative_delta(series: list[dict[str, Any]], field: str) -> float:
    if not series:
        return 0.0
    curr = _extract_raw_metric(series[-1], field)
    if len(series) >= 2:
        prev = _extract_raw_metric(series[-2], field)
        return max(0.0, curr - prev)
    return max(0.0, curr)


def extract_latest_tradebook_delta(tradebook_payload: dict[str, Any]) -> dict[str, Any]:
    """Extracts the latest 1-minute HAKA/HAKI lot & value delta from Stockbit trade-book JSON."""
    data = tradebook_payload.get("data") or {}
    buy_series = data.get("buy")
    sell_series = data.get("sell")
    if isinstance(buy_series, list) and isinstance(sell_series, list) and (buy_series or sell_series):
        last_entry = buy_series[-1] if buy_series else sell_series[-1]
        return {
            "buy_lot": _latest_cumulative_delta(buy_series, "lot"),
            "sell_lot": _latest_cumulative_delta(sell_series, "lot"),
            "buy_val": _latest_cumulative_delta(buy_series, "value"),
            "sell_val": _latest_cumulative_delta(sell_series, "value"),
            "time": str(last_entry.get("time")) if isinstance(last_entry, dict) and last_entry.get("time") else None,
        }
    return {"buy_lot": 0.0, "sell_lot": 0.0, "buy_val": 0.0, "sell_val": 0.0, "time": None}


def detect_tradebook_dominance(
    ticker: str,
    tradebook_payload: dict[str, Any],
    min_value_idr: float = 100_000_000.0,
    dominance_ratio: float = 0.75,
) -> dict[str, Any] | None:
    """
    Checks latest 1m bar of Stockbit trade-book/chart for HAKA vs HAKI dominance
    above min_value_idr (filtering out < Rp100jt noise).
    Supports Stockbit's real cumulative `data.buy` / `data.sell` arrays as well as
    non-cumulative `chart` / `trade_book` / `bars` fallback.
    """
    data = tradebook_payload.get("data") or {}
    buy_series = data.get("buy")
    sell_series = data.get("sell")

    bar_time: str | None = None
    buy_lot = 0.0
    sell_lot = 0.0

    if isinstance(buy_series, list) and isinstance(sell_series, list) and (buy_series or sell_series):
        buy_val = _latest_cumulative_delta(buy_series, "value")
        sell_val = _latest_cumulative_delta(sell_series, "value")
        buy_lot = _latest_cumulative_delta(buy_series, "lot")
        sell_lot = _latest_cumulative_delta(sell_series, "lot")
        last_entry = buy_series[-1] if buy_series else sell_series[-1]
        if isinstance(last_entry, dict) and last_entry.get("time"):
            bar_time = str(last_entry.get("time"))
    else:
        bars = data.get("chart") or data.get("trade_book") or data.get("bars") or []
        if not bars or not isinstance(bars, list):
            return None
        last = bars[-1]
        buy_val = parse_safe_float(last.get("buy_value") or last.get("haka_value") or last.get("buy_val")) or 0.0
        sell_val = parse_safe_float(last.get("sell_value") or last.get("haki_value") or last.get("sell_val")) or 0.0
        if last.get("time"):
            bar_time = str(last.get("time"))

    total = buy_val + sell_val
    if total < min_value_idr:
        return None

    buy_pct = buy_val / total
    sell_pct = sell_val / total
    if buy_pct >= dominance_ratio:
        return {
            "ticker": ticker,
            "side": "HAKA",
            "dominance_pct": round(buy_pct * 100.0, 1),
            "total_value_idr": total,
            "buy_lot": int(round(buy_lot)),
            "sell_lot": int(round(sell_lot)),
            "time": bar_time,
        }
    if sell_pct >= dominance_ratio:
        return {
            "ticker": ticker,
            "side": "HAKI",
            "dominance_pct": round(sell_pct * 100.0, 1),
            "total_value_idr": total,
            "buy_lot": int(round(buy_lot)),
            "sell_lot": int(round(sell_lot)),
            "time": bar_time,
        }
    return None


def format_tradebook_dominance_alert(ev: dict[str, Any]) -> str:
    val_jt = ev["total_value_idr"] / 1e6
    time_suffix = f" ({ev['time']} WIB)" if ev.get("time") else ""
    if ev["side"] == "HAKA":
        return f"⚡ *HAKA DOMINAN 1M | {ev['ticker']}*{time_suffix}\n• Rasio HAKA: `{ev['dominance_pct']}%` (Nilai: `Rp {val_jt:.0f} Jt`)"
    return f"🔻 *HAKI DOMINAN 1M | {ev['ticker']}*{time_suffix}\n• Rasio HAKI: `{ev['dominance_pct']}%` (Nilai: `Rp {val_jt:.0f} Jt`)"
