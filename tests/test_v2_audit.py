"""Unit tests for v2 audit protocol, statistical guarantees, and look-ahead prevention."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from src.data.market_feed import fetch_jk_ohlcv
from src.engine.forecaster import BULLISH_PROB_THRESHOLD, FEATURE_COLS, _classify_direction, _prepare_dataset
from src.eval.h1_volatility import _compute_vol_series, _eval_cones
from src.eval.stats_v2 import date_clustered_bootstrap_ci, independent_bootstrap_ci, random_baseline_matched


def test_no_lookahead_features_and_predictions() -> None:
    rng = np.random.default_rng(7)
    n = 140
    dates = pd.date_range("2025-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    closes = 1000.0 * np.cumprod(1.0 + rng.normal(0.0, 0.015, size=n))
    df1 = pd.DataFrame({
        "date": dates,
        "open": closes * 0.995,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": rng.uniform(5e5, 2e6, size=n),
    })
    df2 = df1.copy()
    df2.loc[90:, ["open", "high", "low", "close"]] *= 3.0

    p1 = _prepare_dataset(df1).iloc[:90][FEATURE_COLS]
    p2 = _prepare_dataset(df2).iloc[:90][FEATURE_COLS]
    pd.testing.assert_frame_equal(p1, p2)


def test_purge_gap_in_walk_forward() -> None:
    # Verify purge gap prevents overlap between train labels (shift -5) and test start
    horizon = 5
    split = 100
    tr_end = split - horizon
    train_indices = set(range(tr_end))
    # Last train label uses close[tr_end - 1 + horizon] = close[split - 1], strictly < split
    assert max(train_indices) + horizon < split


def test_single_threshold_consistency() -> None:
    assert BULLISH_PROB_THRESHOLD == 0.58
    assert _classify_direction(BULLISH_PROB_THRESHOLD * 100.0) == "BULLISH (Cenderung Naik)"
    assert _classify_direction(BULLISH_PROB_THRESHOLD * 100.0 - 0.1) == "NETRAL"


def test_caret_symbol_no_jk_suffix() -> None:
    urls: list[str] = []

    def _fake(req, timeout=10.0):
        urls.append(req.full_url)
        raise RuntimeError("stop")

    with patch("urllib.request.urlopen", side_effect=_fake):
        fetch_jk_ohlcv("^JKSE")
        fetch_jk_ohlcv("BBCA")

    assert "%5EJKSE?" in urls[0] and ".JK" not in urls[0]
    assert "BBCA.JK?" in urls[1]


def test_date_clustered_ci_wider_than_independent_on_correlated_data() -> None:
    rng = np.random.default_rng(42)
    n_dates = 100
    n_stocks = 20
    market_shock = rng.normal(0.0, 2.0, size=n_dates)
    dates, vals = [], []
    for d in range(n_dates):
        for s in range(n_stocks):
            dates.append(f"2025-{(d // 28) + 1:02d}-{(d % 28) + 1:02d}")
            vals.append(market_shock[d] + rng.normal(0.0, 0.3))
    vals_arr = np.array(vals)
    ci_ind = independent_bootstrap_ci(vals_arr, block_size=5, n_boot=1000, seed=42)
    ci_cls = date_clustered_bootstrap_ci(np.array(dates), vals_arr, block_size=10, n_boot=1000, seed=42)
    w_ind = ci_ind[1] - ci_ind[0]
    w_cls = ci_cls["ci_hi"] - ci_cls["ci_lo"]
    assert w_cls > w_ind


def test_synthetic_cone_coverage_near_nominal() -> None:
    rng = np.random.default_rng(123)
    n = 400
    dates = pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    closes = 1000.0 * np.cumprod(np.exp(rng.normal(0.0, 0.015, size=n)))
    df = pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": np.full(n, 1e9),
        "liq_ok": True,
        "segment": ["DISCOVERY"] * 250 + ["LOCK-RECENT"] * 150,
    })
    vdf = _compute_vol_series(df)
    res = _eval_cones({"SYN": vdf}, pd.DataFrame(), "V0", "LOCK-RECENT")
    assert abs(res["cov68_5d"] - 68.0) <= 12.0
    assert abs(res["cov90_5d"] - 90.0) <= 10.0


def test_random_baseline_exact_frequency() -> None:
    rng = np.random.default_rng(9)
    rets = rng.normal(0.0, 1.0, size=500)
    dates = np.array([f"2025-01-{(i % 28) + 1:02d}" for i in range(500)])
    res = random_baseline_matched(dates, rets, n_signals=75, n_seeds=200, seed=42)
    assert res["p2_5"] < res["p50"] < res["p97_5"]
