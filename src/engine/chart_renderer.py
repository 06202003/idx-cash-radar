"""Zero-token PNG chart renderer for Telegram Morning Alerts (matplotlib Agg)."""

from __future__ import annotations

import io
import textwrap
from datetime import datetime, timedelta
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.engine.risk_manager import compute_risk_reward_plan


def _next_trading_date_label(last_date_str: str, trading_days_ahead: int) -> str:
    """Advances N IDX trading days (skipping Saturday & Sunday) and returns MM-DD label."""
    try:
        cur = datetime.strptime(str(last_date_str)[:10], "%Y-%m-%d").date()
    except Exception:
        return f"+{trading_days_ahead}HB"
    added = 0
    while added < trading_days_ahead:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return f"{cur.strftime('%m-%d')} (+{trading_days_ahead}HB)"


def _fmt_rp_short(val: float | None) -> str:
    if val is None:
        return "-"
    return f"Rp {int(round(val)):,}".replace(",", ".")


def render_morning_chart(
    ticker: str,
    ohlcv_df: pd.DataFrame,
    analysis_res: dict[str, Any],
    pattern_res: dict[str, Any],
    capital_idr: float = 100_000_000.0,
) -> bytes:
    """Renders a 3-panel dark-mode morning view PNG and returns raw bytes."""
    clean_t = ticker.strip().upper().replace(".JK", "")
    tech = analysis_res.get("technicals") or {}
    fc = analysis_res.get("forecast") or {}
    score = analysis_res.get("composite_score", 50.0)
    close_px = tech.get("close")
    ret_1d = float(tech.get("ret_1d_pct") or 0.0)
    low_20d = tech.get("low_20d")
    high_20d = tech.get("high_20d")
    p_up = fc.get("p_up_pct")

    bg_color = "#0f172a"
    panel_color = "#1e293b"
    text_color = "#f8fafc"
    muted_color = "#94a3b8"
    green_color = "#22c55e"
    red_color = "#ef4444"
    cyan_color = "#38bdf8"
    amber_color = "#f59e0b"

    fig = plt.figure(figsize=(8.6, 6.6), dpi=140, facecolor=bg_color)
    gs = fig.add_gridspec(3, 1, height_ratios=[2.3, 1.4, 0.95], hspace=0.34, top=0.88, bottom=0.05, left=0.09, right=0.95)

    # Header title
    ret_color = green_color if ret_1d >= 0 else red_color
    p_up_txt = f" | P(Naik 5H): {p_up:.0f}%" if p_up is not None else ""
    fig.suptitle(
        f"{clean_t}  |  {_fmt_rp_short(close_px)} ({ret_1d:+.2f}%)  |  Score {score}/100{p_up_txt}",
        color=text_color,
        fontsize=12.5,
        fontweight="bold",
        y=0.955,
    )
    fig.text(
        0.5,
        0.915,
        f"Morning Confluence View  •  Data: {tech.get('date', '-')}",
        color=muted_color,
        fontsize=8.5,
        ha="center",
    )

    # Panel 1: Price action (last 25 bars) + Key Levels
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor(panel_color)
    df_tail = ohlcv_df.tail(25).reset_index(drop=True) if not ohlcv_df.empty else pd.DataFrame()
    if not df_tail.empty:
        xs = list(range(len(df_tail)))
        closes = df_tail["close"].astype(float).tolist()
        highs = df_tail["high"].astype(float).tolist()
        lows = df_tail["low"].astype(float).tolist()

        ax1.fill_between(xs, lows, highs, color=cyan_color, alpha=0.14, label="Range H-L")
        ax1.plot(xs, closes, color=text_color, linewidth=2.0, marker="o", markersize=3, label="Close")

        if len(closes) >= 5:
            ema = df_tail["close"].astype(float).ewm(span=min(10, len(closes)), adjust=False).mean().tolist()
            ax1.plot(xs, ema, color=amber_color, linewidth=1.2, linestyle="--", alpha=0.85, label="EMA10")

        if high_20d:
            ax1.axhline(float(high_20d), color=red_color, linestyle=":", linewidth=1.1, alpha=0.85)
            ax1.text(0.2, float(high_20d), f" Resist {_fmt_rp_short(high_20d)}", color=red_color, fontsize=7.5, va="bottom")
        if low_20d:
            ax1.axhline(float(low_20d), color=green_color, linestyle=":", linewidth=1.1, alpha=0.85)
            ax1.text(0.2, float(low_20d), f" Supp {_fmt_rp_short(low_20d)}", color=green_color, fontsize=7.5, va="bottom")

        # Plot Top Buyer Avg Price if available
        top_buyers = pattern_res.get("top_buyers_yesterday") or []
        if top_buyers and top_buyers[0].get("avg_price"):
            avg_b = float(top_buyers[0]["avg_price"])
            b_code = top_buyers[0]["code"]
            ax1.axhline(avg_b, color=cyan_color, linestyle="-.", linewidth=1.1, alpha=0.9)
            ax1.text(
                max(xs) * 0.62,
                avg_b,
                f"Avg {b_code} {_fmt_rp_short(avg_b)}",
                color=cyan_color,
                fontsize=7.5,
                va="bottom",
            )

        # Plot 5-Day Forward ML Trajectory & Cone if available
        traj = fc.get("trajectory") or {}
        mid_pts = traj.get("mid") or []
        up_pts = traj.get("upper") or []
        lo_pts = traj.get("lower") or []
        if mid_pts and len(mid_pts) == len(up_pts) == len(lo_pts):
            last_x = xs[-1]
            last_c = closes[-1]
            fx = [last_x] + [last_x + k + 1 for k in range(len(mid_pts))]
            f_mid = [last_c] + [float(v) for v in mid_pts]
            f_up = [last_c] + [float(v) for v in up_pts]
            f_lo = [last_c] + [float(v) for v in lo_pts]
            t_pct = float(traj.get("target_5d_pct") or 0.0)
            f_col = green_color if t_pct >= 0 else red_color
            ax1.fill_between(fx, f_lo, f_up, color=f_col, alpha=0.18)
            ax1.plot(fx, f_mid, color=f_col, linestyle="--", linewidth=1.8, marker=".", markersize=5)
            ax1.text(
                fx[-1],
                f_mid[-1],
                f" ML+5H ({t_pct:+.1f}%)",
                color=f_col,
                fontsize=7.5,
                fontweight="bold",
                va="center",
                ha="left",
            )
            ax1.set_xlim(-0.5, fx[-1] + 4.2)

        # Sparse x-axis date ticks
        step = max(1, len(xs) // 5)
        tick_idx = xs[::step]
        tick_lbl = [str(df_tail.iloc[i]["date"])[5:10] for i in tick_idx]
        if mid_pts:
            last_d = str(df_tail.iloc[-1]["date"])[:10]
            tick_idx = tick_idx + [xs[-1] + len(mid_pts)]
            tick_lbl = tick_lbl + [_next_trading_date_label(last_d, len(mid_pts))]
        ax1.set_xticks(tick_idx)
        ax1.set_xticklabels(tick_lbl, color=muted_color, fontsize=7.5)
    else:
        ax1.text(0.5, 0.5, "Data OHLCV tidak tersedia", color=muted_color, ha="center", va="center")

    ax1.tick_params(axis="y", colors=muted_color, labelsize=7.5)
    ax1.grid(color="#334155", linestyle="--", linewidth=0.5, alpha=0.5)
    ax1.set_title("Pergerakan Harga 25 Hari & Level Kunci", color=text_color, fontsize=9.5, loc="left", pad=6)
    for spine in ax1.spines.values():
        spine.set_color("#334155")

    # Panel 2: Broker Flow (Top Buyers vs Top Sellers)
    ax2 = fig.add_subplot(gs[1])
    ax2.set_facecolor(panel_color)
    buyers = (pattern_res.get("top_buyers_yesterday") or [])[:4]
    sellers = (pattern_res.get("top_sellers_yesterday") or [])[:4]
    combined = [(b["code"], float(b["net_val_idr"]) / 1e9, green_color) for b in buyers] + [
        (s["code"], -abs(float(s["net_val_idr"])) / 1e9, red_color) for s in sellers
    ]
    if combined:
        labels = [c[0] for c in combined][::-1]
        vals = [c[1] for c in combined][::-1]
        cols = [c[2] for c in combined][::-1]
        y_pos = list(range(len(labels)))
        bars = ax2.barh(y_pos, vals, color=cols, height=0.62, alpha=0.9)
        ax2.axvline(0, color=muted_color, linewidth=0.8)
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(labels, color=text_color, fontsize=8, fontweight="bold")
        max_abs = max(abs(v) for v in vals) or 1.0
        ax2.set_xlim(-max_abs * 1.28, max_abs * 1.28)
        for bar, v in zip(bars, vals):
            ha = "left" if v >= 0 else "right"
            offset = max_abs * 0.03 if v >= 0 else -max_abs * 0.03
            lbl = f"{v:+.2f}M" if abs(v) >= 0.1 else f"{v * 1000:+.0f}Jt"
            ax2.text(v + offset, bar.get_y() + bar.get_height() / 2, lbl, va="center", ha=ha, color=text_color, fontsize=7.5)
    else:
        ax2.text(0.5, 0.5, "Belum ada data broksum (token Stockbit perlu aktif)", color=muted_color, ha="center", va="center", fontsize=8.5)

    ax2.tick_params(axis="x", colors=muted_color, labelsize=7.5)
    ax2.grid(axis="x", color="#334155", linestyle="--", linewidth=0.5, alpha=0.5)
    day_lbl = pattern_res.get("latest_day") or "Terbaru"
    ax2.set_title(f"Top Net Buyer vs Seller ({day_lbl})", color=text_color, fontsize=9.5, loc="left", pad=6)
    for spine in ax2.spines.values():
        spine.set_color("#334155")

    # Panel 3: Pattern & Action Callout
    ax3 = fig.add_subplot(gs[2])
    ax3.set_facecolor("#172554")
    ax3.set_xticks([])
    ax3.set_yticks([])
    for spine in ax3.spines.values():
        spine.set_color(cyan_color)
        spine.set_linewidth(1.0)

    headline = pattern_res.get("headline") or "-"
    wrapped_headline = "\n".join(textwrap.wrap(f"POLA BROKER: {headline}", width=82))

    rr_line = ""
    if close_px and low_20d and high_20d:
        plan = compute_risk_reward_plan(
            entry_price=float(close_px),
            support_price=float(low_20d),
            resistance_price=float(high_20d),
            capital_idr=capital_idr,
        )
        if plan:
            rr_line = (
                f"PATOKAN: Entry {_fmt_rp_short(plan['entry'])} | "
                f"SL {_fmt_rp_short(plan['stop_loss'])} | TP {_fmt_rp_short(plan['take_profit'])} "
                f"(RR {plan['rr_ratio']:.1f}x, {plan['recommended_lots']} lot)"
            )

    full_box = wrapped_headline + (f"\n{rr_line}" if rr_line else "")
    ax3.text(0.02, 0.5, full_box, color=text_color, fontsize=8.3, va="center", ha="left", linespacing=1.4)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=bg_color)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_ascii_bar_chart(
    ticker: str,
    prices: list[float],
    labels: list[str] | None = None,
    width: int = 16,
    height: int = 5,
    subtitle: str = "Intraday",
) -> str:
    """
    Renders a clean solid-block ASCII/Unicode bar chart using single-backtick monospace lines
    (no triple-backtick COPY CODE box on Telegram mobile).
    """
    clean_t = ticker.strip().upper().replace(".JK", "")
    valid = [float(p) for p in prices if p is not None and float(p) > 0]
    if len(valid) < 2:
        return f"📈 *{clean_t}* — Data grafik belum cukup."

    if len(valid) > width:
        sampled = [valid[int(round(i * (len(valid) - 1) / (width - 1)))] for i in range(width)]
    else:
        sampled = valid

    lo = min(sampled)
    hi = max(sampled)
    span = hi - lo if hi > lo else max(1.0, hi * 0.01)

    # Use half-step resolution (height * 2) with █ (full) and ▄ (bottom half)
    max_units = height * 2
    units = [
        max(1, min(max_units, int(round((p - lo) / span * (max_units - 1))) + 1))
        for p in sampled
    ]

    def _px_s(v: float) -> str:
        return f"{int(round(v)):,}".replace(",", ".")

    hi_s = _px_s(hi)
    mid_s = _px_s((hi + lo) / 2.0)
    lo_s = _px_s(lo)
    pad_w = max(len(hi_s), len(mid_s), len(lo_s))
    mid_row = height // 2

    lines = []
    for r in range(height):
        level_bot = (height - 1 - r) * 2
        row_chars = []
        for u in units:
            if u >= level_bot + 2:
                row_chars.append("█")
            elif u == level_bot + 1:
                row_chars.append("▄")
            else:
                row_chars.append(" ")
        if r == 0:
            axis = hi_s.rjust(pad_w) + " |"
        elif r == mid_row:
            axis = mid_s.rjust(pad_w) + " |"
        elif r == height - 1:
            axis = lo_s.rjust(pad_w) + " |"
        else:
            axis = (" " * pad_w) + " |"
        lines.append(f"`{axis}{''.join(row_chars)}`")

    t_start = labels[0] if labels and len(labels) >= 1 else "Open"
    t_end = labels[-1] if labels and len(labels) >= 2 else "Now"
    cols = len(sampled)
    gap = max(1, cols - len(t_start) - len(t_end))
    footer = (" " * (pad_w + 2)) + t_start + (" " * gap) + t_end
    lines.append(f"`{footer}`")

    first_px, last_px = valid[0], valid[-1]
    chg = ((last_px / first_px) - 1.0) * 100.0 if first_px > 0 else 0.0
    header = f"📊 *{clean_t} {subtitle}* | `{_px_s(last_px)}` (`{chg:+.2f}%`)"
    return header + "\n" + "\n".join(lines)


