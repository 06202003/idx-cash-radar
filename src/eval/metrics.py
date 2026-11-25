"""Statistical metrics, confidence intervals, and paired block-bootstrap tests."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, log_loss, roc_auc_score


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (returned in %)."""
    if n <= 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2)


def block_bootstrap_ci(
    values: np.ndarray,
    block_size: int = 5,
    n_boot: int = 500,
    seed: int = 42,
) -> tuple[float, float]:
    """Circular/moving block bootstrap 95% CI for the mean of serially correlated series."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    if n < block_size:
        m = float(np.mean(values))
        return round(m, 4), round(m, 4)

    rng = np.random.default_rng(seed)
    n_blocks = max(1, int(math.ceil(n / block_size)))
    max_start = n - block_size
    starts = rng.integers(0, max_start + 1, size=(n_boot, n_blocks))
    offsets = np.arange(block_size)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_boot, -1)[:, :n]
    means = values[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


def paired_block_bootstrap_diff(
    a: np.ndarray,
    b: np.ndarray,
    block_size: int = 5,
    n_boot: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Paired block bootstrap for mean(a - b) with 95% CI and zero-exclusion flag."""
    diff = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    valid = np.isfinite(diff)
    diff = diff[valid]
    if len(diff) == 0:
        return {"mean_diff": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "significant": False}
    mean_d = round(float(np.mean(diff)), 4)
    lo, hi = block_bootstrap_ci(diff, block_size=block_size, n_boot=n_boot, seed=seed)
    sig = bool((lo > 0.0 and hi > 0.0) or (lo < 0.0 and hi < 0.0))
    return {"mean_diff": mean_d, "ci_lo": lo, "ci_hi": hi, "significant": sig}


def calibration_table(probs: np.ndarray, actuals: np.ndarray, n_bins: int = 5) -> list[dict[str, Any]]:
    """Computes probability calibration bins vs realized positive frequency."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        cnt = int(mask.sum())
        rows.append({
            "bin": f"[{lo:.1f}, {hi:.1f}]",
            "n": cnt,
            "mean_pred": round(float(probs[mask].mean()) * 100.0, 1) if cnt > 0 else None,
            "realized_up": round(float(actuals[mask].mean()) * 100.0, 1) if cnt > 0 else None,
        })
    return rows


def compute_classification_metrics(
    preds: np.ndarray,
    probs: np.ndarray | None,
    actuals: np.ndarray,
    fwd_rets: np.ndarray,
    maj_preds: np.ndarray,
    fee: float = 0.004,
) -> dict[str, Any]:
    """Computes full suite of Step 3 metrics for a prediction series."""
    n_total = len(actuals)
    if n_total == 0:
        return {"n_total": 0}

    acc = float(np.mean(preds == actuals)) * 100.0
    maj_acc = float(np.mean(maj_preds == actuals)) * 100.0
    bal_acc = float(balanced_accuracy_score(actuals, preds)) * 100.0 if len(np.unique(actuals)) > 1 else acc

    bull_mask = preds == 1
    n_sig = int(bull_mask.sum())
    n_eff = round(n_sig / 5.0, 1)
    if n_sig > 0:
        bull_wins = int((actuals[bull_mask] == 1).sum())
        bull_wr = round((bull_wins / n_sig) * 100.0, 2)
        wr_lo, wr_hi = wilson_ci(bull_wins, n_sig)
        net_rets = (fwd_rets[bull_mask] - fee) * 100.0
        bull_ret = round(float(np.mean(net_rets)), 3)
        ret_lo, ret_hi = block_bootstrap_ci(net_rets, block_size=5, n_boot=500, seed=42)
    else:
        bull_wr, wr_lo, wr_hi = 0.0, 0.0, 0.0
        bull_ret, ret_lo, ret_hi = 0.0, 0.0, 0.0

    auc = None
    brier = None
    ll = None
    if probs is not None and len(np.unique(actuals)) > 1:
        clipped = np.clip(probs, 1e-6, 1.0 - 1e-6)
        auc = round(float(roc_auc_score(actuals, clipped)), 4)
        brier = round(float(brier_score_loss(actuals, clipped)), 4)
        ll = round(float(log_loss(actuals, clipped)), 4)

    return {
        "n_total": n_total,
        "n_signals": n_sig,
        "n_eff": n_eff,
        "bull_wr": bull_wr,
        "bull_wr_ci": (wr_lo, wr_hi),
        "bull_net_ret": bull_ret,
        "bull_ret_ci": (round(ret_lo, 3), round(ret_hi, 3)),
        "acc": round(acc, 2),
        "bal_acc": round(bal_acc, 2),
        "maj_acc": round(maj_acc, 2),
        "auc": auc,
        "brier": brier,
        "log_loss": ll,
    }
