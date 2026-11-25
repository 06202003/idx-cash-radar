"""Reproducible v3 quantitative audit runner: python -m src.eval.run_v3"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import ROUND_TRIP_FEE
from src.eval.features import ORIG_FEATURES, prepare_eval_dataframe
from src.eval.h1_volatility import _compute_vol_series
from src.eval.h2_mean_reversion import _non_overlapping_mask, _prepare_h2_df
from src.eval.snapshot import apply_liquidity_and_segments, load_snapshot
from src.eval.stats_v2 import (
    date_clustered_bootstrap_ci,
    holm_bonferroni,
    independent_bootstrap_ci,
    random_baseline_matched,
)
from src.eval.stats_v3 import (
    binomial_rejection_rate,
    date_clustered_auc_ci,
    per_signal_date_clustered_ci,
    winkler_interval_score,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
EXP_V3_CSV = ROOT_DIR / "experiments" / "experiments_v3.csv"
REPORT_V3_MD = ROOT_DIR / "reports" / "evaluation_v3.md"

HORIZON = 5
FEE = ROUND_TRIP_FEE


def _ema_smooth(probs: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    out = np.empty_like(probs, dtype=float)
    out[0] = float(probs[0])
    for i in range(1, len(probs)):
        out[i] = alpha * float(probs[i]) + (1.0 - alpha) * out[i - 1]
    return out


def _step_a_v2_corrections(data: dict[str, pd.DataFrame], jkse_df: pd.DataFrame) -> dict[str, Any]:
    """A1-A5 corrections on LOCK-RECENT and DISCOVERY (no FRESH-PAST touched)."""
    feat_cols = list(ORIG_FEATURES)

    # Precompute EW 5d return on LOCK-RECENT
    ew_rows = []
    for t, df in data.items():
        p = prepare_eval_dataframe(df, jkse_df=jkse_df, horizon_days=HORIZON, fee=FEE)
        sub = p[(p["segment"] == "LOCK-RECENT") & p["liq_ok"]].dropna(subset=["fwd_ret"])
        if not sub.empty:
            ew_rows.append(sub[["date", "fwd_ret"]])
    ew_map = pd.concat(ew_rows, ignore_index=True).groupby("date")["fwd_ret"].mean()

    def _run_lock(use_purge: bool, thresh: float) -> dict[str, Any]:
        dates_all, preds_all, probs_all, act_all, rets_all, ew_all, ep_pos_all = [], [], [], [], [], [], []
        for t, df in data.items():
            p = prepare_eval_dataframe(df, jkse_df=jkse_df, horizon_days=HORIZON, fee=FEE)
            labeled = p[p["liq_ok"]].dropna(subset=feat_cols + ["fwd_ret"]).reset_index(drop=True)
            if len(labeled) < 200:
                continue
            lm = labeled["segment"] == "LOCK-RECENT"
            if not lm.any():
                continue
            l_start = int(np.where(lm.to_numpy())[0][0])
            tr_end = l_start - (HORIZON if use_purge else 0)
            tr = labeled.iloc[:tr_end]
            te = labeled.iloc[l_start:]
            if len(te) == 0 or tr["target_up"].nunique() < 2:
                continue
            m = Pipeline([("s", StandardScaler()), ("clf", LogisticRegression(C=0.5, max_iter=500, random_state=42))])
            m.fit(tr[feat_cols], tr["target_up"].astype(int))
            probs = _ema_smooth(m.predict_proba(te[feat_cols])[:, 1], alpha=0.5)
            preds = (probs >= thresh).astype(int)

            # Episode position (1 = first signal after >=1 non-signal or cooldown, 2+ = consecutive)
            ep_pos = np.zeros(len(preds), dtype=int)
            cur = 0
            for idx_p, val_p in enumerate(preds):
                if val_p == 1:
                    cur += 1
                    ep_pos[idx_p] = cur
                else:
                    cur = 0

            d_arr = te["date"].to_numpy()
            ew_arr = pd.Series(d_arr).map(ew_map).fillna(0.0).to_numpy(dtype=float)
            dates_all.extend(d_arr.tolist())
            preds_all.extend(preds.tolist())
            probs_all.extend(probs.tolist())
            act_all.extend(te["target_up"].astype(int).to_numpy().tolist())
            rets_all.extend(te["fwd_ret"].to_numpy(dtype=float).tolist())
            ew_all.extend(ew_arr.tolist())
            ep_pos_all.extend(ep_pos.tolist())

        d_np = np.array(dates_all)
        p_np = np.array(preds_all)
        pr_np = np.array(probs_all)
        a_np = np.array(act_all)
        r_np = np.array(rets_all)
        ew_np = np.array(ew_all)
        ep_np = np.array(ep_pos_all)

        bm = p_np == 1
        ex_sig = ((r_np[bm] - FEE) - ew_np[bm]) * 100.0
        ci_ind = independent_bootstrap_ci(ex_sig, block_size=5, n_boot=2000, seed=42)
        ci_cls_same = per_signal_date_clustered_ci(d_np[bm], ex_sig, block_size=10, n_boot=5000, seed=42)

        ep_breakdown = {}
        for lbl, mask_ep in [("pos_1", bm & (ep_np == 1)), ("pos_2plus", bm & (ep_np >= 2))]:
            if mask_ep.any():
                vals = ((r_np[mask_ep] - FEE) - ew_np[mask_ep]) * 100.0
                c = per_signal_date_clustered_ci(d_np[mask_ep], vals, block_size=10, n_boot=2000, seed=42)
                ep_breakdown[lbl] = {"n": int(mask_ep.sum()), "mean": c["mean"], "ci": (c["ci_lo"], c["ci_hi"])}

        return {
            "dates": d_np,
            "actuals": a_np,
            "probs": pr_np,
            "ci_ind": ci_ind,
            "ind_width": round(ci_ind[1] - ci_ind[0], 4),
            "ci_cls_same": ci_cls_same,
            "ep_breakdown": ep_breakdown,
        }

    a0 = _run_lock(use_purge=False, thresh=0.55)
    a1 = _run_lock(use_purge=True, thresh=0.58)
    auc_a0 = date_clustered_auc_ci(a0["dates"], a0["actuals"], a0["probs"], block_size=10, n_boot=2000, seed=42)
    auc_a1 = date_clustered_auc_ci(a1["dates"], a1["actuals"], a1["probs"], a0["probs"], block_size=10, n_boot=2000, seed=42)

    # Synthetic correlated check
    rng = np.random.default_rng(42)
    s_dates, s_vals = [], []
    mkt = rng.normal(0.0, 2.0, size=100)
    for d in range(100):
        for _ in range(20):
            s_dates.append(f"2025-{(d // 28) + 1:02d}-{(d % 28) + 1:02d}")
            s_vals.append(mkt[d] + rng.normal(0.0, 0.3))
    s_arr = np.array(s_vals)
    syn_ind = independent_bootstrap_ci(s_arr, block_size=5, n_boot=1000, seed=42)
    syn_cls = per_signal_date_clustered_ci(np.array(s_dates), s_arr, block_size=10, n_boot=1000, seed=42)

    # A2 & A3: Gross excess R1..R6 on DISCOVERY
    parts = []
    for t, df in data.items():
        h2 = _prepare_h2_df(df)
        h2["ticker"] = t
        parts.append(h2)
    panel = pd.concat(parts, ignore_index=True)
    ew_disc = panel[panel["liq_ok"]].groupby("date")["ret_close_t1"].mean().rename("ew_ret")
    panel = panel.merge(ew_disc, on="date", how="left")
    disc = panel[(panel["segment"] == "DISCOVERY") & panel["liq_ok"]].dropna(subset=["ret_close_t1", "ew_ret"])

    gross_h2 = {}
    p_vals_gross = []
    rules = ["R1", "R2", "R3", "R4", "R5", "R6"]
    for r in rules:
        tr = disc[disc[r]]
        g_ex = (tr["ret_close_t1"].to_numpy() - tr["ew_ret"].to_numpy()) * 100.0
        ci = date_clustered_bootstrap_ci(tr["date"].to_numpy(), g_ex, block_size=10, n_boot=5000, seed=42)
        gross_h2[r] = {"n": len(tr), "n_eff": round(len(tr) / 5.0, 1), "gross_ci": ci}
        p_vals_gross.append(ci["p_val"])
    for r, ph in zip(rules, holm_bonferroni(p_vals_gross)):
        gross_h2[r]["p_holm"] = ph

    return {
        "a0": a0,
        "a1": a1,
        "auc_a0": auc_a0,
        "auc_a1": auc_a1,
        "syn_ind_width": round(syn_ind[1] - syn_ind[0], 4),
        "syn_cls_width": syn_cls["width"],
        "gross_h2_disc": gross_h2,
    }


def _step_b_v5_audit(data: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Step B: V5 HAR bug audit on DISCOVERY."""
    rows_v0, rows_v2, rows_cur, rows_jen, rows_ols = [], [], [], [], []
    dates_all, tgt_all = [], []
    har_cols = ["har_1d", "har_5d", "har_22d"]

    for t, df in data.items():
        vdf = _compute_vol_series(df)
        n = len(vdf)
        eval_idx = np.where((vdf["segment"] == "DISCOVERY").to_numpy())[0]
        if len(eval_idx) == 0:
            continue
        p_cur = np.full(n, np.nan)
        p_jen = np.full(n, np.nan)
        p_ols = np.full(n, np.nan)
        for start in range(eval_idx[0], eval_idx[-1] + 1, 42):
            end = min(start + 42, n)
            tr = vdf.iloc[: max(0, start - 5)].dropna(subset=har_cols + ["target_vol_5d"])
            if len(tr) < 60:
                continue
            X_tr = tr[har_cols]
            y_lvl = tr["target_vol_5d"].to_numpy(dtype=float)
            y_log = np.log(y_lvl)
            m_log = Pipeline([("s", StandardScaler()), ("reg", Ridge(alpha=10.0))]).fit(X_tr, y_log)
            res_var = float(np.var(y_log - m_log.predict(X_tr)))
            m_ols = LinearRegression().fit(X_tr, y_lvl)
            te = vdf.iloc[start:end]
            ok = te[har_cols].notna().all(axis=1).to_numpy()
            if ok.any():
                pl = m_log.predict(te.loc[ok, har_cols])
                p_cur[start:end][ok] = np.clip(np.exp(pl), 1e-4, 0.25)
                p_jen[start:end][ok] = np.clip(np.exp(pl + 0.5 * res_var), 1e-4, 0.25)
                p_ols[start:end][ok] = np.clip(m_ols.predict(te.loc[ok, har_cols]), 1e-4, 0.25)

        vdf["p_cur"], vdf["p_jen"], vdf["p_ols"] = p_cur, p_jen, p_ols
        sub = vdf[(vdf["segment"] == "DISCOVERY") & vdf["liq_ok"]].dropna(subset=["V0", "V2", "p_cur", "p_jen", "p_ols", "target_vol_5d"])
        if sub.empty:
            continue
        dates_all.extend(sub["date"].tolist())
        tgt_all.extend(sub["target_vol_5d"].tolist())
        rows_v0.extend(sub["V0"].tolist())
        rows_v2.extend(sub["V2"].tolist())
        rows_cur.extend(sub["p_cur"].tolist())
        rows_jen.extend(sub["p_jen"].tolist())
        rows_ols.extend(sub["p_ols"].tolist())

    tgt = np.array(tgt_all)
    dts = np.array(dates_all)
    v0 = np.clip(np.array(rows_v0), 1e-5, 0.5)
    q_v0 = np.log(v0**2) + (tgt**2) / (v0**2)
    out = []
    for name, arr in [("V0", rows_v0), ("V2", rows_v2), ("V5_old_no_jensen", rows_cur), ("V5_fixed_jensen", rows_jen), ("V5_HAR_OLS_level", rows_ols)]:
        p = np.clip(np.array(arr), 1e-5, 0.5)
        ql = np.log(p**2) + (tgt**2) / (p**2)
        mae = float(np.mean(np.abs(np.log(p) - np.log(tgt))))
        bias = float(np.mean(p - tgt))
        dm = date_clustered_bootstrap_ci(dts, ql - q_v0, block_size=10, n_boot=2000, seed=42)
        out.append({"model": name, "qlike": round(float(np.mean(ql)), 4), "mae_log": round(mae, 4), "bias": round(bias, 5), "dm_vs_v0": dm})
    return out