def render_sparkline_line(
    ticker: str,
    prices: list[float],
    subtitle: str = "Intraday",
    width: int = 18,
) -> str:
    """Renders a clean 1-line Unicode sparkline (no code block, no COPY CODE button on mobile)."""
    clean_t = ticker.strip().upper().replace(".JK", "")
    valid = [float(p) for p in prices if p is not None and float(p) > 0]
    if len(valid) < 2:
        return f"📈 *{clean_t}* — Data grafik belum cukup."

    if len(valid) > width:
        sampled = [valid[int(round(i * (len(valid) - 1) / (width - 1)))] for i in range(width)]
    else:
        sampled = valid

    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(sampled), max(sampled)
    span = hi - lo if hi > lo else 1.0
    spark = "".join(blocks[min(7, max(0, int((p - lo) / span * 7)))] for p in sampled)

    first_px, last_px = valid[0], valid[-1]
    chg = ((last_px / first_px) - 1.0) * 100.0 if first_px > 0 else 0.0
    return (
        f"📈 *{clean_t} {subtitle}:* `{spark}`\n"
        f"   Now `{_fmt_rp_short(last_px)}` (`{chg:+.2f}%`) | Range `{_fmt_rp_short(lo)}`–`{_fmt_rp_short(hi)}`"
    )


