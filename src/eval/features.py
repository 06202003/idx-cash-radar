"""Causal feature engineering for walk-forward evaluation (no look-ahead)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import ROUND_TRIP_FEE
from src.engine.indicators import compute_indicators

ORIG_FEATURES: list[str] = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "dist_ma20",
    "dist_ma50",
    "rsi14",
    "vol_ratio_log",
    "volatility_20d",
]

EXTRA_OHLCV_FEATURES: list[str] = [
    "bar_pos",
    "atr14_pct",
    "pos_20d",
    "ma20_slope5",
    "signed_vol_5d",
]

IHSG_FEATURES: list[str] = [
    "jkse_ret_5d",
    "rel_str_5d",
    "jkse_above_ma50",
]


def prepare_eval_dataframe(
    df: pd.DataFrame,
    jkse_df: pd.DataFrame | None = None,
    horizon_days: int = 5,
    fee: float = ROUND_TRIP_FEE,
) -> pd.DataFrame:
    """
    Computes strictly causal features up to bar t, and forward label shift(-horizon_days).
    Every rolling/diff indicator depends only on bars <= t.
    """
    ind = compute_indicators(df)
    c = ind["close"].astype(float)
    h = ind["high"].astype(float)
    l = ind["low"].astype(float)
    v = ind["volume"].astype(float)
    rng = (h - l).replace(0.0, np.nan)

    ind["vol_ratio_log"] = np.log1p(ind["vol_ratio_20d"].clip(lower=0.0))
    ind["bar_pos"] = ((c - l) / rng).fillna(0.5)
    ind["atr14_pct"] = (rng.rolling(14, min_periods=14).mean() / c.replace(0.0, np.nan)).fillna(0.0)
    ind["pos_20d"] = ((c - ind["low_20d"]) / (ind["high_20d"] - ind["low_20d"]).replace(0.0, np.nan)).fillna(0.5)
    ind["ma20_slope5"] = ind["ma20"].pct_change(5).fillna(0.0)

    signed_v = np.sign(c.diff().fillna(0.0)) * v
    vol_denom = (v.rolling(20, min_periods=20).mean() * 5.0).replace(0.0, np.nan)
    ind["signed_vol_5d"] = (signed_v.rolling(5, min_periods=5).sum() / vol_denom).fillna(0.0)

    if jkse_df is not None and not jkse_df.empty:
        j = jkse_df[["date", "close"]].copy()
        jc = j["close"].astype(float)
        j["jkse_ret_5d"] = jc.pct_change(5)
        j_ma50 = jc.rolling(50, min_periods=50).mean()
        j["jkse_above_ma50"] = (jc > j_ma50).astype(float)
        ind = ind.merge(j[["date", "jkse_ret_5d", "jkse_above_ma50"]], on="date", how="left")
        ind["jkse_ret_5d"] = ind["jkse_ret_5d"].ffill().fillna(0.0)
        ind["jkse_above_ma50"] = ind["jkse_above_ma50"].ffill().fillna(0.5)
        ind["rel_str_5d"] = (ind["ret_5d"] - ind["jkse_ret_5d"]).fillna(0.0)
    else:
        ind["jkse_ret_5d"] = 0.0
        ind["jkse_above_ma50"] = 0.5
        ind["rel_str_5d"] = 0.0

    # Forward targets (used strictly as labels, never as features)
    for k in range(1, horizon_days + 1):
        ind[f"fwd_ret_{k}"] = (c.shift(-k) / c) - 1.0
    ind["fwd_ret"] = ind[f"fwd_ret_{horizon_days}"]
    ind["target_up"] = (ind["fwd_ret"] > fee).astype(float)
    return ind
