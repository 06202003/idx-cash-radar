"""Walk-forward ML stock direction forecaster (5-day horizon, net of 0.4% transaction fee)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import ROUND_TRIP_FEE
from src.engine.indicators import compute_indicators

BULLISH_PROB_THRESHOLD = 0.58

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


def compute_v2_volatility_cone(df: pd.DataFrame, horizon_days: int = 5) -> dict[str, Any] | None:
    """
    Computes H1'-validated V2 (EWMA lambda=0.97) volatility cone centered at flat last close
    (zero directional claim) using causal empirical quantiles of standardized residuals.
    """
    if df.empty or len(df) < 90:
        return None
    c = df["close"].astype(float)
    last_close = float(c.iloc[-1])
    if last_close <= 0:
        return None
    log_r = np.log(c / c.shift(1)).to_numpy(dtype=float)
    n = len(log_r)
    valid = np.where(np.isfinite(log_r))[0]
    if len(valid) < 60:
        return None

    var = max(float(np.var(log_r[valid[:20]])), 1e-8)
    sig = np.full(n, np.nan, dtype=float)
    for i in range(valid[0], n):
        if np.isfinite(log_r[i]):
            var = 0.97 * var + 0.03 * (log_r[i] ** 2)
        sig[i] = np.sqrt(max(var, 1e-8))
    cur_sig = float(sig[-1])
    if not np.isfinite(cur_sig) or cur_sig <= 0:
        return None

    mid = [round(last_close, 2)] * horizon_days
    lo68, hi68, lo90, hi90 = [], [], [], []
    for h in range(1, horizon_days + 1):
        cum_r = np.log(c.shift(-h) / c).to_numpy(dtype=float)
        # Strictly causal prior residuals up to n - 1 - h
        end_idx = max(0, n - 1 - h)
        ok = np.isfinite(cum_r[:end_idx]) & np.isfinite(sig[:end_idx]) & (sig[:end_idx] > 0)
        if ok.sum() < 40:
            return None
        z = cum_r[:end_idx][ok] / sig[:end_idx][ok]
        q16, q84 = np.quantile(z, [0.16, 0.84])
        q05, q95 = np.quantile(z, [0.05, 0.95])
        lo68.append(round(last_close * float(np.exp(cur_sig * q16)), 2))
        hi68.append(round(last_close * float(np.exp(cur_sig * q84)), 2))
        lo90.append(round(last_close * float(np.exp(cur_sig * q05)), 2))
        hi90.append(round(last_close * float(np.exp(cur_sig * q95)), 2))

    return {"mid": mid, "lo68": lo68, "hi68": hi68, "lo90": lo90, "hi90": hi90}


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

    ridge = Pipeline([("scaler", StandardScaler()), ("reg", Ridge(alpha=30.0))])
    ridge.fit(X_train, Y_train[:, -1])
    pred_5d = float(np.clip(ridge.predict(X_curr)[0], -0.20, 0.20))
    pred_rets = np.array([pred_5d * (((k + 1) / horizon_days) ** 0.85) for k in range(horizon_days)])

    tr_5d = np.clip(ridge.predict(X_train), -0.20, 0.20)
    tr_paths = np.column_stack([tr_5d * (((k + 1) / horizon_days) ** 0.85) for k in range(horizon_days)])
    res = Y_train - tr_paths
    q_lo = np.quantile(res, 0.16, axis=0)
    q_hi = np.quantile(res, 0.84, axis=0)

    mid = [round(last_close * (1.0 + float(pred_rets[k])), 2) for k in range(horizon_days)]
    upper = [round(last_close * (1.0 + float(pred_rets[k] + q_hi[k])), 2) for k in range(horizon_days)]
    lower = [round(last_close * (1.0 + float(pred_rets[k] + q_lo[k])), 2) for k in range(horizon_days)]

    return {
        "mid": mid,
        "upper": upper,
        "lower": lower,
        "target_5d_pct": round(float(pred_rets[-1]) * 100.0, 2),
    }


def _recency_weights(length: int, half_life: float = 150.0) -> np.ndarray:
    """Exponential decay weights so recent market regimes carry more influence."""
    age = np.arange(length, dtype=float)[::-1]
    return np.exp(-np.log(2.0) * age / half_life)


def _build_model() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.5, max_iter=500, random_state=42)),
    ])


def _ema_smooth(probs: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """Applies causal exponential moving average to reduce 1-day probability flip-flops."""
    if len(probs) == 0:
        return probs
    out = np.empty_like(probs, dtype=float)
    out[0] = float(probs[0])
    for i in range(1, len(probs)):
        out[i] = alpha * float(probs[i]) + (1.0 - alpha) * out[i - 1]
    return out


def _classify_direction(p_up_pct: float) -> str:
    if p_up_pct >= BULLISH_PROB_THRESHOLD * 100.0:
        return "BULLISH (Cenderung Naik)"
    if p_up_pct <= 42.0:
        return "BEARISH (Cenderung Turun)"
    return "NETRAL"


def forecast_direction_with_backtest(
    df: pd.DataFrame,
    horizon_days: int = 5,
    fee: float = ROUND_TRIP_FEE,
) -> dict[str, Any]:
    """
    Trains an expanding-window walk-forward classifier to estimate 5-day price direction
    sentiment (BULLISH / NETRAL / BEARISH) with EMA probability smoothing, 2-day flip
    confirmation, and OOS comparison between fixed-hold vs dynamic early-exit.
    """
    if df.empty or len(df) < 120:
        return {
            "status": "insufficient_data",
            "direction": "NETRAL",
            "p_up_pct": 50.0,
            "p_up_raw_pct": 50.0,
            "confidence_label": "Data Historis < 120 Hari",
            "oos_sample_count": 0,
            "oos_accuracy_pct": None,
            "oos_bullish_win_rate_pct": None,
            "oos_bullish_avg_net_ret_pct": None,
            "oos_bullish_signals": 0,
            "oos_dynamic_exit_win_rate_pct": None,
            "oos_dynamic_exit_avg_net_ret_pct": None,
            "oos_recommended_strategy": None,
            "holding_guidance": None,
        }

    prep = _prepare_dataset(df, horizon_days=horizon_days, fee=fee)
    labeled = prep.dropna(subset=FEATURE_COLS + ["fwd_ret"]).reset_index(drop=True)
    if len(labeled) < 80:
        return {
            "status": "insufficient_data",
            "direction": "NETRAL",
            "p_up_pct": 50.0,
            "p_up_raw_pct": 50.0,
            "confidence_label": "Sampel Terlabel < 80 Baris",
            "oos_sample_count": 0,
            "oos_accuracy_pct": None,
            "oos_bullish_win_rate_pct": None,
            "oos_bullish_avg_net_ret_pct": None,
            "oos_bullish_signals": 0,
            "oos_dynamic_exit_win_rate_pct": None,
            "oos_dynamic_exit_avg_net_ret_pct": None,
            "oos_recommended_strategy": None,
            "holding_guidance": None,
        }

    # Walk-forward out-of-sample evaluation (3 expanding folds over the second half of history)
    n = len(labeled)
    start_eval = max(60, n // 2)
    step = max(20, (n - start_eval) // 3)
    oos_preds: list[int] = []
    oos_probs: list[float] = []
    oos_actuals: list[int] = []
    oos_fwd_rets: list[float] = []
    oos_dyn_rets: list[float] = []

    for split in range(start_eval, n, step):
        end = min(split + step, n)
        test_df = labeled.iloc[split:end]
        # Purge horizon_days before split to prevent overlapping 5-day label leakage
        tr_end = max(30, split - horizon_days)
        train_df = labeled.iloc[:tr_end]
        if len(test_df) == 0 or train_df["target_up"].nunique() < 2:
            continue
        model = _build_model()
        model.fit(train_df[FEATURE_COLS], train_df["target_up"].astype(int))

        # Score extra horizon_days bars ahead so dynamic-exit simulation can observe flips
        ext_end = min(end + horizon_days, n)
        ext_probs_raw = model.predict_proba(labeled.iloc[split:ext_end][FEATURE_COLS])[:, 1]
        ext_probs = _ema_smooth(ext_probs_raw, alpha=0.5)

        probs = ext_probs[: len(test_df)]
        preds = (probs >= BULLISH_PROB_THRESHOLD).astype(int)
        oos_probs.extend(probs.tolist())
        oos_preds.extend(preds.tolist())
        oos_actuals.extend(test_df["target_up"].astype(int).tolist())
        oos_fwd_rets.extend(test_df["fwd_ret"].tolist())

        closes_ext = labeled.iloc[split:ext_end]["close"].to_numpy(dtype=float)
        fwd_rets_test = test_df["fwd_ret"].to_numpy(dtype=float)
        for j in range(len(test_df)):
            if preds[j] != 1:
                continue
            entry_px = closes_ext[j]
            exit_ret = float(fwd_rets_test[j])
            # Exit early only on 2 consecutive bearish-flip days (<= 0.42) to avoid 1-day noise
            consec_bear = 0
            for d in range(1, horizon_days):
                idx_d = j + d
                if idx_d >= len(ext_probs):
                    break
                if ext_probs[idx_d] <= 0.42:
                    consec_bear += 1
                    if consec_bear >= 2 and entry_px > 0:
                        exit_ret = (closes_ext[idx_d] / entry_px) - 1.0
                        break
                else:
                    consec_bear = 0
            oos_dyn_rets.append(exit_ret - fee)

    oos_acc = None
    bullish_win = None
    bullish_avg_net = None
    dyn_win = None
    dyn_avg_net = None
    rec_strategy = None
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

            if oos_dyn_rets:
                dyn_wins = sum(1 for r in oos_dyn_rets if r > 0.0)
                dyn_win = round((dyn_wins / len(oos_dyn_rets)) * 100.0, 1)
                dyn_avg_net = round(float(np.mean(oos_dyn_rets)) * 100.0, 2)
                rec_strategy = "HOLD_5D" if bullish_avg_net >= dyn_avg_net else "EXIT_ON_FLIP"

    # Fit final model on all labeled rows and smooth over recent bars to dampen 1-day noise
    valid_feat = prep.dropna(subset=FEATURE_COLS)
    latest_row = valid_feat.iloc[-1:]
    if latest_row.empty or labeled["target_up"].nunique() < 2:
        p_up_raw = 0.50
        p_up_smooth = 0.50
        prev_p_up_smooth = 0.50
    else:
        final_model = _build_model()
        final_model.fit(labeled[FEATURE_COLS], labeled["target_up"].astype(int))
        recent_rows = valid_feat.iloc[-5:]
        recent_raw = final_model.predict_proba(recent_rows[FEATURE_COLS])[:, 1]
        recent_smooth = _ema_smooth(recent_raw, alpha=0.5)
        p_up_raw = float(recent_raw[-1])
        p_up_smooth = float(recent_smooth[-1])
        prev_p_up_smooth = float(recent_smooth[-2]) if len(recent_smooth) >= 2 else p_up_smooth

    p_up_pct = round(p_up_smooth * 100.0, 1)
    p_up_raw_pct = round(p_up_raw * 100.0, 1)
    prev_p_up_pct = round(prev_p_up_smooth * 100.0, 1)

    direction = _classify_direction(p_up_pct)
    prev_direction = _classify_direction(prev_p_up_pct)
    direction_confirmed = direction == prev_direction

    if direction.startswith("BULLISH"):
        holding_guidance = "Sinyal naik aktif; hold sesuai plan & jaga SL (jangan cut cuma karena turun ke NETRAL)."
    elif direction.startswith("BEARISH"):
        if direction_confirmed:
            holding_guidance = "BEARISH terkonfirmasi ≥2H — pertimbangkan exit/ketatkan trailing stop."
        else:
            holding_guidance = "Baru 1H flip BEARISH — tunggu konfirmasi close/SL sebelum cut."
    elif prev_direction.startswith("BULLISH"):
        holding_guidance = "Momentum turun dari BULLISH ke NETRAL — tahan posisi selama tidak kena SL."
    else:
        holding_guidance = "Area NETRAL — tunggu sinyal BULLISH atau breakout teknikal."

    trajectory = _forecast_5d_trajectory(prep, latest_row, horizon_days=horizon_days)

    return {
        "status": "ok",
        "horizon_days": horizon_days,
        "direction": direction,
        "direction_confirmed": direction_confirmed,
        "p_up_pct": p_up_pct,
        "p_up_raw_pct": p_up_raw_pct,
        "p_down_pct": round(100.0 - p_up_pct, 1),
        "oos_sample_count": len(oos_preds),
        "oos_accuracy_pct": oos_acc,
        "oos_bullish_win_rate_pct": bullish_win,
        "oos_bullish_avg_net_ret_pct": bullish_avg_net,
        "oos_bullish_signals": bullish_n,
        "oos_dynamic_exit_win_rate_pct": dyn_win,
        "oos_dynamic_exit_avg_net_ret_pct": dyn_avg_net,
        "oos_recommended_strategy": rec_strategy,
        "holding_guidance": holding_guidance,
        "trajectory": trajectory,
    }
