"""Step 3: Hypothesis H2 - Short-term oversold mean reversion evaluation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.engine.indicators import compute_indicators
from src.eval.metrics import wilson_ci
from src.eval.stats_v2 import date_clustered_bootstrap_ci, holm_bonferroni, random_baseline_matched

HOLDING_DAYS = 5


def _ewma_sigma_94(close: pd.Series) -> pd.Series:
    r = close.pct_change(1).to_numpy(dtype=float)
    n = len(r)
    sig = np.full(n, np.nan, dtype=float)
    valid = np.where(np.isfinite(r))[0]
    if len(valid) < 20:
        return pd.Series(sig, index=close.index)
    var = max(float(np.var(r[valid[:20]])), 1e-8)
    for i in range(valid[0], n):
        if np.isfinite(r[i]):
            var = 0.94 * var + 0.06 * (r[i] ** 2)
        sig[i] = np.sqrt(max(var, 1e-8))
    sig[:20] = np.nan
    return pd.Series(sig, index=close.index)


def _prepare_h2_df(df: pd.DataFrame) -> pd.DataFrame:
    ind = compute_indicators(df)
    c = ind["close"].astype(float)
    o = ind["open"].astype(float)
    h = ind["high"].astype(float)
    l = ind["low"].astype(float)

    ind["ret_3d"] = c.pct_change(3)
    ind["sigma_ewma"] = _ewma_sigma_94(c)
    std20 = c.rolling(20, min_periods=20).std()
    ind["bb_low"] = ind["ma20"] - 2.0 * std20

    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    ind["atr14"] = tr.rolling(14, min_periods=14).mean()

    # Realistic entry: close[t+1] -> close[t+6]; sensitivity: open[t+1] -> close[t+6]
    ind["ret_close_t1"] = (c.shift(-1 - HOLDING_DAYS) / c.shift(-1)) - 1.0
    ind["ret_open_t1"] = (c.shift(-1 - HOLDING_DAYS) / o.shift(-1)) - 1.0

    # Causal signal definitions at close t
    ind["R1"] = ind["rsi14"] < 30.0
    ind["R2"] = ind["rsi14"] < 25.0
    ind["R3"] = ind["ret_3d"] < (-1.5 * np.sqrt(3.0) * ind["sigma_ewma"])
    ind["R4"] = c < ind["bb_low"]
    ind["R5"] = (c - ind["ma20"]) < (-1.5 * ind["atr14"])
    ind["R6"] = ind["R3"] & (ind["rsi14"] < 35.0)
    return ind


def _non_overlapping_mask(sig_mask: np.ndarray, hold: int = HOLDING_DAYS) -> np.ndarray:
    out = np.zeros_like(sig_mask, dtype=bool)
    cooldown = 0
    for i in range(len(sig_mask)):
        if cooldown > 0:
            cooldown -= 1
            continue
        if sig_mask[i]:
            out[i] = True
            cooldown = hold
    return out


def _eval_variant_on_segment(
    panel: pd.DataFrame,
    rule_col: str,
    segment: str,
    jkse_above_ma50: pd.Series,
    fee: float = 0.004,
) -> dict[str, Any]:
    sub = panel[(panel["segment"] == segment) & panel["liq_ok"]].dropna(subset=["ret_close_t1", "ew_ret_close_t1"]).copy()
    if sub.empty:
        return {"n_sig": 0}

    sig_mask = sub[rule_col].to_numpy(dtype=bool)
    trades = sub[sig_mask]
    n_sig = len(trades)
    n_eff = round(n_sig / float(HOLDING_DAYS), 1)
    if n_sig == 0:
        return {"n_sig": 0, "n_eff": 0.0, "excess_ci": {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "p_val": 1.0}}

    dates_t = trades["date"].to_numpy()
    raw_net = (trades["ret_close_t1"].to_numpy(dtype=float) - fee) * 100.0
    ew_ret = trades["ew_ret_close_t1"].to_numpy(dtype=float) * 100.0
    excess = raw_net - ew_ret

    raw_ci = date_clustered_bootstrap_ci(dates_t, raw_net, block_size=10, n_boot=5000, seed=42)
    ex_ci = date_clustered_bootstrap_ci(dates_t, excess, block_size=10, n_boot=5000, seed=42)

    wins_eff = int(round(float(np.mean(excess > 0.0)) * max(1.0, n_eff)))
    wr_eff = round(float(np.mean(excess > 0.0)) * 100.0, 2)
    wr_ci = wilson_ci(wins_eff, max(1, int(round(n_eff))))

    # Matched random baseline on excess return
    all_excess = ((sub["ret_close_t1"].to_numpy(dtype=float) - fee) - sub["ew_ret_close_t1"].to_numpy(dtype=float)) * 100.0
    rand_pct = random_baseline_matched(sub["date"].to_numpy(), all_excess, n_sig, n_seeds=500, seed=42)

    # Calendar year breakdown
    years = trades["date"].astype(str).str[:4]
    yr_means = trades.assign(ex=excess).groupby(years)["ex"].mean()
    pct_pos_years = round(float((yr_means > 0).mean()) * 100.0, 1) if len(yr_means) > 0 else 0.0

    # Per-ticker % positive
    tk_means = trades.assign(ex=excess).groupby("ticker")["ex"].mean()
    pct_pos_tickers = round(float((tk_means > 0).mean()) * 100.0, 1) if len(tk_means) > 0 else 0.0

    # Cost sensitivity & open t+1 entry
    ex_06 = date_clustered_bootstrap_ci(dates_t, ((trades["ret_close_t1"].to_numpy(dtype=float) - 0.006) * 100.0) - ew_ret, block_size=10, n_boot=2000, seed=42)["mean"]
    ex_10 = date_clustered_bootstrap_ci(dates_t, ((trades["ret_close_t1"].to_numpy(dtype=float) - 0.010) * 100.0) - ew_ret, block_size=10, n_boot=2000, seed=42)["mean"]
    open_ok = trades["ret_open_t1"].notna().to_numpy()
    ex_open = date_clustered_bootstrap_ci(
        dates_t[open_ok],
        ((trades["ret_open_t1"].to_numpy(dtype=float)[open_ok] - fee) * 100.0) - ew_ret[open_ok],
        block_size=10,
        n_boot=2000,
        seed=42,
    )["mean"] if open_ok.any() else 0.0

    # Non-overlapping single position per ticker
    no_ov_parts = []
    for _, grp in sub.groupby("ticker", sort=False):
        m = _non_overlapping_mask(grp[rule_col].to_numpy(dtype=bool), HOLDING_DAYS)
        if m.any():
            no_ov_parts.append(grp.iloc[m])
    if no_ov_parts:
        no_ov_df = pd.concat(no_ov_parts, ignore_index=True)
        no_ov_ex = ((no_ov_df["ret_close_t1"].to_numpy(dtype=float) - fee) - no_ov_df["ew_ret_close_t1"].to_numpy(dtype=float)) * 100.0
        no_ov_ci = date_clustered_bootstrap_ci(no_ov_df["date"].to_numpy(), no_ov_ex, block_size=10, n_boot=2000, seed=42)
    else:
        no_ov_ci = {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}

    # IHSG regime breakdown (reported only, never used to select)
    j_map = trades["date"].map(jkse_above_ma50)
    ex_j_up = round(float(np.mean(excess[j_map == True])), 3) if (j_map == True).any() else None
    ex_j_dn = round(float(np.mean(excess[j_map == False])), 3) if (j_map == False).any() else None

    return {
        "n_sig": n_sig,
        "n_eff": n_eff,
        "raw_net_ci": raw_ci,
        "excess_ci": ex_ci,
        "wr_excess": wr_eff,
        "wr_ci_eff": wr_ci,
        "rand_pct": rand_pct,
        "beats_rand_97_5": bool(ex_ci["mean"] > rand_pct["p97_5"]),
        "pct_pos_years": pct_pos_years,
        "pct_pos_tickers": pct_pos_tickers,
        "ex_fee_06": ex_06,
        "ex_fee_10": ex_10,
        "ex_open_t1": ex_open,
        "non_overlap_ex_ci": no_ov_ci,
        "ex_ihsg_above_ma50": ex_j_up,
        "ex_ihsg_below_ma50": ex_j_dn,
    }


def run_h2_evaluation(data: dict[str, pd.DataFrame], jkse_df: pd.DataFrame) -> dict[str, Any]:
    """Evaluates R1..R6 on DISCOVERY with Holm correction, then ONCE on FRESH-PAST and LOCK-RECENT."""
    parts = []
    for t, df in data.items():
        h2df = _prepare_h2_df(df)
        h2df["ticker"] = t
        parts.append(h2df)
    panel = pd.concat(parts, ignore_index=True)

    # Equal-weight universe return per date (only liquid bars)
    liq_panel = panel[panel["liq_ok"]]
    ew_by_date = liq_panel.groupby("date")["ret_close_t1"].mean().rename("ew_ret_close_t1")
    panel = panel.merge(ew_by_date, on="date", how="left")

    jkse_above = pd.Series(dtype=bool)
    if not jkse_df.empty:
        jc = jkse_df["close"].astype(float)
        jma50 = jc.rolling(50, min_periods=50).mean()
        jkse_above = pd.Series((jc > jma50).to_numpy(), index=jkse_df["date"].astype(str))

    rules = ["R1", "R2", "R3", "R4", "R5", "R6"]
    disc_res: dict[str, dict[str, Any]] = {}
    p_vals: list[float] = []
    for r in rules:
        res = _eval_variant_on_segment(panel, r, "DISCOVERY", jkse_above, fee=0.004)
        disc_res[r] = res
        p_vals.append(float(res.get("excess_ci", {}).get("p_val", 1.0)))

    p_holm = holm_bonferroni(p_vals)
    for r, ph in zip(rules, p_holm):
        disc_res[r]["p_holm"] = ph

    # Check FRESH-PAST availability
    fresh_n = int(((panel["segment"] == "FRESH-PAST") & panel["liq_ok"]).sum())
    fresh_available = fresh_n >= 500

    # Select at most ONE variant passing Holm (p_holm < 0.05) with positive excess mean
    passing = [r for r in rules if disc_res[r]["p_holm"] < 0.05 and disc_res[r]["excess_ci"]["mean"] > 0.0]
    chosen_rule = max(passing, key=lambda r: disc_res[r]["excess_ci"]["mean"]) if passing else None

    fresh_res = None
    lock_res = None
    h2_status = "H2 tidak terbukti"
    if chosen_rule is not None:
        fresh_res = _eval_variant_on_segment(panel, chosen_rule, "FRESH-PAST", jkse_above, fee=0.004) if fresh_available else None
        lock_res = _eval_variant_on_segment(panel, chosen_rule, "LOCK-RECENT", jkse_above, fee=0.004)
        if not fresh_available:
            h2_status = "eksploratori, tidak terkonfirmasi (FRESH-PAST tidak memadai)"
        else:
            ok_all = (
                fresh_res["excess_ci"]["ci_lo"] > 0.0
                and disc_res[chosen_rule]["excess_ci"]["mean"] > 0.0
                and lock_res["excess_ci"]["mean"] > 0.0
                and disc_res[chosen_rule]["pct_pos_years"] >= 60.0
                and fresh_res["pct_pos_years"] >= 60.0
                and fresh_res["ex_fee_06"] > 0.0
                and fresh_res["beats_rand_97_5"]
                and fresh_res["ex_open_t1"] > 0.0
            )
            h2_status = "H2 LOLOS PENUH" if ok_all else "H2 tidak terbukti (gagal kriteria konfirmasi)"

    return {
        "disc_res": disc_res,
        "fresh_available": fresh_available,
        "fresh_bars": fresh_n,
        "chosen_rule": chosen_rule,
        "fresh_res": fresh_res,
        "lock_res": lock_res,
        "h2_status": h2_status,
    }