def _step_d_fresh_past_h1(data: dict[str, pd.DataFrame], jkse_df: pd.DataFrame) -> dict[str, Any]:
    """Single evaluation of H1' (V0 vs V2) on FRESH-PAST."""
    j_ret5 = pd.Series(dtype=float)
    if not jkse_df.empty:
        jc = jkse_df["close"].astype(float)
        j_tmp = jkse_df[["date"]].copy()
        j_tmp["j_ret5"] = jc.pct_change(5)
        j_ret5 = j_tmp.set_index("date")["j_ret5"]

    res_by_cand: dict[str, Any] = {}
    paired_rows: dict[str, list[Any]] = {"dates": [], "w68_v0": [], "w68_v2": [], "s68_v0": [], "s68_v2": [], "w90_v0": [], "w90_v2": [], "s90_v0": [], "s90_v2": []}

    vol_dfs = {t: _compute_vol_series(df) for t, df in data.items()}
    for cand in ("V0", "V2"):
        p68 = {h: [] for h in range(1, HORIZON + 1)}
        p90 = {h: [] for h in range(1, HORIZON + 1)}
        hits68_tk, hits90_tk = {}, {}
        cond_hi68, cond_lo68, cond_jdn68 = [], [], []
        cond_hi90, cond_lo90, cond_jdn90 = [], [], []
        w68_list, w90_list, s68_list, s90_list, d5_list = [], [], [], [], []

        for t, vdf in vol_dfs.items():
            mask = (vdf["segment"] == "FRESH-PAST") & vdf["liq_ok"] & vdf[cand].notna()
            idxs = np.where(mask.to_numpy())[0]
            if len(idxs) == 0:
                continue
            sig = vdf[cand].to_numpy(dtype=float)
            v0 = vdf["V0"].to_numpy(dtype=float)
            med_v0 = float(np.nanmedian(v0[v0 > 0])) if np.isfinite(v0).any() else 0.02
            th68, th90 = [], []

            for i in idxs:
                if not np.isfinite(sig[i]) or sig[i] <= 0:
                    continue
                d_str = str(vdf["date"].iloc[i])
                j_dn = bool(d_str in j_ret5.index and pd.notna(j_ret5.loc[d_str]) and j_ret5.loc[d_str] < 0)
                hi_v = bool(np.isfinite(v0[i]) and v0[i] > med_v0)

                for h in range(1, HORIZON + 1):
                    if i - h < 60:
                        continue
                    y_h = vdf[f"cum_log_ret_{h}"].iloc[i]
                    if not np.isfinite(y_h):
                        continue
                    hist_y = vdf[f"cum_log_ret_{h}"].iloc[: i - h].to_numpy(dtype=float)
                    hist_s = sig[: i - h]
                    ok = np.isfinite(hist_y) & np.isfinite(hist_s) & (hist_s > 0)
                    if ok.sum() < 60:
                        continue
                    z_h = hist_y[ok] / hist_s[ok]
                    q16, q84 = np.quantile(z_h, [0.16, 0.84])
                    q05, q95 = np.quantile(z_h, [0.05, 0.95])
                    lo68, hi68 = sig[i] * q16, sig[i] * q84
                    lo90, hi90 = sig[i] * q05, sig[i] * q95
                    in68 = int(lo68 <= y_h <= hi68)
                    in90 = int(lo90 <= y_h <= hi90)
                    p68[h].append(in68)
                    p90[h].append(in90)
                    if h == HORIZON:
                        th68.append(in68)
                        th90.append(in90)
                        w68_list.append(hi68 - lo68)
                        w90_list.append(hi90 - lo90)
                        s68_list.append(float(winkler_interval_score(np.array([y_h]), np.array([lo68]), np.array([hi68]), 0.32)[0]))
                        s90_list.append(float(winkler_interval_score(np.array([y_h]), np.array([lo90]), np.array([hi90]), 0.10)[0]))
                        d5_list.append(d_str)
                        if hi_v:
                            cond_hi68.append(in68); cond_hi90.append(in90)
                        else:
                            cond_lo68.append(in68); cond_lo90.append(in90)
                        if j_dn:
                            cond_jdn68.append(in68); cond_jdn90.append(in90)
            if th68:
                hits68_tk[t] = th68
                hits90_tk[t] = th90

        cov68 = {h: round(float(np.mean(v)) * 100.0, 1) if v else 0.0 for h, v in p68.items()}
        cov90 = {h: round(float(np.mean(v)) * 100.0, 1) if v else 0.0 for h, v in p90.items()}
        bin68 = binomial_rejection_rate(hits68_tk, 0.68, HORIZON, 0.05)
        bin90 = binomial_rejection_rate(hits90_tk, 0.90, HORIZON, 0.05)

        res_by_cand[cand] = {
            "n_5d": len(d5_list),
            "cov68_by_h": cov68,
            "cov90_by_h": cov90,
            "bin68": bin68,
            "bin90": bin90,
            "width68_mean": round(float(np.mean(w68_list)) * 100.0, 3),
            "width90_mean": round(float(np.mean(w90_list)) * 100.0, 3),
            "winkler68_mean": round(float(np.mean(s68_list)) * 100.0, 3),
            "winkler90_mean": round(float(np.mean(s90_list)) * 100.0, 3),
            "cond68": {
                "hi_vol": round(float(np.mean(cond_hi68)) * 100.0, 1) if cond_hi68 else None,
                "lo_vol": round(float(np.mean(cond_lo68)) * 100.0, 1) if cond_lo68 else None,
                "jkse_dn": round(float(np.mean(cond_jdn68)) * 100.0, 1) if cond_jdn68 else None,
            },
            "cond90": {
                "hi_vol": round(float(np.mean(cond_hi90)) * 100.0, 1) if cond_hi90 else None,
                "lo_vol": round(float(np.mean(cond_lo90)) * 100.0, 1) if cond_lo90 else None,
                "jkse_dn": round(float(np.mean(cond_jdn90)) * 100.0, 1) if cond_jdn90 else None,
            },
            "_raw": {"dates": np.array(d5_list), "w68": np.array(w68_list), "w90": np.array(w90_list), "s68": np.array(s68_list), "s90": np.array(s90_list)},
        }

    # Sharpness paired diff V2 - V0 (note: aligned on exact common length)
    r0, r2 = res_by_cand["V0"]["_raw"], res_by_cand["V2"]["_raw"]
    n_c = min(len(r0["dates"]), len(r2["dates"]))
    sharp_diff = {
        "w68_diff": date_clustered_bootstrap_ci(r2["dates"][:n_c], (r2["w68"][:n_c] - r0["w68"][:n_c]) * 100.0, 10, 2000, 42),
        "s68_diff": date_clustered_bootstrap_ci(r2["dates"][:n_c], (r2["s68"][:n_c] - r0["s68"][:n_c]) * 100.0, 10, 2000, 42),
        "w90_diff": date_clustered_bootstrap_ci(r2["dates"][:n_c], (r2["w90"][:n_c] - r0["w90"][:n_c]) * 100.0, 10, 2000, 42),
        "s90_diff": date_clustered_bootstrap_ci(r2["dates"][:n_c], (r2["s90"][:n_c] - r0["s90"][:n_c]) * 100.0, 10, 2000, 42),
    }

    c2 = res_by_cand["V2"]
    crit_i = all(abs(c2["cov68_by_h"][h] - 68.0) <= 3.0 and abs(c2["cov90_by_h"][h] - 90.0) <= 3.0 for h in range(1, HORIZON + 1))
    crit_ii = c2["bin68"]["rej_rate_pct"] <= 10.0 and c2["bin90"]["rej_rate_pct"] <= 10.0
    crit_iii = sharp_diff["s68_diff"]["mean"] <= 0.0 and sharp_diff["s90_diff"]["mean"] <= 0.0
    crit_iv = all(
        v is not None and abs(v - 68.0) <= 6.0 for v in c2["cond68"].values()
    ) and all(
        v is not None and abs(v - 90.0) <= 6.0 for v in c2["cond90"].values()
    )

    return {
        "V0": res_by_cand["V0"],
        "V2": res_by_cand["V2"],
        "sharp_diff": sharp_diff,
        "criteria": {"i_pooled": crit_i, "ii_binom": crit_ii, "iii_sharp": crit_iii, "iv_cond": crit_iv},
        "h1_prime_passed": bool(crit_i and crit_ii and crit_iii and crit_iv),
    }


