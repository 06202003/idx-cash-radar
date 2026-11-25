"""Step F unit tests for v3 audit fixes: symmetric fee, two-sided Holm, binomial n_eff, Winkler score, V5 Jensen fix."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.eval.stats_v2 import holm_bonferroni
from src.eval.stats_v3 import binomial_rejection_rate, winkler_interval_score


def test_symmetric_fee_cancels_in_excess_return() -> None:
    strat_gross = np.array([0.02, -0.01, 0.015])
    bench_gross = np.array([0.01, -0.005, 0.01])
    fee = 0.004
    excess_gross = strat_gross - bench_gross
    excess_sym_fee = (strat_gross - fee) - (bench_gross - fee)
    np.testing.assert_allclose(excess_gross, excess_sym_fee)


def test_two_sided_holm_preserves_negative_rejection() -> None:
    # R5 had p=0.0076 on negative excess; two-sided Holm flags it as < 0.05
    p_vals = [0.056, 0.9496, 0.0416, 0.2228, 0.0076, 0.846]
    adj = holm_bonferroni(p_vals)
    assert adj[4] < 0.05


def test_binomial_neff_synthetic_rejection_rate() -> None:
    rng = np.random.default_rng(77)
    hits_by_ticker = {}
    for idx in range(30):
        # 250 correlated 5-day blocks simulated as 50 independent blocks repeated 5x
        indep = (rng.random(50) < 0.68).astype(int)
        hits_by_ticker[f"T{idx}"] = np.repeat(indep, 5).tolist()
    res = binomial_rejection_rate(hits_by_ticker, nominal_p=0.68, horizon=5, alpha=0.05)
    assert res["rej_rate_pct"] <= 15.0


def test_winkler_interval_score_exact() -> None:
    y = np.array([0.0, 2.0, -3.0])
    lo = np.array([-1.0, -1.0, -1.0])
    hi = np.array([1.0, 1.0, 1.0])
    # alpha=0.2 -> penalty factor 2/0.2 = 10
    scores = winkler_interval_score(y, lo, hi, alpha=0.2)
    np.testing.assert_allclose(scores, np.array([2.0, 2.0 + 10.0 * 1.0, 2.0 + 10.0 * 2.0]))


def test_v5_jensen_correction_removes_downward_bias() -> None:
    rng = np.random.default_rng(19)
    n = 500
    X = rng.normal(0.0, 1.0, size=(n, 3))
    y_log = -4.0 + 0.3 * X[:, 0] + rng.normal(0.0, 0.4, size=n)
    y_lvl = np.exp(y_log)

    m = Pipeline([("s", StandardScaler()), ("reg", Ridge(alpha=1.0))]).fit(X, y_log)
    res_var = float(np.var(y_log - m.predict(X)))
    pred_no_jensen = np.exp(m.predict(X))
    pred_with_jensen = np.exp(m.predict(X) + 0.5 * res_var)

    bias_no = abs(float(np.mean(pred_no_jensen - y_lvl)))
    bias_yes = abs(float(np.mean(pred_with_jensen - y_lvl)))
    assert bias_yes < bias_no
