"""Zero-token PNG chart renderer for Telegram Morning Alerts (matplotlib Agg)."""

from __future__ import annotations

import io
import textwrap
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.engine.risk_manager import compute_risk_reward_plan


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

        # Sparse x-axis date ticks
        step = max(1, len(xs) // 5)
        tick_idx = xs[::step]
        tick_lbl = [str(df_tail.iloc[i]["date"])[5:10] for i in tick_idx]
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


def render_ascii_intraday_chart(
    ticker: str,
    prices: list[float],
    labels: list[str] | None = None,
    width: int = 24,
    height: int = 6,
    subtitle: str = "Intraday",
) -> str:
    """
    Renders a compact mobile-safe Unicode box-drawing chart (<= 38 chars wide)
    inside a Telegram Markdown monospace block.
    """
    clean_t = ticker.strip().upper().replace(".JK", "")
    valid = [float(p) for p in prices if p is not None and float(p) > 0]
    if len(valid) < 2:
        return f"📈 *{clean_t}* — Data grafik belum cukup."

    # Resample evenly to `width` points so it never wraps on mobile Telegram
    if len(valid) > width:
        sampled = [valid[int(round(i * (len(valid) - 1) / (width - 1)))] for i in range(width)]
    else:
        sampled = valid

    cols = len(sampled)
    lo = min(sampled)
    hi = max(sampled)
    span = hi - lo if hi > lo else max(1.0, hi * 0.01)

    # Map each price to row index [0 .. height - 1] (0 = top, height - 1 = bottom)
    rows_idx = [
        max(0, min(height - 1, height - 1 - int(round((p - lo) / span * (height - 1)))))
        for p in sampled
    ]

    grid = [[" " for _ in range(cols)] for _ in range(height)]
    for x in range(cols):
        y = rows_idx[x]
        if x == 0:
            grid[y][x] = "─"
            continue
        prev_y = rows_idx[x - 1]
        if y == prev_y:
            grid[y][x] = "─"
        elif y < prev_y:
            # Going up
            grid[prev_y][x] = "╯"
            for mid_y in range(y + 1, prev_y):
                grid[mid_y][x] = "│"
            grid[y][x] = "╭"
        else:
            # Going down
            grid[prev_y][x] = "╮"
            for mid_y in range(prev_y + 1, y):
                grid[mid_y][x] = "│"
            grid[y][x] = "╰"

    def _px_s(v: float) -> str:
        return f"{int(round(v)):,}".replace(",", ".")

    hi_s = _px_s(hi)
    mid_s = _px_s((hi + lo) / 2.0)
    lo_s = _px_s(lo)
    pad_w = max(len(hi_s), len(mid_s), len(lo_s))
    mid_row = height // 2

    lines = []
    for r in range(height):
        if r == 0:
            axis = hi_s.rjust(pad_w) + " ┤"
        elif r == mid_row:
            axis = mid_s.rjust(pad_w) + " ┤"
        elif r == height - 1:
            axis = lo_s.rjust(pad_w) + " ┼"
        else:
            axis = (" " * pad_w) + " │"
        lines.append(axis + "".join(grid[r]))

    first_px = valid[0]
    last_px = valid[-1]
    chg_pct = ((last_px / first_px) - 1.0) * 100.0 if first_px > 0 else 0.0

    t_start = labels[0] if labels else "Start"
    t_end = labels[-1] if labels else "Now"
    footer_pad = " " * (pad_w + 2)
    gap = max(1, cols - len(t_start) - len(t_end))
    lines.append(footer_pad + t_start + (" " * gap) + t_end)

    header = f"📈 *{clean_t} {subtitle}* | `{_px_s(last_px)}` (`{chg_pct:+.2f}%`)"
    return header + "\n```\n" + "\n".join(lines) + "\n```"