def render_intraday_png(
    ticker: str,
    prices: list[float],
    labels: list[str] | None = None,
    subtitle: str = "Intraday",
) -> bytes:
    """Renders a sleek dark-mode PNG price chart for /chart command (0 AI tokens)."""
    clean_t = ticker.strip().upper().replace(".JK", "")
    valid = [float(p) for p in prices if p is not None and float(p) > 0]

    bg = "#0f172a"
    panel = "#1e293b"
    txt = "#f8fafc"
    muted = "#94a3b8"
    first_px = valid[0] if valid else 0.0
    last_px = valid[-1] if valid else 0.0
    chg = ((last_px / first_px) - 1.0) * 100.0 if first_px > 0 else 0.0
    accent = "#22c55e" if chg >= 0 else "#ef4444"

    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=140, facecolor=bg)
    fig.subplots_adjust(left=0.12, right=0.95, top=0.82, bottom=0.14)
    ax.set_facecolor(panel)

    if len(valid) >= 2:
        xs = list(range(len(valid)))
        lo, hi = min(valid), max(valid)
        ax.plot(xs, valid, color=accent, linewidth=2.4)
        ax.fill_between(xs, valid, lo, color=accent, alpha=0.16)
        ax.scatter([xs[-1]], [last_px], color=accent, s=45, zorder=5)
        ax.axhline(first_px, color=muted, linestyle=":", linewidth=0.9, alpha=0.7)
        if labels and len(labels) >= 2:
            ax.set_xticks([0, len(valid) - 1])
            ax.set_xticklabels([labels[0], labels[-1]], color=muted, fontsize=8.5)
        else:
            ax.set_xticks([])
        pad = max(1.0, (hi - lo) * 0.14)
        ax.set_ylim(lo - pad, hi + pad)
    else:
        ax.text(0.5, 0.5, "Data grafik tidak cukup", color=muted, ha="center", va="center")
        ax.set_xticks([])

    ax.tick_params(axis="y", colors=muted, labelsize=8.5)
    ax.grid(color="#334155", linestyle="--", linewidth=0.5, alpha=0.5)
    for spine in ax.spines.values():
        spine.set_color("#334155")

    fig.suptitle(
        f"{clean_t} {subtitle}  |  {_fmt_rp_short(last_px)} ({chg:+.2f}%)",
        color=txt,
        fontsize=12,
        fontweight="bold",
        y=0.93,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=bg)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