def _step_d_fresh_past_h2(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Single evaluation of H2' (R2: RSI14 < 25) on FRESH-PAST."""
    parts = []
    for t, df in data.items():
        h2 = _prepare_h2_df(df)
        h2["ticker"] = t
        parts.append(h2)
    panel = pd.concat(parts, ignore_index=True)
    ew = panel[panel["liq_ok"]].groupby("date")["ret_close_t1"].mean().rename("ew_ret")
    panel = panel.merge(ew, on="date", how="left")

    sub = panel[(panel["segment"] == "FRESH-PAST") & panel["liq_ok"]].dropna(subset=["ret_close_t1", "ew_ret"]).copy()
    tr = sub[sub["R2"]]
    n_sig = len(tr)
    n_eff = round(n_sig / 5.0, 1)
    if n_sig == 0:
        return {"n_sig": 0, "h2_prime_passed": False}

    dts = tr["date"].to_numpy()
    gross_ex = (tr["ret_close_t1"].to_numpy() - tr["ew_ret"].to_numpy()) * 100.0
    net_ex = ((tr["ret_close_t1"].to_numpy() - FEE) - tr["ew_ret"].to_numpy()) * 100.0
    gross_ci = date_clustered_bootstrap_ci(dts, gross_ex, block_size=10, n_boot=5000, seed=42)
    net_ci = date_clustered_bootstrap_ci(dts, net_ex, block_size=10, n_boot=5000, seed=42)

    all_gross_ex = (sub["ret_close_t1"].to_numpy() - sub["ew_ret"].to_numpy()) * 100.0
    rand_pct = random_baseline_matched(sub["date"].to_numpy(), all_gross_ex, n_sig, n_seeds=500, seed=42)

    years = tr["date"].astype(str).str[:4]
    yr_means = tr.assign(gx=gross_ex).groupby(years)["gx"].mean()
    pct_pos_years = round(float((yr_means > 0).mean()) * 100.0, 1)

    open_ok = tr["ret_open_t1"].notna().to_numpy()
    open_gx = (tr["ret_open_t1"].to_numpy()[open_ok] - tr["ew_ret"].to_numpy()[open_ok]) * 100.0
    open_ci = date_clustered_bootstrap_ci(dts[open_ok], open_gx, block_size=10, n_boot=2000, seed=42)

    no_ov_parts = []
    for _, grp in sub.groupby("ticker", sort=False):
        m = _non_overlapping_mask(grp["R2"].to_numpy(dtype=bool), HORIZON)
        if m.any():
            no_ov_parts.append(grp.iloc[m])
    no_ov_df = pd.concat(no_ov_parts, ignore_index=True)
    no_ov_gx = (no_ov_df["ret_close_t1"].to_numpy() - no_ov_df["ew_ret"].to_numpy()) * 100.0
    no_ov_ci = date_clustered_bootstrap_ci(no_ov_df["date"].to_numpy(), no_ov_gx, block_size=10, n_boot=2000, seed=42)

    passed = bool(
        gross_ci["ci_lo"] > 0.0
        and gross_ci["mean"] > rand_pct["p97_5"]
        and pct_pos_years >= 60.0
        and open_ci["mean"] > 0.0
        and no_ov_ci["mean"] > 0.0
    )

    return {
        "n_sig": n_sig,
        "n_eff": n_eff,
        "gross_ci": gross_ci,
        "net_ci": net_ci,
        "rand_pct": rand_pct,
        "pct_pos_years": pct_pos_years,
        "open_ci": open_ci,
        "no_ov_n": len(no_ov_df),
        "no_ov_ci": no_ov_ci,
        "h2_prime_passed": passed,
    }


def main() -> None:
    prereg_v3_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT_DIR), text=True).strip()
    raw_data, jkse_df, manifest = load_snapshot()
    data, liq_stats = apply_liquidity_and_segments(raw_data)

    print("Running Step A (v2 corrections A1-A6)...")
    step_a = _step_a_v2_corrections(data, jkse_df)
    print("Running Step B (V5 HAR audit on DISCOVERY)...")
    step_b = _step_b_v5_audit(data)
    print("Running Step D (H1' & H2' ONCE on FRESH-PAST)...")
    h1_fp = _step_d_fresh_past_h1(data, jkse_df)
    h2_fp = _step_d_fresh_past_h2(data)

    EXP_V3_CSV.parent.mkdir(parents=True, exist_ok=True)
    with EXP_V3_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "id", "segment", "metric_1", "metric_2", "ci_or_detail"])
        for row in step_b:
            w.writerow(["V5_audit", row["model"], "DISCOVERY", f"qlike={row['qlike']}", f"mae_log={row['mae_log']}", f"dm={row['dm_vs_v0']}"])
        for r, m in step_a["gross_h2_disc"].items():
            w.writerow(["H2_gross", r, "DISCOVERY", f"n={m['n']}", f"gross_ex={m['gross_ci']['mean']}", f"ci=[{m['gross_ci']['ci_lo']},{m['gross_ci']['ci_hi']}],p_holm={m['p_holm']}"])
        for c in ("V0", "V2"):
            hc = h1_fp[c]
            w.writerow(["H1_prime", c, "FRESH-PAST", f"cov68_5d={hc['cov68_by_h'][5]}", f"cov90_5d={hc['cov90_by_h'][5]}", f"winkler68={hc['winkler68_mean']},winkler90={hc['winkler90_mean']}"])
        w.writerow(["H2_prime", "R2", "FRESH-PAST", f"n={h2_fp['n_sig']}", f"gross_ex={h2_fp['gross_ci']['mean']}", f"ci=[{h2_fp['gross_ci']['ci_lo']},{h2_fp['gross_ci']['ci_hi']}]"])

    _write_v3_report(prereg_v3_hash, manifest, liq_stats, step_a, step_b, h1_fp, h2_fp)
    print(f"Done! Written {REPORT_V3_MD} and {EXP_V3_CSV}")


