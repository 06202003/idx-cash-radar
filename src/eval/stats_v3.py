"""Statistical helpers for v3 audit: same-quantity date-clustered CI, Winkler score, binomial n_eff."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.metrics import roc_auc_score


def per_signal_date_clustered_ci(
    dates: np.ndarray,
    values: np.ndarray,
    block_size: int = 10,
    n_boot: int = 5000,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Date-clustered block bootstrap targeting the EXACT same per-signal mean as independent bootstrap:
    resamples blocks of dates, pools all signals on the resampled dates, and takes the grand mean.
    """
    df = pd.DataFrame({"date": dates, "val": np.asarray(values, dtype=float)}).dropna(subset=["val"])
    if df.empty:
        return {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "width": 0.0, "n": 0}
    point_mean = float(df["val"].mean())
    grouped = [g["val"].to_numpy(dtype=float) for _, g in df.groupby("date", sort=True)]
    n_d = len(grouped)
    if n_d < block_size:
        return {"mean": round(point_mean, 4), "ci_lo": round(point_mean, 4), "ci_hi": round(point_mean, 4), "width": 0.0, "n": len(df)}

    sums = np.array([g.sum() for g in grouped], dtype=float)
    cnts = np.array([len(g) for g in grouped], dtype=float)

    rng = np.random.default_rng(seed)
    n_blocks = max(1, int(math.ceil(n_d / block_size)))
    starts = rng.integers(0, n_d - block_size + 1, size=(n_boot, n_blocks))
    offsets = np.arange(block_size)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_boot, -1)[:, :n_d]
    boot_means = sums[idx].sum(axis=1) / np.maximum(cnts[idx].sum(axis=1), 1.0)
    lo, hi = np.percentile(boot_means, [2.5, 97.5])
    return {
        "mean": round(point_mean, 4),
        "ci_lo": round(float(lo), 4),
        "ci_hi": round(float(hi), 4),
        "width": round(float(hi - lo), 4),
        "n": len(df),
    }


def date_clustered_auc_ci(
    dates: np.ndarray,
    actuals: np.ndarray,
    probs_a: np.ndarray,
    probs_b: np.ndarray | None = None,
    block_size: int = 10,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict[str, Any]:
    """Date-clustered block bootstrap 95% CI for ROC AUC (and optional AUC_a - AUC_b)."""
    df = pd.DataFrame({"date": dates, "y": actuals, "pa": probs_a})
    if probs_b is not None:
        df["pb"] = probs_b
    auc_a = float(roc_auc_score(df["y"], df["pa"]))
    auc_b = float(roc_auc_score(df["y"], df["pb"])) if probs_b is not None else None

    unique_dates = np.sort(df["date"].unique())
    n_d = len(unique_dates)
    by_date = {d: grp for d, grp in df.groupby("date", sort=False)}
    rng = np.random.default_rng(seed)
    n_blocks = max(1, int(math.ceil(n_d / block_size)))
    starts = rng.integers(0, max(1, n_d - block_size + 1), size=(n_boot, n_blocks))
    offsets = np.arange(block_size)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_boot, -1)[:, :n_d]

    aucs_a, diffs = [], []
    for b in range(n_boot):
        sub = pd.concat([by_date[unique_dates[i]] for i in idx[b]], ignore_index=True)
        if sub["y"].nunique() < 2:
            continue
        aa = float(roc_auc_score(sub["y"], sub["pa"]))
        aucs_a.append(aa)
        if probs_b is not None:
            diffs.append(aa - float(roc_auc_score(sub["y"], sub["pb"])))

    lo_a, hi_a = np.percentile(aucs_a, [2.5, 97.5])
    out: dict[str, Any] = {
        "auc": round(auc_a, 4),
        "ci_lo": round(float(lo_a), 4),
        "ci_hi": round(float(hi_a), 4),
    }
    if probs_b is not None and diffs:
        lo_d, hi_d = np.percentile(diffs, [2.5, 97.5])
        out["diff_mean"] = round(float(auc_a - auc_b), 4)
        out["diff_ci_lo"] = round(float(lo_d), 4)
        out["diff_ci_hi"] = round(float(hi_d), 4)
    return out


def winkler_interval_score(
    y: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    alpha: float,
) -> np.ndarray:
    """Proper scoring rule for interval forecasts: width + (2/alpha)*miss_penalty."""
    width = hi - lo
    below = np.where(y < lo, (2.0 / alpha) * (lo - y), 0.0)
    above = np.where(y > hi, (2.0 / alpha) * (y - hi), 0.0)
    return width + below + above


def binomial_rejection_rate(
    hits_by_ticker: dict[str, list[int]],
    nominal_p: float,
    horizon: int = 5,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Two-sided binomial test per ticker using n_eff = max(1, round(n / horizon))."""
    rejected = []
    tested = 0
    for t, hits in hits_by_ticker.items():
        n = len(hits)
        if n < horizon:
            continue
        n_eff = max(1, int(round(n / float(horizon))))
        k_eff = min(n_eff, max(0, int(round(float(np.mean(hits)) * n_eff))))
        pval = float(binomtest(k_eff, n_eff, p=nominal_p, alternative="two-sided").pvalue)
        tested += 1
        if pval < alpha:
            rejected.append((t, round(float(np.mean(hits)) * 100.0, 1), n_eff, round(pval, 4)))
    rej_rate = round((len(rejected) / tested) * 100.0, 1) if tested > 0 else 0.0
    return {"tested": tested, "n_rejected": len(rejected), "rej_rate_pct": rej_rate, "rejected": rejected}
