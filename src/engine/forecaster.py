"""Walk-forward ML stock direction forecaster (5-day horizon, net of 0.4% transaction fee)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import ROUND_TRIP_FEE
from src.engine.indicators import compute_indicators

FEATURE_COLS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "dist_ma20",
    "dist_ma50",
    "rsi14",
    "vol_ratio_log",
    "volatility_20d",
]


def _prepare_dataset(df: pd.DataFrame, horizon_days: int = 5, fee: float = ROUND_TRIP_FEE) -> pd.DataFrame:
    ind = compute_indicators(df)
    ind["vol_ratio_log"] = np.log1p(ind["vol_ratio_20d"].clip(lower=0.0))
    ind["fwd_ret"] = (ind["close"].shift(-horizon_days) / ind["close"]) - 1.0
    ind["target_up"] = (ind["fwd_ret"] > fee).astype(float)
    return ind


def _forecast_5d_trajectory(
    prep: pd.DataFrame,
    latest_row: pd.DataFrame,
    horizon_days: int = 5,
) -> dict[str, Any] | None:
    """Predicts +1D..+5D price trajectory + 1-sigma cone using an MLP + Ridge ensemble."""
    if latest_row.empty:
        return None
    last_close = float(latest_row["close"].iloc[0])
    if last_close <= 0:
        return None

    target_cols = []
    work = prep.copy()
    for k in range(1, horizon_days + 1):
        col = f"fwd_ret_{k}"
        work[col] = ((work["close"].shift(-k) / work["close"]) - 1.0).clip(-0.25, 0.25)
        target_cols.append(col)

    train_df = work.dropna(subset=FEATURE_COLS + target_cols)
    if len(train_df) < 60:
        return None

    X_train = train_df[FEATURE_COLS]
    Y_train = train_df[target_cols].to_numpy(dtype=float)
    X_curr = latest_row[FEATURE_COLS]

    ridge = Pipeline([("scaler", StandardScaler()), ("reg", Ridge(alpha=15.0))])
    ridge.fit(X_train, Y_train)
    pred_rets = ridge.predict(X_curr)[0]

    try:
        mlp = Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=300, early_stopping=True, random_state=42)),
        ])
        mlp.fit(X_train, Y_train)
        pred_mlp = mlp.predict(X_curr)[0]
        pred_rets = 0.5 * pred_rets + 0.5 * pred_mlp
    except Exception:
        pass

    pred_rets = np.clip(pred_rets, -0.20, 0.20)
    daily_vol = float(latest_row["volatility_20d"].iloc[0]) if pd.notna(latest_row["volatility_20d"].iloc[0]) else 0.02
    daily_vol = max(0.008, min(0.06, daily_vol))

    mid = [round(last_close * (1.0 + float(pred_rets[k])), 2) for k in range(horizon_days)]
    upper = [round(last_close * (1.0 + float(pred_rets[k]) + daily_vol * np.sqrt(k + 1)), 2) for k in range(horizon_days)]
    lower = [round(last_close * (1.0 + float(pred_rets[k]) - daily_vol * np.sqrt(k + 1)), 2) for k in range(horizon_days)]

    return {
        "mid": mid,
        "upper": upper,
        "lower": lower,
        "target_5d_pct": round(float(pred_rets[-1]) * 100.0, 2),
    }


def _build_model() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.5, max_iter=500, random_state=42)),
    ])


def forecast_direction_with_backtest(
    df: pd.DataFrame,
    horizon_days: int = 5,
    fee: float = ROUND_TRIP_FEE,
) -> dict[str, Any]:
    """
    Trains an expanding-window walk-forward classifier to estimate 5-day price direction
    sentiment (BULLISH / NETRAL / BEARISH) alongside out-of-sample win-rate & net return.
    """
    if df.empty or len(df) < 120:
        return {
            "status": "insufficient_data",
            "direction": "NETRAL",
            "p_up_pct": 50.0,
            "confidence_label": "Data Historis < 120 Hari",
            "oos_sample_count": 0,
            "oos_accuracy_pct": None,
            "oos_bullish_win_rate_pct": None,
            "oos_bullish_avg_net_ret_pct": None,
            "oos_bullish_signals": 0,
        }

    prep = _prepare_dataset(df, horizon_days=horizon_days, fee=fee)
    labeled = prep.dropna(subset=FEATURE_COLS + ["fwd_ret"]).reset_index(drop=True)
    if len(labeled) < 80:
        return {
            "status": "insufficient_data",
            "direction": "NETRAL",
            "p_up_pct": 50.0,
            "confidence_label": "Sampel Terlabel < 80 Baris",
            "oos_sample_count": 0,
            "oos_accuracy_pct": None,
            "oos_bullish_win_rate_pct": None,
            "oos_bullish_avg_net_ret_pct": None,
            "oos_bullish_signals": 0,
        }

    # Walk-forward out-of-sample evaluation (3 expanding folds over the second half of history)
    n = len(labeled)
    start_eval = max(60, n // 2)
    step = max(20, (n - start_eval) // 3)
    oos_preds: list[int] = []
    oos_probs: list[float] = []
    oos_actuals: list[int] = []
    oos_fwd_rets: list[float] = []

    for split in range(start_eval, n, step):
        end = min(split + step, n)
        train_df = labeled.iloc[:split]
        test_df = labeled.iloc[split:end]
        if len(test_df) == 0 or train_df["target_up"].nunique() < 2:
            continue
        model = _build_model()
        model.fit(train_df[FEATURE_COLS], train_df["target_up"].astype(int))
        probs = model.predict_proba(test_df[FEATURE_COLS])[:, 1]
        preds = (probs >= 0.55).astype(int)
        oos_probs.extend(probs.tolist())
        oos_preds.extend(preds.tolist())
        oos_actuals.extend(test_df["target_up"].astype(int).tolist())
        oos_fwd_rets.extend(test_df["fwd_ret"].tolist())

    oos_acc = None
    bullish_win = None
    bullish_avg_net = None
    bullish_n = 0
    if oos_preds:
        acc_hits = sum(1 for p, a in zip(oos_preds, oos_actuals) if (p == 1 and a == 1) or (p == 0 and a == 0))
        oos_acc = round((acc_hits / len(oos_preds)) * 100.0, 1)
        bull_idx = [i for i, p in enumerate(oos_preds) if p == 1]
        bullish_n = len(bull_idx)
        if bullish_n > 0:
            bull_wins = sum(1 for i in bull_idx if oos_actuals[i] == 1)
            bullish_win = round((bull_wins / bullish_n) * 100.0, 1)
            avg_net = float(np.mean([oos_fwd_rets[i] - fee for i in bull_idx])) * 100.0
            bullish_avg_net = round(avg_net, 2)

    # Fit final model on all labeled rows to score latest bar
    latest_row = prep.dropna(subset=FEATURE_COLS).iloc[-1:]
    if latest_row.empty or labeled["target_up"].nunique() < 2:
        p_up = 0.50
    else:
        final_model = _build_model()
        final_model.fit(labeled[FEATURE_COLS], labeled["target_up"].astype(int))
        p_up = float(final_model.predict_proba(latest_row[FEATURE_COLS])[:, 1][0])

    p_up_pct = round(p_up * 100.0, 1)
    if p_up_pct >= 58.0:
        direction = "BULLISH (Cenderung Naik)"
    elif p_up_pct <= 42.0:
        direction = "BEARISH (Cenderung Turun)"
    else:
        direction = "NETRAL"

    trajectory = _forecast_5d_trajectory(prep, latest_row, horizon_days=horizon_days)

    return {
        "status": "ok",
        "horizon_days": horizon_days,
        "direction": direction,
        "p_up_pct": p_up_pct,
        "p_down_pct": round(100.0 - p_up_pct, 1),
        "oos_sample_count": len(oos_preds),
        "oos_accuracy_pct": oos_acc,
        "oos_bullish_win_rate_pct": bullish_win,
        "oos_bullish_avg_net_ret_pct": bullish_avg_net,
        "oos_bullish_signals": bullish_n,
        "trajectory": trajectory,
    }