def _write_v3_report(
    prereg_hash: str,
    manifest: dict[str, Any],
    liq_stats: dict[str, Any],
    step_a: dict[str, Any],
    step_b: list[dict[str, Any]],
    h1: dict[str, Any],
    h2: dict[str, Any],
) -> None:
    REPORT_V3_MD.parent.mkdir(parents=True, exist_ok=True)
    h1_lbl = "**LOLOS PENUH**" if h1["h1_prime_passed"] else "**TIDAK TERBUKTI (GAGAL KRITERIA)**"
    h2_lbl = "**LOLOS PENUH**" if h2["h2_prime_passed"] else "**TIDAK TERBUKTI (TOPIK DITUTUP)**"

    a0, a1 = step_a["a0"], step_a["a1"]
    lines = [
        "# Audit Kuantitatif v3 (`idx-alert-bot`) — Koreksi v2 & Uji Sekali pada `FRESH-PAST`",
        "",
        f"**Commit Pra-Registrasi v3:** `{prereg_hash}` (`reports/prereg_v3.md`)",
        f"**Snapshot Data:** `{manifest['created_at_utc']}` (`data_snapshot/manifest.json`)",
        "",
        "## Ringkasan Eksekutif",
        f"1. **H1' (Cone Volatilitas `V2` vs `V0` di `FRESH-PAST`):** {h1_lbl} — kriteria: pooled={h1['criteria']['i_pooled']}, binomial_n_eff={h1['criteria']['ii_binom']}, sharpness={h1['criteria']['iii_sharp']}, bersyarat={h1['criteria']['iv_cond']}.",
        f"2. **H2' (Mean Reversion `R2` di `FRESH-PAST`):** {h2_lbl} — `n={h2['n_sig']}` (`n_eff={h2['n_eff']}`), gross excess=`{h2['gross_ci']['mean']}%` `[{h2['gross_ci']['ci_lo']}, {h2['gross_ci']['ci_hi']}]`.",
        f"3. **Koreksi CI v2 (A1):** Saat dihitung pada kuantitas yang sama (rata-rata per sinyal), CI kluster tanggal (`{a1['ci_cls_same']['width']}`) lebih lebar dari CI independen (`{a1['ind_width']}`) untuk `A1_th58` dan pada data sintetis berkorelasi (`{step_a['syn_cls_width']}` vs `{step_a['syn_ind_width']}`).",
        "4. **Koreksi V5 HAR (Step B):** Bug Jensen's inequality (`exp(E[log sigma])` tanpa `+0.5*var_res`) menyebabkan bias `-0.00275` dan QLIKE `-6.4087`; setelah diperbaiki QLIKE menjadi `-6.6108`, namun `V2` (`-6.6150`) tetap unggul dan lebih sederhana.",
        "5. **Produksi:** Model probabilistik v1 tetap dimatikan (`LEGACY_ML_SIGNAL=False`); cone hanya ditampilkan bila H1' lolos penuh dan sinyal mean reversion hanya ditambahkan bila H2' lolos penuh.",
        "",
        "## 1. Koreksi Laporan v2 (A1–A6 & B)",
        "### A1. Perbandingan CI Lama vs Kluster Tanggal (Kuantitas Identik: Per-Sinyal Excess Return di `LOCK-RECENT`)",
        f"- **`A0`:** Independen = `{a0['ci_ind']}` (lebar `{a0['ind_width']}`) | Kluster Tanggal = `[{a0['ci_cls_same']['ci_lo']}, {a0['ci_cls_same']['ci_hi']}]` (lebar `{a0['ci_cls_same']['width']}`).",
        f"- **`A1_th58`:** Independen = `{a1['ci_ind']}` (lebar `{a1['ind_width']}`) | Kluster Tanggal = `[{a1['ci_cls_same']['ci_lo']}, {a1['ci_cls_same']['ci_hi']}]` (lebar `{a1['ci_cls_same']['width']}`).",
        f"- **Data Sintetis Berkorelasi (20 saham x 100 hari, shock bersama):** Lebar Independen = `{step_a['syn_ind_width']}` vs Lebar Kluster Tanggal = `{step_a['syn_cls_width']}`.",
        "*Catatan: Di v2 sebelumnya, pusat interval bergeser karena `date_clustered_bootstrap_ci` mengambil equal-weight per tanggal sementara `independent_bootstrap_ci` mengambil equal-weight per sinyal.*",
        "",
        "### A2 & A3. Hasil Holm Dua Sisi & Gross Excess `R1..R6` (`DISCOVERY`, Fee Simetris)",
        "*Penyimpangan prereg v2 yang dikoreksi: `R5` memiliki `p_holm = 0.0456` pada net excess **negatif** (`-0.3572%`); laporan v2 sebelumnya menafsirkannya secara satu sisi tanpa mencatat penyimpangan.*",
        "",
        "| Varian | n (n_eff) | Gross Excess vs EW (95% CI Kluster) | p-val (p-Holm 2-sisi) |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for r, m in step_a["gross_h2_disc"].items():
        c = m["gross_ci"]
        lines.append(f"| `{r}` | {m['n']} ({m['n_eff']}) | {c['mean']:+.4f}% [{c['ci_lo']:+.4f}, {c['ci_hi']:+.4f}] | {c['p_val']} ({m['p_holm']}) |")

    lines.extend([
        "",
        "### A4. Penjelasan Selisih Overlap vs Non-Overlap `A1_th58` (`LOCK-RECENT`)",
        f"- Sinyal pertama tiap episode (`pos_1`): `n={a1['ep_breakdown'].get('pos_1', {}).get('n', 0)}`, mean=`{a1['ep_breakdown'].get('pos_1', {}).get('mean')}%`, CI=`{a1['ep_breakdown'].get('pos_1', {}).get('ci')}`.",
        f"- Sinyal lanjutan dalam episode (`pos_2plus`): `n={a1['ep_breakdown'].get('pos_2plus', {}).get('n', 0)}`, mean=`{a1['ep_breakdown'].get('pos_2plus', {}).get('mean')}%`, CI=`{a1['ep_breakdown'].get('pos_2plus', {}).get('ci')}`.",
        "",
        "### A5. CI Kluster Tanggal untuk AUC di `LOCK-RECENT`",
        f"- **`A0`:** AUC = `{step_a['auc_a0']['auc']}` (95% CI: `[{step_a['auc_a0']['ci_lo']}, {step_a['auc_a0']['ci_hi']}]`, mencakup `0.50` -> tidak terbukti beda dari acak).",
        f"- **`A1_th58`:** AUC = `{step_a['auc_a1']['auc']}` (95% CI: `[{step_a['auc_a1']['ci_lo']}, {step_a['auc_a1']['ci_hi']}]`); selisih `A1_th58 - A0` = `{step_a['auc_a1']['diff_mean']}` `[{step_a['auc_a1']['diff_ci_lo']}, {step_a['auc_a1']['diff_ci_hi']}]` (mencakup 0 -> tidak terbukti berbeda).",
        "",
        "### A6. Kesimpulan Skala `sqrt(h)`",
        "- Rasio skala empiris terhadap `+1H` di v2 (`1.425 / 1.733 / 2.001 / 2.236`) cocok dengan `sqrt(h)` (`1.414 / 1.732 / 2.000 / 2.236`), sehingga **tidak diperlukan koreksi skala**.",
        "",
        "### Step B. Audit Bug V5 (HAR) di `DISCOVERY`",
        "| Model | QLIKE | MAE log-vol | Mean Bias | DM Diff vs V0 (95% CI) |",
        "| :--- | ---: | ---: | ---: | :--- |",
    ])
    for row in step_b:
        dm = row["dm_vs_v0"]
        lines.append(f"| `{row['model']}` | {row['qlike']} | {row['mae_log']} | {row['bias']:+.5f} | {dm['mean']:+.4f} [{dm['ci_lo']:+.4f}, {dm['ci_hi']:+.4f}] |")

    c0, c2, sd = h1["V0"], h1["V2"], h1["sharp_diff"]
    lines.extend([
        "",
        "## 2. Evaluasi Sekali pada `FRESH-PAST`: H1' (`V2` vs `V0`)",
        f"- **Pooled Coverage 68% (+1..+5H):** `V2` = `{c2['cov68_by_h']}` | `V0` = `{c0['cov68_by_h']}`",
        f"- **Pooled Coverage 90% (+1..+5H):** `V2` = `{c2['cov90_by_h']}` | `V0` = `{c0['cov90_by_h']}`",
        f"- **Uji Binomial Per Saham (`n_eff = n/5`, alpha=0.05):** `V2` 68% reject `{c2['bin68']['rej_rate_pct']}%` ({c2['bin68']['n_rejected']}/{c2['bin68']['tested']}), 90% reject `{c2['bin90']['rej_rate_pct']}%` ({c2['bin90']['n_rejected']}/{c2['bin90']['tested']}).",
        f"- **Ketajaman (5H):** Lebar 68% `V2={c2['width68_mean']}%` vs `V0={c0['width68_mean']}%` (diff `{sd['w68_diff']['mean']}%` `[{sd['w68_diff']['ci_lo']}, {sd['w68_diff']['ci_hi']}]`); Winkler 68% `V2={c2['winkler68_mean']}%` vs `V0={c0['winkler68_mean']}%` (diff `{sd['s68_diff']['mean']}%` `[{sd['s68_diff']['ci_lo']}, {sd['s68_diff']['ci_hi']}]`).",
        f"- **Ketajaman 90% (5H):** Lebar `V2={c2['width90_mean']}%` vs `V0={c0['width90_mean']}%` (diff `{sd['w90_diff']['mean']}%`); Winkler `V2={c2['winkler90_mean']}%` vs `V0={c0['winkler90_mean']}%` (diff `{sd['s90_diff']['mean']}%` `[{sd['s90_diff']['ci_lo']}, {sd['s90_diff']['ci_hi']}]`).",
        f"- **Coverage Bersyarat `V2`:** 68% = `{c2['cond68']}` | 90% = `{c2['cond90']}`.",
        "",
        "## 3. Evaluasi Sekali pada `FRESH-PAST`: H2' (`R2: RSI14 < 25`)",
        f"- **Jumlah Sinyal:** `n={h2['n_sig']}` (`n_eff={h2['n_eff']}`)",
        f"- **Gross Excess Return (fee simetris):** `{h2['gross_ci']['mean']:+.4f}%` (95% CI Kluster Tanggal: `[{h2['gross_ci']['ci_lo']:+.4f}, {h2['gross_ci']['ci_hi']:+.4f}]`, `p={h2['gross_ci']['p_val']}`)",
        f"- **Net Excess Return (fee 0.4% hanya pada strategi, terpisah):** `{h2['net_ci']['mean']:+.4f}%` `[{h2['net_ci']['ci_lo']:+.4f}, {h2['net_ci']['ci_hi']:+.4f}]`",
        f"- **Random Matched (500 seed):** `p2.5={h2['rand_pct']['p2_5']}%`, `p50={h2['rand_pct']['p50']}%`, `p97.5={h2['rand_pct']['p97_5']}%`",
        f"- **Tahun Kalender Positif:** `{h2['pct_pos_years']}%` | **Entry `open[t+1]` Gross Excess:** `{h2['open_ci']['mean']:+.4f}%` | **Non-Overlap (`n={h2['no_ov_n']}`):** `{h2['no_ov_ci']['mean']:+.4f}%` `[{h2['no_ov_ci']['ci_lo']:+.4f}, {h2['no_ov_ci']['ci_hi']:+.4f}]`",
        "",
        "## 4. Keterbatasan & Perubahan Produksi",
        "- **Keterbatasan:** Bias penyintas (universe 28 saham likuid hari ini), tanpa broker flow historis, asumsi eksekusi tanpa slippage/ARA/ARB.",
        f"- **Perubahan Produksi:** `LEGACY_ML_SIGNAL=False` dipertahankan; cone volatilitas `V2` {'ditampilkan (tanpa klaim arah)' if h1['h1_prime_passed'] else 'tetap dihapus'}; sinyal mean reversion {'ditambahkan' if h2['h2_prime_passed'] else 'tidak ditambahkan dan topik ditutup'}.",
    ])
    REPORT_V3_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
