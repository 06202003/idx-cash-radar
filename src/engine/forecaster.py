"""Walk-forward ML stock direction forecaster (5-day horizon, net of 0.4% transaction fee)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression, Ridge
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
    "bar_pos",
    "atr14_pct",
    "pos_20d",
    "ma20_slope5",
    "signed_vol_5d",
]


def _prepare_dataset(df: pd.DataFrame, horizon_days: int = 5, fee: float = ROUND_TRIP_FEE) -> pd.DataFrame:
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

    ind["fwd_ret"] = (c.shift(-horizon_days) / c) - 1.0
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
        et = ExtraTreesRegressor(n_estimators=100, max_depth=4, min_samples_leaf=10, random_state=42)
        et.fit(X_train, Y_train)
        pred_et = et.predict(X_curr)[0]
        pred_rets = 0.5 * pred_rets + 0.5 * pred_et
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


def _recency_weights(length: int, half_life: float = 150.0) -> np.ndarray:
    """Exponential decay weights so recent market regimes carry more influence."""
    age = np.arange(length, dtype=float)[::-1]
    return np.exp(-np.log(2.0) * age / half_life)


class _SoftEnsemble:
    """Blends a regularized linear classifier with a shallow gradient-boosted tree."""

    def __init__(self) -> None:
        self.lr = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=0.3, max_iter=500, random_state=42)),
        ])
        self.gb = HistGradientBoostingClassifier(
            max_depth=3,
            max_iter=60,
            learning_rate=0.05,
            min_samples_leaf=15,
            l2_regularization=3.0,
            random_state=42,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series, sample_weight: np.ndarray | None = None) -> _SoftEnsemble:
        self.lr.fit(X, y, clf__sample_weight=sample_weight)
        self.gb.fit(X, y, sample_weight=sample_weight)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return 0.4 * self.lr.predict_proba(X) + 0.6 * self.gb.predict_proba(X)


def _build_model() -> _SoftEnsemble:
    return _SoftEnsemble()


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
    if p_up_pct >= 58.0:
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
        w_tr = _recency_weights(len(train_df))
        model.fit(train_df[FEATURE_COLS], train_df["target_up"].astype(int), sample_weight=w_tr)

        # Score extra horizon_days bars ahead so dynamic-exit simulation can observe flips
        ext_end = min(end + horizon_days, n)
        ext_probs_raw = model.predict_proba(labeled.iloc[split:ext_end][FEATURE_COLS])[:, 1]
        ext_probs = _ema_smooth(ext_probs_raw, alpha=0.5)

        probs = ext_probs[: len(test_df)]
        preds = (probs >= 0.58).astype(int)
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
        w_all = _recency_weights(len(labeled))
        final_model.fit(labeled[FEATURE_COLS], labeled["target_up"].astype(int), sample_weight=w_all)
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
