"""Date-clustered block bootstrap, Diebold-Mariano test, Holm correction, and matched random baseline."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def date_clustered_bootstrap_ci(
    dates: np.ndarray | pd.Series,
    values: np.ndarray,
    block_size: int = 10,
    n_boot: int = 5000,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Aggregates values equal-weight per date, then runs moving block bootstrap over dates.
    Returns mean, 95% CI [lo, hi], and two-sided bootstrap p-value against 0.
    """
    df = pd.DataFrame({"date": dates, "val": np.asarray(values, dtype=float)})
    df = df.dropna(subset=["val"])
    if df.empty:
        return {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "p_val": 1.0, "n_dates": 0}

    daily = df.groupby("date", sort=True)["val"].mean().to_numpy(dtype=float)
    n_d = len(daily)
    mean_v = float(np.mean(daily))
    if n_d < block_size:
        return {"mean": round(mean_v, 4), "ci_lo": round(mean_v, 4), "ci_hi": round(mean_v, 4), "p_val": 1.0, "n_dates": n_d}

    rng = np.random.default_rng(seed)
    n_blocks = max(1, int(math.ceil(n_d / block_size)))
    starts = rng.integers(0, n_d - block_size + 1, size=(n_boot, n_blocks))
    offsets = np.arange(block_size)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_boot, -1)[:, :n_d]
    boot_means = daily[idx].mean(axis=1)
    lo, hi = np.percentile(boot_means, [2.5, 97.5])

    # Two-sided p-value: 2 * min(P(boot <= 0), P(boot >= 0))
    p_le = float(np.mean(boot_means <= 0.0))
    p_ge = float(np.mean(boot_means >= 0.0))
    p_val = min(1.0, 2.0 * min(p_le, p_ge))
    return {
        "mean": round(mean_v, 4),
        "ci_lo": round(float(lo), 4),
        "ci_hi": round(float(hi), 4),
        "p_val": round(p_val, 4),
        "n_dates": n_d,
    }


def independent_bootstrap_ci(
    values: np.ndarray,
    block_size: int = 5,
    n_boot: int = 2000,
    seed: int = 42,
) -> tuple[float, float]:
    """Old naive cross-sectional-independent block bootstrap CI (for v1 vs v2 comparison)."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n == 0:
        return 0.0, 0.0
    if n < block_size:
        m = float(np.mean(arr))
        return round(m, 4), round(m, 4)
    rng = np.random.default_rng(seed)
    n_blocks = max(1, int(math.ceil(n / block_size)))
    starts = rng.integers(0, n - block_size + 1, size=(n_boot, n_blocks))
    offsets = np.arange(block_size)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_boot, -1)[:, :n]
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Computes Holm-Bonferroni adjusted p-values preserving original order."""
    m = len(p_values)
    if m == 0:
        return []
    order = np.argsort(p_values)
    adj = np.empty(m, dtype=float)
    running_max = 0.0
    for rank, idx in enumerate(order):
        val = float(p_values[idx]) * (m - rank)
        running_max = max(running_max, val)
        adj[idx] = min(1.0, running_max)
    return [round(float(x), 4) for x in adj]


def random_baseline_matched(
    dates: np.ndarray,
    excess_rets: np.ndarray,
    n_signals: int,
    n_seeds: int = 500,
    seed: int = 42,
) -> dict[str, float]:
    """Randomly selects exact n_signals observations over 500 seeds and reports percentiles."""
    n = len(excess_rets)
    if n == 0 or n_signals <= 0:
        return {"p2_5": 0.0, "p50": 0.0, "p97_5": 0.0}
    k = min(n_signals, n)
    rng = np.random.default_rng(seed)
    means = np.empty(n_seeds, dtype=float)
    for s in range(n_seeds):
        idx = rng.choice(n, size=k, replace=False)
        means[s] = float(np.mean(excess_rets[idx]))
    p2_5, p50, p97_5 = np.percentile(means, [2.5, 50.0, 97.5])
    return {"p2_5": round(float(p2_5), 4), "p50": round(float(p50), 4), "p97_5": round(float(p97_5), 4)}
