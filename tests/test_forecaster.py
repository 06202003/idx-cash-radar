"""Tests for walk-forward ML direction forecaster."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.engine.forecaster import forecast_direction_with_backtest


def test_forecaster_walk_forward_outputs() -> None:
    rng = np.random.default_rng(7)
    n = 260
    dates = pd.date_range("2025-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    rets = rng.normal(0.001, 0.018, size=n)
    closes = 2000.0 * np.cumprod(1.0 + rets)
    vols = rng.uniform(500_000, 2_000_000, size=n)

    df = pd.DataFrame({
        "date": dates,
        "open": closes * 0.995,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": vols,
    })

    res = forecast_direction_with_backtest(df)
    assert res["status"] == "ok"
    assert 0.0 <= res["p_up_pct"] <= 100.0
    assert 0.0 <= res["p_up_raw_pct"] <= 100.0
    assert res["direction"] in ("BULLISH (Cenderung Naik)", "BEARISH (Cenderung Turun)", "NETRAL")
    assert isinstance(res["direction_confirmed"], bool)
    assert res["holding_guidance"]
    assert res["oos_sample_count"] > 0
    assert res["oos_accuracy_pct"] is not None
    if res["oos_bullish_signals"] > 0:
        assert res["oos_recommended_strategy"] in ("HOLD_5D", "EXIT_ON_FLIP")


def test_forecaster_insufficient_data_guard() -> None:
    df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"],
        "open": [1000.0, 1010.0],
        "high": [1020.0, 1020.0],
        "low": [990.0, 1000.0],
        "close": [1010.0, 1015.0],
        "volume": [100000.0, 120000.0],
    })
    res = forecast_direction_with_backtest(df)
    assert res["status"] == "insufficient_data"
    assert res["direction"] == "NETRAL"


def test_no_lookahead_in_features() -> None:
    rng = np.random.default_rng(11)
    n = 120
    dates = pd.date_range("2025-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    closes = 1000.0 * np.cumprod(1.0 + rng.normal(0.0, 0.015, size=n))
    df1 = pd.DataFrame({
        "date": dates,
        "open": closes * 0.995,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": rng.uniform(1e5, 1e6, size=n),
    })
    df2 = df1.copy()
    df2.loc[80:, "close"] *= 2.5
    df2.loc[80:, "high"] *= 2.5
    df2.loc[80:, "low"] *= 2.5

    from src.engine.forecaster import FEATURE_COLS, _prepare_dataset

    p1 = _prepare_dataset(df1).iloc[:80][FEATURE_COLS]
    p2 = _prepare_dataset(df2).iloc[:80][FEATURE_COLS]
    pd.testing.assert_frame_equal(p1, p2)


def test_single_threshold_and_caret_symbol() -> None:
    from unittest.mock import patch
    from src.data.market_feed import fetch_jk_ohlcv
    from src.engine.forecaster import BULLISH_PROB_THRESHOLD, _classify_direction

    assert _classify_direction(BULLISH_PROB_THRESHOLD * 100.0) == "BULLISH (Cenderung Naik)"
    assert _classify_direction(BULLISH_PROB_THRESHOLD * 100.0 - 0.1) == "NETRAL"

    captured_urls: list[str] = []

    def _fake_urlopen(req, timeout=10.0):
        captured_urls.append(req.full_url)
        raise RuntimeError("stop")

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        fetch_jk_ohlcv("^JKSE")
        fetch_jk_ohlcv("BBCA")

    assert "%5EJKSE?" in captured_urls[0]
    assert ".JK" not in captured_urls[0]
    assert "BBCA.JK?" in captured_urls[1]
