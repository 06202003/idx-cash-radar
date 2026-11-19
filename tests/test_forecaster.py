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
    assert res["direction"] in ("BULLISH (Cenderung Naik)", "BEARISH (Cenderung Turun)", "NETRAL")
    assert res["oos_sample_count"] > 0
    assert res["oos_accuracy_pct"] is not None


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
