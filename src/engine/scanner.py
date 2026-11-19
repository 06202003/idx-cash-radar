"""Confluence scanner combining direction forecast, news sentiment, technicals, and cash safety."""

from __future__ import annotations

from typing import Any

from src.data.fundamental_client import fetch_cash_radar_map
from src.data.market_feed import fetch_jk_ohlcv
from src.data.news_feed import fetch_latest_news
from src.data.stockbit_feed import (
    StockbitAuthError,
    fetch_stockbit_broker_summary,
    fetch_stockbit_daily,
)
from src.data.stockbit_token_manager import load_active_token, refresh_token_via_playwright
from src.engine.forecaster import forecast_direction_with_backtest
from src.engine.indicators import compute_indicators, summarize_latest_technicals
from src.engine.risk_manager import compute_risk_reward_plan, format_risk_reward_block


def _fetch_stockbit_context(ticker: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, bool]:
    """Fetches Stockbit broker summary & daily quote, auto-refreshing via Playwright once on 401."""
    tok = load_active_token()
    if not tok:
        return None, None, False
    for attempt in range(2):
        try:
            broksum = fetch_stockbit_broker_summary(ticker, token=tok)
            daily = fetch_stockbit_daily(ticker, token=tok)
            return broksum, daily, False
        except StockbitAuthError:
            if attempt == 0:
                refreshed = refresh_token_via_playwright(headless=True)
                if refreshed:
                    tok = refreshed
                    continue
            return None, None, True
        except Exception:
            return None, None, False
    return None, None, False


def analyze_ticker(ticker: str, cash_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Runs full technical + Stockbit broker summary + direction forecast + news + cash check."""
    clean_t = ticker.strip().upper().replace(".JK", "")
    broksum, sb_daily, auth_expired = _fetch_stockbit_context(clean_t)
    df = fetch_jk_ohlcv(clean_t, range_str="2y")
    ind_df = compute_indicators(df) if not df.empty else df
    tech = summarize_latest_technicals(ind_df)
    forecast = forecast_direction_with_backtest(df)
    news = fetch_latest_news(clean_t, max_items=3)

    if cash_map is None:
        cash_map = fetch_cash_radar_map()
    funda = cash_map.get(clean_t)

    top_news = news[0] if news else None
    news_sent = top_news["sentiment"] if top_news else "NETRAL"

    # Overall composite sentiment score (ML direction + news + fundamental safety)
    score = float(forecast.get("p_up_pct") or 50.0)
    if news_sent == "POSITIF":
        score += 5.0
    elif news_sent == "PERHATIAN":
        score -= 8.0

    funda_safe = True
    if funda:
        if funda.get("flag_acute_liquidity") or funda.get("flag_accrual_divergence"):
            funda_safe = False
            score -= 10.0

    score = max(min(round(score, 1), 99.0), 1.0)
    if score >= 60.0 and funda_safe:
        badge = "🟢 SENTIMEN NAIK"
    elif score <= 42.0 or not funda_safe:
        badge = "🔴 WASPADA / TURUN"
    else:
        badge = "🟡 NETRAL"

    return {
        "ticker": clean_t,
        "badge": badge,
        "composite_score": score,
        "technicals": tech,
        "stockbit_broksum": broksum,
        "stockbit_daily": sb_daily,
        "stockbit_auth_expired": auth_expired,
        "forecast": forecast,
        "news": news,
        "fundamental": funda,
        "funda_safe": funda_safe,
    }


def format_ticker_alert(res: dict[str, Any], capital_idr: float = 100_000_000.0) -> str:
    """Formats analysis result into a crisp 3-second scannable Telegram alert card."""
    t = res["ticker"]
    tech = res.get("technicals") or {}
    fc = res.get("forecast") or {}
    news = res.get("news") or []
    funda = res.get("fundamental")

    def _fmt_rp(v: Any) -> str:
        return f"Rp {int(round(float(v))):,}".replace(",", ".") if v else "-"

    price_str = _fmt_rp(tech.get("close"))
    low20_str = _fmt_rp(tech.get("low_20d"))
    high20_str = _fmt_rp(tech.get("high_20d"))
    ret1 = tech.get("ret_1d_pct", 0.0)
    rsi = tech.get("rsi14")
    vol_r = tech.get("vol_ratio_20d", 1.0)
    trend = tech.get("trend", "-")
    bar_date = tech.get("date", "-")

    lines = [
        f"🔥 *ALERT RADAR | {t} | {res['badge']}*",
        "",
        f"⏰ *Data:* `{bar_date}` _(delay ±5-15m)_",
        f"💵 *Harga:* `{price_str}` (`{ret1:+.2f}%` 1D)",
        f"📊 *Volume:* `{vol_r}x` rata-rata 20H | *RSI:* `{rsi}`",
        "",
        "📐 *LEVEL HARGA & TREN (20H):*",
        f"• Support 20H: `{low20_str}`",
        f"• Resistance 20H: `{high20_str}`",
        f"• Tren: {trend}",
    ]

    if tech.get("spike_chase_warning"):
        lines.append("⚠️ *Catatan:* Volume ≥ 3x disertai kenaikan ≥ 3% (hindari mengejar harga).")

    rr_plan = compute_risk_reward_plan(
        entry_price=float(tech.get("close") or 0.0),
        support_price=float(tech.get("low_20d") or 0.0) or None,
        resistance_price=float(tech.get("high_20d") or 0.0) or None,
        capital_idr=capital_idr,
    )
    if rr_plan:
        lines.extend(format_risk_reward_block(rr_plan))

    lines.extend([
        "",
        "🎯 *FORECAST 5H & BACKTEST OOS:*",
        f"• Arah: *{fc.get('direction', 'NETRAL')}* (P(Naik): `{fc.get('p_up_pct', 50.0)}%` | Skor: `{res['composite_score']}%`)",
    ])

    if fc.get("oos_sample_count", 0) > 0:
        win_s = f"{fc['oos_bullish_win_rate_pct']}%" if fc.get("oos_bullish_win_rate_pct") is not None else "N/A"
        net_s = f"{fc['oos_bullish_avg_net_ret_pct']:+.2f}%" if fc.get("oos_bullish_avg_net_ret_pct") is not None else "N/A"
        lines.append(
            f"• OOS ({fc['oos_sample_count']}H): Akurasi `{fc.get('oos_accuracy_pct')}%` | "
            f"Win-rate `{win_s}` | Avg Net `{net_s}`"
        )

    if funda:
        cov_disp = funda.get("cash_coverage_display") or "-"
        sloan = funda.get("sloan_ratio_pct")
        status_lbl = funda.get("status_label") or "-"
        lines.append(f"🏦 *Kas XBRL:* {status_lbl} | Coverage `{cov_disp}` | Sloan `{sloan}%`")

    broksum = res.get("stockbit_broksum")
    if broksum:
        buys = ", ".join(broksum.get("buyer_codes") or []) or "-"
        sells = ", ".join(broksum.get("seller_codes") or []) or "-"
        lines.append(
            f"🤝 *Broksum Stockbit:* {broksum.get('bandar_action', '-')} | "
            f"Buy `{buys}` | Sell `{sells}`"
        )
    elif res.get("stockbit_auth_expired"):
        lines.append("🔑 *Stockbit:* Token expired — kirim `/settoken` untuk refresh.")

    if news:
        top = news[0]
        lines.append(f"📰 *Berita ({top['date']}):* {top['headline']}")

    return "\n".join(lines)
