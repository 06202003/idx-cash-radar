"""Step 9: Out-of-sample walk-forward evaluation of ML+5H trajectory vs naive baselines."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.eval.features import EXTRA_OHLCV_FEATURES, ORIG_FEATURES, prepare_eval_dataframe


def _is_zigzag(path_rets: np.ndarray) -> bool:
    """Returns True if step-to-step changes flip sign >= 2 times across +1..+5d."""
    diffs = np.diff(np.concatenate([[0.0], path_rets]))
    signs = np.sign(diffs)
    non_zero = signs[signs != 0]
    if len(non_zero) < 2:
        return False
    flips = int(np.sum(non_zero[1:] != non_zero[:-1]))
    return flips >= 2


def evaluate_trajectory_oos(
    data: dict[str, pd.DataFrame],
    jkse_df: pd.DataFrame,
    horizon: int = 5,
    holdout_days: int = 63,
) -> dict[str, Any]:
    """
    Walk-forward OOS evaluation on dev set for +1..+5D trajectory models:
    1) Naive flat (pred_ret = 0)
    2) Historical drift (k * mean_1d_ret_train)
    3) Current Ridge + ExtraTrees multi-output (direct returns)
    4) Smooth/cumulative Ridge-only (stepwise positive/negative damped drift -> no zig-zag)
    """
    feat_cols = ORIG_FEATURES + EXTRA_OHLCV_FEATURES
    target_cols = [f"fwd_ret_{k}" for k in range(1, horizon + 1)]

    actuals_all: list[np.ndarray] = []
    pred_zero_all: list[np.ndarray] = []
    pred_drift_all: list[np.ndarray] = []
    pred_cur_all: list[np.ndarray] = []
    pred_mono_all: list[np.ndarray] = []
    cur_lo_all: list[np.ndarray] = []
    cur_hi_all: list[np.ndarray] = []

    for ticker, df in data.items():
        prep = prepare_eval_dataframe(df, jkse_df=jkse_df, horizon_days=horizon)
        labeled = prep.dropna(subset=feat_cols + target_cols).reset_index(drop=True)
        if len(labeled) < 200:
            continue

        holdout_start = len(labeled) - holdout_days
        dev_df = labeled.iloc[: holdout_start - horizon].reset_index(drop=True)
        n_dev = len(dev_df)
        start_eval = max(120, n_dev // 2)
        step = max(20, (n_dev - start_eval) // 5)

        for split in range(start_eval, n_dev, step):
            end = min(split + step, n_dev)
            tr_end = max(60, split - horizon)
            train_df = dev_df.iloc[:tr_end]
            test_df = dev_df.iloc[split:end]
            if len(test_df) == 0:
                continue

            X_tr = train_df[feat_cols]
            Y_tr = train_df[target_cols].clip(-0.25, 0.25).to_numpy(dtype=float)
            X_te = test_df[feat_cols]
            Y_te = test_df[target_cols].to_numpy(dtype=float)

            # 1) Naive flat
            p_zero = np.zeros_like(Y_te)

            # 2) Historical drift
            mean_1d = float(train_df["ret_1d"].mean())
            p_drift = np.column_stack([np.full(len(test_df), mean_1d * k) for k in range(1, horizon + 1)])

            # 3) Current Ridge + ExtraTrees
            ridge = Pipeline([("s", StandardScaler()), ("reg", Ridge(alpha=20.0))])
            ridge.fit(X_tr, Y_tr)
            et = ExtraTreesRegressor(n_estimators=80, max_depth=4, min_samples_leaf=12, random_state=42)
            et.fit(X_tr, Y_tr)
            p_cur = np.clip(0.5 * ridge.predict(X_te) + 0.5 * et.predict(X_te), -0.20, 0.20)

            # Empirical OOS residual quantile cone from training residuals
            tr_res = Y_tr - np.clip(0.5 * ridge.predict(X_tr) + 0.5 * et.predict(X_tr), -0.20, 0.20)
            q_lo = np.quantile(tr_res, 0.16, axis=0)
            q_hi = np.quantile(tr_res, 0.84, axis=0)
            cur_lo_all.append(p_cur + q_lo[None, :])
            cur_hi_all.append(p_cur + q_hi[None, :])

            # 4) Monotonic cumulative Ridge: predict 5d return and interpolate smoothly
            r5 = Pipeline([("s", StandardScaler()), ("reg", Ridge(alpha=30.0))])
            r5.fit(X_tr, Y_tr[:, -1])
            p_5d = np.clip(r5.predict(X_te), -0.20, 0.20)
            p_mono = np.column_stack([p_5d * ((k / horizon) ** 0.85) for k in range(1, horizon + 1)])

            actuals_all.append(Y_te)
            pred_zero_all.append(p_zero)
            pred_drift_all.append(p_drift)
            pred_cur_all.append(p_cur)
            pred_mono_all.append(p_mono)

    Y = np.vstack(actuals_all)
    P_zero = np.vstack(pred_zero_all)
    P_drift = np.vstack(pred_drift_all)
    P_cur = np.vstack(pred_cur_all)
    P_mono = np.vstack(pred_mono_all)
    C_lo = np.vstack(cur_lo_all)
    C_hi = np.vstack(cur_hi_all)

    def _summarize(name: str, P: np.ndarray) -> dict[str, Any]:
        err = P - Y
        mae_h = [round(float(np.mean(np.abs(err[:, k]))) * 100.0, 3) for k in range(horizon)]
        rmse_h = [round(float(np.sqrt(np.mean(err[:, k] ** 2))) * 100.0, 3) for k in range(horizon)]
        dir_h = [
            round(float(np.mean((P[:, k] > 0) == (Y[:, k] > 0))) * 100.0, 1)
            for k in range(horizon)
        ]
        zig_rate = round(float(np.mean([_is_zigzag(row) for row in P])) * 100.0, 1)
        return {
            "model": name,
            "n_samples": len(Y),
            "mae_pct": mae_h,
            "rmse_pct": rmse_h,
            "dir_acc_pct": dir_h,
            "zigzag_rate_pct": zig_rate,
        }

    cone_cov = [
        round(float(np.mean((Y[:, k] >= C_lo[:, k]) & (Y[:, k] <= C_hi[:, k]))) * 100.0, 1)
        for k in range(horizon)
    ]

    return {
        "zero": _summarize("Naive Flat (0%)", P_zero),
        "drift": _summarize("Historical Drift", P_drift),
        "current_et_ridge": _summarize("Ridge + ExtraTrees", P_cur),
        "mono_ridge": _summarize("Monotonic Ridge", P_mono),
        "empirical_cone_coverage_pct": cone_cov,
    }
