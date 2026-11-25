"""Step 2: Hypothesis H1 - 5-day volatility forecasting & calibrated cones."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.eval.stats_v2 import date_clustered_bootstrap_ci

HORIZON = 5


def _ewma_vol(log_ret: np.ndarray, lam: float) -> np.ndarray:
    n = len(log_ret)
    out = np.full(n, np.nan, dtype=float)
    valid = np.where(np.isfinite(log_ret))[0]
    if len(valid) < 20:
        return out
    init_var = float(np.var(log_ret[valid[:20]]))
    var = max(init_var, 1e-8)
    for i in range(valid[0], n):
        r = log_ret[i]
        if np.isfinite(r):
            var = lam * var + (1.0 - lam) * (r * r)
        out[i] = np.sqrt(max(var, 1e-8))
    out[:20] = np.nan
    return out


def _garman_klass_vol(df: pd.DataFrame, window: int = 20) -> np.ndarray:
    h = df["high"].astype(float).clip(lower=1e-6)
    l = df["low"].astype(float).clip(lower=1e-6)
    o = df["open"].astype(float).clip(lower=1e-6)
    c = df["close"].astype(float).clip(lower=1e-6)
    hl = np.log(h / l)
    co = np.log(c / o)
    gk = 0.5 * (hl ** 2) - (2.0 * np.log(2.0) - 1.0) * (co ** 2)
    gk_var = gk.rolling(window, min_periods=window).mean().clip(lower=1e-8)
    return np.sqrt(gk_var).to_numpy(dtype=float)


def _compute_vol_series(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"].astype(float)
    log_r = np.log(c / c.shift(1))
    out["log_ret"] = log_r

    # Target: realized daily vol over t+1..t+5
    sq_r = log_r ** 2
    fwd_var = sum(sq_r.shift(-k) for k in range(1, HORIZON + 1)) / float(HORIZON)
    out["target_vol_5d"] = np.sqrt(fwd_var.clip(lower=1e-10))

    # Forward cumulative log returns for horizons +1..+5
    for k in range(1, HORIZON + 1):
        out[f"cum_log_ret_{k}"] = np.log(c.shift(-k) / c)

    out["V0"] = log_r.rolling(60, min_periods=60).std().clip(lower=1e-5)
    out["V1"] = _ewma_vol(log_r.to_numpy(dtype=float), 0.94)
    out["V2"] = _ewma_vol(log_r.to_numpy(dtype=float), 0.97)
    out["V3"] = _garman_klass_vol(out, 20)
    out["V6"] = 0.5 * out["V1"] + 0.5 * out["V3"]

    # HAR features (causal)
    out["har_1d"] = log_r.abs()
    out["har_5d"] = np.sqrt((sq_r.rolling(5, min_periods=5).mean()).clip(lower=1e-10))
    out["har_22d"] = np.sqrt((sq_r.rolling(22, min_periods=22).mean()).clip(lower=1e-10))
    return out


def _fit_har_walkforward(df: pd.DataFrame, eval_mask: np.ndarray) -> np.ndarray:
    """Walk-forward Ridge HAR on target_vol_5d with 5-bar purge gap."""
    n = len(df)
    preds = np.full(n, np.nan, dtype=float)
    har_cols = ["har_1d", "har_5d", "har_22d"]
    eval_idx = np.where(eval_mask)[0]
    if len(eval_idx) == 0:
        return preds

    # Retrain every 42 bars (~2 months) for speed & realism
    step = 42
    for start in range(eval_idx[0], eval_idx[-1] + 1, step):
        end = min(start + step, n)
        tr_end = max(0, start - HORIZON)
        tr = df.iloc[:tr_end].dropna(subset=har_cols + ["target_vol_5d"])
        if len(tr) < 60:
            continue
        model = Pipeline([("s", StandardScaler()), ("reg", Ridge(alpha=10.0))])
        y_log = np.log(tr["target_vol_5d"].to_numpy(dtype=float))
        model.fit(tr[har_cols], y_log)
        # Jensen's inequality correction: E[exp(y)] = exp(mu + 0.5 * sigma_res^2)
        res_var = float(np.var(y_log - model.predict(tr[har_cols])))
        te = df.iloc[start:end]
        valid_te = te[har_cols].notna().all(axis=1).to_numpy()
        if valid_te.any():
            p_log = model.predict(te.loc[valid_te, har_cols])
            preds[start:end][valid_te] = np.clip(np.exp(p_log + 0.5 * res_var), 1e-4, 0.25)
    return preds


def _eval_cones(
    vol_dfs: dict[str, pd.DataFrame],
    jkse_df: pd.DataFrame,
    cand_col: str,
    segment_name: str,
) -> dict[str, Any]:
    """Builds causal empirical-quantile cones centered at 0 and computes 68%/90% coverage."""
    j_ret5 = pd.Series(dtype=float)
    if not jkse_df.empty:
        jc = jkse_df["close"].astype(float)
        j_tmp = jkse_df[["date"]].copy()
        j_tmp["j_ret5"] = jc.pct_change(5)
        j_ret5 = j_tmp.set_index("date")["j_ret5"]

    pooled_68 = {h: [] for h in range(1, HORIZON + 1)}
    pooled_90 = {h: [] for h in range(1, HORIZON + 1)}
    cond_hi_68, cond_lo_68, cond_jdown_68 = [], [], []
    per_ticker_68: dict[str, float] = {}
    per_ticker_90: dict[str, float] = {}
    emp_q68_scale: dict[int, list[float]] = {h: [] for h in range(1, HORIZON + 1)}

    for t, df in vol_dfs.items():
        seg_mask = (df["segment"] == segment_name) & df["liq_ok"] & df[cand_col].notna()
        idxs = np.where(seg_mask.to_numpy())[0]
        if len(idxs) == 0:
            continue

        sig = df[cand_col].to_numpy(dtype=float)
        v0 = df["V0"].to_numpy(dtype=float)
        med_v0 = float(np.nanmedian(v0[v0 > 0])) if np.isfinite(v0).any() else 0.02
        t_hits68, t_hits90 = [], []

        for i in idxs:
            if not np.isfinite(sig[i]) or sig[i] <= 0:
                continue
            d_str = str(df["date"].iloc[i])
            j_down = bool(d_str in j_ret5.index and pd.notna(j_ret5.loc[d_str]) and j_ret5.loc[d_str] < 0)
            hi_vol = bool(np.isfinite(v0[i]) and v0[i] > med_v0)

            for h in range(1, HORIZON + 1):
                if i - h < 60:
                    continue
                y_h = df[f"cum_log_ret_{h}"].iloc[i]
                if not np.isfinite(y_h):
                    continue
                # Causal standardized residuals strictly before i - h (purge = h)
                hist_y = df[f"cum_log_ret_{h}"].iloc[: i - h].to_numpy(dtype=float)
                hist_s = sig[: i - h]
                ok = np.isfinite(hist_y) & np.isfinite(hist_s) & (hist_s > 0)
                if ok.sum() < 60:
                    continue
                z_hist = hist_y[ok] / hist_s[ok]
                q16, q84 = np.quantile(z_hist, [0.16, 0.84])
                q05, q95 = np.quantile(z_hist, [0.05, 0.95])
                emp_q68_scale[h].append(float((q84 - q16) / 2.0))

                lo68, hi68 = sig[i] * q16, sig[i] * q84
                lo90, hi90 = sig[i] * q05, sig[i] * q95
                in68 = int(lo68 <= y_h <= hi68)
                in90 = int(lo90 <= y_h <= hi90)

                pooled_68[h].append(in68)
                pooled_90[h].append(in90)
                if h == HORIZON:
                    t_hits68.append(in68)
                    t_hits90.append(in90)
                    if hi_vol:
                        cond_hi_68.append(in68)
                    else:
                        cond_lo_68.append(in68)
                    if j_down:
                        cond_jdown_68.append(in68)

        if t_hits68:
            per_ticker_68[t] = round(float(np.mean(t_hits68)) * 100.0, 1)
            per_ticker_90[t] = round(float(np.mean(t_hits90)) * 100.0, 1)

    cov68_h = {h: round(float(np.mean(v)) * 100.0, 1) if v else 0.0 for h, v in pooled_68.items()}
    cov90_h = {h: round(float(np.mean(v)) * 100.0, 1) if v else 0.0 for h, v in pooled_90.items()}
    pct_within_6_68 = round(float(np.mean([abs(v - 68.0) <= 6.0 for v in per_ticker_68.values()])) * 100.0, 1) if per_ticker_68 else 0.0
    pct_within_6_90 = round(float(np.mean([abs(v - 90.0) <= 6.0 for v in per_ticker_90.values()])) * 100.0, 1) if per_ticker_90 else 0.0
    scale_emp = {h: round(float(np.mean(v)), 3) if v else 0.0 for h, v in emp_q68_scale.items()}

    return {
        "cov68_by_h": cov68_h,
        "cov90_by_h": cov90_h,
        "cov68_5d": cov68_h[HORIZON],
        "cov90_5d": cov90_h[HORIZON],
        "pct_tickers_within_6pp_68": pct_within_6_68,
        "pct_tickers_within_6pp_90": pct_within_6_90,
        "cond_hi_vol_68": round(float(np.mean(cond_hi_68)) * 100.0, 1) if cond_hi_68 else None,
        "cond_lo_vol_68": round(float(np.mean(cond_lo_68)) * 100.0, 1) if cond_lo_68 else None,
        "cond_jkse_down_68": round(float(np.mean(cond_jdown_68)) * 100.0, 1) if cond_jdown_68 else None,
        "empirical_scale_by_h": scale_emp,
        "sqrt_h_ref": {h: round(float(np.sqrt(h)), 3) for h in range(1, HORIZON + 1)},
    }


def run_h1_evaluation(data: dict[str, pd.DataFrame], jkse_df: pd.DataFrame) -> dict[str, Any]:
    """Evaluates V0..V7 on DISCOVERY, selects best, and evaluates ONCE on LOCK-RECENT."""
    vol_dfs: dict[str, pd.DataFrame] = {}
    for t, df in data.items():
        vdf = _compute_vol_series(df)
        eval_mask = (vdf["segment"].isin(["DISCOVERY", "LOCK-RECENT"])).to_numpy()
        vdf["V5"] = _fit_har_walkforward(vdf, eval_mask)
        vdf["V7"] = 0.5 * vdf["V1"] + 0.5 * vdf["V5"]
        vol_dfs[t] = vdf

    candidates = ["V0", "V1", "V2", "V3", "V5", "V6", "V7"]
    disc_table: dict[str, dict[str, Any]] = {}

    # Collect DISCOVERY rows where all candidates & target are valid
    all_rows = []
    for t, vdf in vol_dfs.items():
        sub = vdf[(vdf["segment"] == "DISCOVERY") & vdf["liq_ok"]].dropna(subset=candidates + ["target_vol_5d"]).copy()
        if not sub.empty:
            sub["ticker"] = t
            all_rows.append(sub)
    disc_df = pd.concat(all_rows, ignore_index=True)

    target = disc_df["target_vol_5d"].to_numpy(dtype=float)
    v0_pred = np.clip(disc_df["V0"].to_numpy(dtype=float), 1e-5, 0.5)
    v0_qlike = np.log(v0_pred ** 2) + (target ** 2) / (v0_pred ** 2)
    dates = disc_df["date"].to_numpy()

    for c in candidates:
        pred = np.clip(disc_df[c].to_numpy(dtype=float), 1e-5, 0.5)
        qlike_arr = np.log(pred ** 2) + (target ** 2) / (pred ** 2)
        mae_log = float(np.mean(np.abs(np.log(pred) - np.log(target))))
        dm_res = (
            date_clustered_bootstrap_ci(dates, qlike_arr - v0_qlike, block_size=10, n_boot=5000, seed=42)
            if c != "V0"
            else {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "p_val": 1.0}
        )
        disc_table[c] = {
            "qlike": round(float(np.mean(qlike_arr)), 4),
            "mae_log": round(mae_log, 4),
            "dm_vs_v0": dm_res,
        }

    # Pick best on DISCOVERY (lowest QLIKE with DM CI < 0, else V0)
    sig_better = [c for c in candidates if c != "V0" and disc_table[c]["dm_vs_v0"]["ci_hi"] < 0.0]
    best_cand = min(sig_better, key=lambda c: disc_table[c]["qlike"]) if sig_better else "V0"

    disc_cone_best = _eval_cones(vol_dfs, jkse_df, best_cand, "DISCOVERY")

    # Single evaluation on LOCK-RECENT for best_cand and V0
    lock_rows = []
    for t, vdf in vol_dfs.items():
        sub = vdf[(vdf["segment"] == "LOCK-RECENT") & vdf["liq_ok"]].dropna(subset=[best_cand, "V0", "target_vol_5d"]).copy()
        if not sub.empty:
            sub["ticker"] = t
            lock_rows.append(sub)
    lock_df = pd.concat(lock_rows, ignore_index=True)

    l_target = lock_df["target_vol_5d"].to_numpy(dtype=float)
    l_dates = lock_df["date"].to_numpy()
    l_v0 = np.clip(lock_df["V0"].to_numpy(dtype=float), 1e-5, 0.5)
    l_best = np.clip(lock_df[best_cand].to_numpy(dtype=float), 1e-5, 0.5)
    q_v0 = np.log(l_v0 ** 2) + (l_target ** 2) / (l_v0 ** 2)
    q_best = np.log(l_best ** 2) + (l_target ** 2) / (l_best ** 2)
    dm_lock = date_clustered_bootstrap_ci(l_dates, q_best - q_v0, block_size=10, n_boot=5000, seed=42)

    lock_cone_best = _eval_cones(vol_dfs, jkse_df, best_cand, "LOCK-RECENT")
    lock_cone_v0 = _eval_cones(vol_dfs, jkse_df, "V0", "LOCK-RECENT")

    cov_ok = (
        abs(lock_cone_best["cov68_5d"] - 68.0) <= 3.0
        and abs(lock_cone_best["cov90_5d"] - 90.0) <= 3.0
        and lock_cone_best["pct_tickers_within_6pp_68"] >= 70.0
        and lock_cone_best["pct_tickers_within_6pp_90"] >= 70.0
    )
    qlike_ok = best_cand != "V0" and dm_lock["ci_hi"] < 0.0
    v0_cov_ok = abs(lock_cone_v0["cov68_5d"] - 68.0) <= 3.0 and abs(lock_cone_v0["cov90_5d"] - 90.0) <= 3.0
    h1_passed = bool(cov_ok and (qlike_ok or not v0_cov_ok))

    return {
        "n_disc": len(disc_df),
        "n_lock": len(lock_df),
        "disc_table": disc_table,
        "best_cand": best_cand,
        "disc_cone_best": disc_cone_best,
        "lock_qlike_v0": round(float(np.mean(q_v0)), 4),
        "lock_qlike_best": round(float(np.mean(q_best)), 4),
        "lock_dm_diff": dm_lock,
        "lock_cone_best": lock_cone_best,
        "lock_cone_v0": lock_cone_v0,
        "h1_passed": h1_passed,
    }
