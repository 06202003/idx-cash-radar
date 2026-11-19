"""Tests for technical indicators and volume spike warnings."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.engine.indicators import compute_indicators, summarize_latest_technicals


def test_indicators_and_spike_warning() -> None:
    dates = pd.date_range("2025-01-01", periods=80, freq="B").strftime("%Y-%m-%d")
    closes = np.linspace(1000.0, 1200.0, 80)
    closes[-1] = closes[-2] * 1.05  # +5% jump on last day
    vols = np.full(80, 1_000_000.0)
    vols[-1] = 4_000_000.0  # 4x volume spike

    df = pd.DataFrame({
        "date": dates,
        "open": closes * 0.99,
        "high": closes * 1.01,
        "low": closes * 0.98,
        "close": closes,
        "volume": vols,
    })

    ind = compute_indicators(df)
    summary = summarize_latest_technicals(ind)
    assert summary["spike_chase_warning"] is True
    assert "UPTREND" in summary["trend"]
    assert summary["rsi14"] is not None
    assert summary["vol_ratio_20d"] >= 3.0
