"""Broker Lead-Lag & Pattern Engine (e.g. 'XL net buy yesterday -> XC active today')."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


def _fmt_miliar(val_idr: float) -> str:
    av = abs(val_idr)
    if av >= 1e9:
        return f"Rp {val_idr / 1e9:.1f}M"
    if av >= 1e6:
        return f"Rp {val_idr / 1e6:.0f}Jt"
    return f"Rp {val_idr:,.0f}".replace(",", ".")


def _build_price_map(ohlcv_df: pd.DataFrame | None) -> dict[str, dict[str, float]]:
    if ohlcv_df is None or ohlcv_df.empty:
        return {}
    out: dict[str, dict[str, float]] = {}
    for _, row in ohlcv_df.iterrows():
        d_raw = row.get("date")
        if d_raw is None:
            continue
        day_str = str(d_raw)[:10]
        c = float(row.get("close") or 0.0)
        h = float(row.get("high") or c)
        o = float(row.get("open") or c)
        if c > 0:
            out[day_str] = {"open": o, "high": h, "close": c}
    return out


def analyze_broker_patterns(
    history_rows: list[dict[str, Any]],
    ohlcv_df: pd.DataFrame | None = None,
    latest_broksum: dict[str, Any] | None = None,
    min_val_idr: float = 200_000_000.0,
) -> dict[str, Any]:
    """
    Detects historical T-1 -> T broker lead-lag patterns and next-day price reactions.
    """
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in history_rows:
        day = str(r.get("day_wib") or "")[:10]
        if day:
            by_day[day].append(r)

    days = sorted(by_day.keys())
    price_map = _build_price_map(ohlcv_df)

    # Fallback when DB history is empty: use latest_broksum snapshot if available
    if not days:
        top_b = []
        top_s = []
        if latest_broksum:
            top_b = [
                {
                    "code": b["code"],
                    "net_val_idr": float(b.get("value_idr") or 0.0),
                    "avg_price": b.get("avg_price"),
                }
                for b in (latest_broksum.get("top_buyers") or [])[:4]
            ]
            top_s = [
                {
                    "code": s["code"],
                    "net_val_idr": -abs(float(s.get("value_idr") or 0.0)),
                    "avg_price": s.get("avg_price"),
                }
                for s in (latest_broksum.get("top_sellers") or [])[:4]
            ]
        headline = "History broker harian mulai direkam hari ini. Cek top buyer/seller terbaru di grafik."
        if top_b:
            lead = top_b[0]
            headline = (
                f"Top Buyer terbaru: {lead['code']} ({_fmt_miliar(lead['net_val_idr'])}). "
                "History pola T-1->T mulai dikumpulkan."
            )
        return {
            "history_days": 0,
            "latest_day": None,
            "top_buyers_yesterday": top_b,
            "top_sellers_yesterday": top_s,
            "lead_lag_signals": [],
            "headline": headline,
        }

    # Build per-day top buyers & all buyers/sellers
    day_top_buyers: dict[str, list[dict[str, Any]]] = {}
    day_all_buyers: dict[str, set[str]] = {}
    day_top_sellers: dict[str, list[dict[str, Any]]] = {}

    for d in days:
        rows = by_day[d]
        buyers = sorted(
            [r for r in rows if float(r.get("net_val_idr") or 0.0) > 0],
            key=lambda x: float(x.get("net_val_idr") or 0.0),
            reverse=True,
        )
        sellers = sorted(
            [r for r in rows if float(r.get("net_val_idr") or 0.0) < 0],
            key=lambda x: float(x.get("net_val_idr") or 0.0),
        )
        day_top_buyers[d] = [
            {
                "code": str(b["broker_code"]),
                "net_val_idr": float(b["net_val_idr"]),
                "avg_price": b.get("avg_price"),
            }
            for b in buyers[:4]
        ]
        day_top_sellers[d] = [
            {
                "code": str(s["broker_code"]),
                "net_val_idr": float(s["net_val_idr"]),
                "avg_price": s.get("avg_price"),
            }
            for s in sellers[:4]
        ]
        day_all_buyers[d] = {
            str(b["broker_code"])
            for b in buyers
            if float(b.get("net_val_idr") or 0.0) >= (min_val_idr * 0.5)
        }

    latest_day = days[-1]
    latest_buyers = day_top_buyers[latest_day]
    latest_sellers = day_top_sellers[latest_day]

    # Compute T-1 -> T transitions across historical pairs (excluding latest_day as T-1 since T hasn't happened)
    lead_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"triggers": 0, "followers": defaultdict(int), "rets": [], "max_gains": []}
    )
    for idx in range(len(days) - 1):
        d_prev = days[idx]
        d_next = days[idx + 1]
        # Top-3 buyers on d_prev above min_val_idr
        sig_leads = [
            b["code"]
            for b in day_top_buyers[d_prev][:3]
            if b["net_val_idr"] >= min_val_idr
        ]
        next_buyers = day_all_buyers[d_next]
        p_prev = price_map.get(d_prev)
        p_next = price_map.get(d_next)
        ret_pct = None
        max_gain_pct = None
        if p_prev and p_next and p_prev["close"] > 0:
            ret_pct = (p_next["close"] / p_prev["close"] - 1.0) * 100.0
            max_gain_pct = (p_next["high"] / p_prev["close"] - 1.0) * 100.0

        for lead_code in sig_leads:
            st = lead_stats[lead_code]
            st["triggers"] += 1
            for f_code in next_buyers:
                if f_code != lead_code:
                    st["followers"][f_code] += 1
            if ret_pct is not None:
                st["rets"].append(ret_pct)
            if max_gain_pct is not None:
                st["max_gains"].append(max_gain_pct)

    signals: list[dict[str, Any]] = []
    for b in latest_buyers[:3]:
        lead_code = b["code"]
        if b["net_val_idr"] < min_val_idr:
            continue
        st = lead_stats.get(lead_code)
        if not st or st["triggers"] < 2 or not st["followers"]:
            continue
        best_follow, follow_cnt = max(st["followers"].items(), key=lambda kv: kv[1])
        triggers = st["triggers"]
        follow_rate = (follow_cnt / triggers) * 100.0
        if follow_cnt < 2 or follow_rate < 50.0:
            continue

        max_gains = st["max_gains"]
        rets = st["rets"]
        avg_max_gain = sum(max_gains) / len(max_gains) if max_gains else None
        win_rate = (sum(1 for g in max_gains if g >= 1.0) / len(max_gains) * 100.0) if max_gains else None
        avg_ret = sum(rets) / len(rets) if rets else None

        gain_txt = f" | avg max H+1 {avg_max_gain:+.1f}%" if avg_max_gain is not None else ""
        summary_id = (
            f"{lead_code} masuk {_fmt_miliar(b['net_val_idr'])} ({latest_day}) -> "
            f"historis {follow_cnt}/{triggers}x ({follow_rate:.0f}%) {best_follow} ikut masuk di H+1{gain_txt}"
        )
        signals.append({
            "lead_broker": lead_code,
            "lead_net_val_idr": b["net_val_idr"],
            "follow_broker": best_follow,
            "follow_count": follow_cnt,
            "total_triggers": triggers,
            "follow_rate_pct": round(follow_rate, 1),
            "avg_max_gain_pct": round(avg_max_gain, 2) if avg_max_gain is not None else None,
            "avg_ret_pct": round(avg_ret, 2) if avg_ret is not None else None,
            "win_rate_pct": round(win_rate, 1) if win_rate is not None else None,
            "summary_id": summary_id,
        })

    signals.sort(key=lambda s: (s["follow_rate_pct"], s["follow_count"]), reverse=True)

    if signals:
        headline = signals[0]["summary_id"]
    elif latest_buyers:
        lead = latest_buyers[0]
        headline = (
            f"Kemarin ({latest_day}) {lead['code']} Top Buyer {_fmt_miliar(lead['net_val_idr'])} "
            f"(history {len(days)} hari — butuh lebih banyak kejadian untuk konfirmasi pola)."
        )
    else:
        headline = f"Data broker {len(days)} hari tersimpan; belum ada akumulasi dominan kemarin."

    return {
        "history_days": len(days),
        "latest_day": latest_day,
        "top_buyers_yesterday": latest_buyers,
        "top_sellers_yesterday": latest_sellers,
        "lead_lag_signals": signals,
        "headline": headline,
    }
