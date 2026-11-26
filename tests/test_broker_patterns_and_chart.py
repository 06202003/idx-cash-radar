"""Tests for broker daily history storage, lead-lag pattern engine, and PNG chart renderer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.db.store import AlertStore
from src.engine.broker_patterns import analyze_broker_patterns
from src.engine.chart_renderer import render_ascii_bar_chart, render_morning_chart, render_sparkline_line


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.date_range("2026-11-01", periods=25, freq="B")
    rows = []
    px = 1000.0
    for i, d in enumerate(dates):
        o = px
        c = px + (20.0 if i % 2 == 0 else -5.0)
        h = max(o, c) + 25.0
        l = min(o, c) - 15.0
        rows.append({"date": d.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c, "volume": 1_000_000})
        px = c
    return pd.DataFrame(rows)


def test_broker_history_and_lead_lag_xl_to_xc(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "test_broker.db")
    ohlcv = _sample_ohlcv()
    days = ohlcv["date"].tolist()[:6]

    # Simulate 3 historical pairs where XL net buys on day T-1 and XC follows on day T
    for i in (0, 2):
        store.upsert_broker_daily(
            days[i],
            "BBRI",
            [
                {"broker_code": "XL", "broker_type": "Lokal", "side": "BUY", "net_val_idr": 3_500_000_000, "net_lot": 30000, "avg_price": 1010},
                {"broker_code": "YP", "broker_type": "Lokal", "side": "SELL", "net_val_idr": -2_000_000_000, "net_lot": -18000, "avg_price": 1015},
            ],
        )
        store.upsert_broker_daily(
            days[i + 1],
            "BBRI",
            [
                {"broker_code": "XC", "broker_type": "Lokal", "side": "BUY", "net_val_idr": 2_800_000_000, "net_lot": 25000, "avg_price": 1020},
                {"broker_code": "CC", "broker_type": "Lokal", "side": "SELL", "net_val_idr": -1_500_000_000, "net_lot": -13000, "avg_price": 1025},
            ],
        )

    # Latest day (yesterday): XL enters heavily again
    store.upsert_broker_daily(
        days[4],
        "BBRI",
        [
            {"broker_code": "XL", "broker_type": "Lokal", "side": "BUY", "net_val_idr": 4_200_000_000, "net_lot": 38000, "avg_price": 1030},
            {"broker_code": "PD", "broker_type": "Lokal", "side": "SELL", "net_val_idr": -2_100_000_000, "net_lot": -19000, "avg_price": 1035},
        ],
    )

    assert len(store.list_broker_history_days("BBRI", lookback_days=60)) == 5
    hist = store.get_broker_daily_history("BBRI", lookback_days=60)
    pat = analyze_broker_patterns(hist, ohlcv_df=ohlcv)

    assert pat["history_days"] == 5
    assert pat["latest_day"] == days[4]
    assert len(pat["lead_lag_signals"]) >= 1
    top_sig = pat["lead_lag_signals"][0]
    assert top_sig["lead_broker"] == "XL"
    assert top_sig["follow_broker"] == "XC"
    assert top_sig["follow_count"] == 2
    assert top_sig["total_triggers"] == 2
    assert top_sig["follow_rate_pct"] == 100.0
    assert "XL" in pat["headline"] and "XC" in pat["headline"]


def test_render_morning_chart_outputs_valid_png(tmp_path: Path) -> None:
    ohlcv = _sample_ohlcv()
    analysis_res = {
        "ticker": "BBRI",
        "badge": "🟢 SENTIMEN NAIK",
        "composite_score": 72.5,
        "technicals": {
            "date": ohlcv["date"].iloc[-1],
            "close": float(ohlcv["close"].iloc[-1]),
            "ret_1d_pct": 1.85,
            "low_20d": 990.0,
            "high_20d": 1220.0,
            "atr14": 25.0,
        },
        "forecast": {
            "p_up_pct": 66.0,
            "trajectory": {
                "mid": [1210.0, 1220.0, 1225.0, 1235.0, 1245.0],
                "upper": [1230.0, 1250.0, 1265.0, 1280.0, 1295.0],
                "lower": [1190.0, 1190.0, 1185.0, 1190.0, 1195.0],
                "target_5d_pct": 3.75,
            },
        },
    }
    pattern_res = {
        "latest_day": "2026-11-19",
        "top_buyers_yesterday": [
            {"code": "XL", "net_val_idr": 4_200_000_000, "avg_price": 1150.0},
            {"code": "XC", "net_val_idr": 2_100_000_000, "avg_price": 1145.0},
        ],
        "top_sellers_yesterday": [
            {"code": "YP", "net_val_idr": -2_900_000_000, "avg_price": 1155.0},
        ],
        "headline": "XL masuk Rp 4.2M (2026-11-19) -> historis 2/2x (100%) XC ikut masuk di H+1",
    }

    png_bytes = render_morning_chart("BBRI", ohlcv, analysis_res, pattern_res, capital_idr=100_000_000.0)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png_bytes) > 10_000


def test_render_sparkline_and_ascii_bar_chart() -> None:
    prices = [3840, 3850, 3870, 3860, 3890, 3910, 3900, 3880, 3895, 3920]
    spark = render_sparkline_line("BMRI", prices, subtitle="Intraday")
    assert "BMRI Intraday" in spark
    assert "```" not in spark
    assert "▁" in spark and "█" in spark

    bar = render_ascii_bar_chart("BMRI", prices, labels=["09:00", "14:50"], subtitle="Intraday")
    assert "BMRI Intraday" in bar
    assert "```" not in bar
    assert "█" in bar


def test_stockbit_intraday_sorts_descending_and_slices_session(monkeypatch) -> None:
    from src.data import stockbit_feed
    from src.bot import main as bot_main

    fake_payload = {
        "data": {
            "previous": 5825,
            "chartbit": [
                {"date": "2026-11-26 15:00:00", "close": 5925, "unixdate": 1795680000},
                {"date": "2026-11-26 14:00:00", "close": 5900, "unixdate": 1795676400},
                {"date": "2026-11-26 10:00:00", "close": 5875, "unixdate": 1795662000},
                {"date": "2026-11-26 09:00:00", "close": 5850, "unixdate": 1795658400},
                {"date": "2026-11-25 15:50:00", "close": 5825, "unixdate": 1795596600},
            ],
        }
    }
    monkeypatch.setattr(stockbit_feed, "_get_json", lambda url, tok: fake_payload)
    df = stockbit_feed.fetch_stockbit_intraday("BBCA", token="dummy", lookback_days=2)
    assert df["close"].tolist() == [5825.0, 5850.0, 5875.0, 5900.0, 5925.0]
    assert df.attrs.get("previous_close") == 5825.0

    monkeypatch.setattr(bot_main, "load_active_token", lambda: "dummy")
    monkeypatch.setattr(bot_main, "fetch_stockbit_intraday", lambda *a, **kw: df)
    prices, labels, subtitle, prev_close = bot_main._fetch_chart_data("BBCA")
    assert prices == [5850.0, 5875.0, 5900.0, 5925.0]
    assert labels == ["09:00", "15:00"]
    assert subtitle == "Intraday"
    assert prev_close == 5825.0

    spark = render_sparkline_line("BBCA", prices, subtitle=subtitle, prev_close=prev_close)
    assert "+1.72%" in spark

