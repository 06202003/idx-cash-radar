"""
Unit tests for Machine Learning & Econometric Suite (src/engine/ml_models.py).
"""

from src.db.repository import FinancialRepository
from src.engine.ml_models import FinancialMLSuite


def test_distress_probability_high_distress():
    ml = FinancialMLSuite()
    # High Sloan accrual, negative CFO, low cash coverage (< 0.20x)
    mock_distress = {
        "cash_coverage_ratio": 0.10,
        "debt_free_short_term": False,
        "sloan_ratio_ttm": 0.25,
        "cfo_ttm_idr": -2_000_000_000_000,
        "revenue_ttm_idr": 10_000_000_000_000,
        "gross_contract_exposure_ratio": 0.45,
    }
    result = ml.compute_distress_probability(mock_distress)

    assert result["distress_probability"] > 0.50
    assert result["credit_classification"] == "HIGH_DISTRESS_RISK"
    assert result["synthetic_rating"] == "C"
    assert result["feature_contributions"]["sloan_impact"] > 0


def test_distress_probability_solvent_debt_free():
    ml = FinancialMLSuite()
    # Debt-free company with strong positive CFO
    mock_solvent = {
        "cash_coverage_ratio": None,
        "debt_free_short_term": True,
        "sloan_ratio_ttm": -0.05,
        "cfo_ttm_idr": 5_000_000_000_000,
        "revenue_ttm_idr": 20_000_000_000_000,
        "gross_contract_exposure_ratio": 0.10,
    }
    result = ml.compute_distress_probability(mock_solvent)

    assert result["distress_probability"] < 0.10
    assert result["credit_classification"] in ["PRIME_LIQUIDITY", "STABLE_SOLVENCY"]
    assert result["synthetic_rating"] in ["AAA", "BBB"]


def test_forecast_cash_flow_trajectory():
    repo = FinancialRepository()
    ml = FinancialMLSuite(repo=repo)

    res = ml.forecast_cash_flow_trajectory("WIKA", forecast_years=2)
    assert res["status"] == "success"
    assert res["ticker"] == "WIKA"
    assert len(res["projections"]) == 2
    assert res["projections"][0]["forecast_year"] == 2026
    assert "projected_cfo_idr" in res["projections"][0]
    assert "projected_distress_probability_pct" in res["projections"][0]


def test_feature_importance_matrix():
    ml = FinancialMLSuite()
    features = ml.get_feature_importance_matrix()

    assert len(features) == 4
    names = [f["feature"] for f in features]
    assert any("Sloan Accrual" in n for n in names)
    assert any("Cash Coverage" in n for n in names)

    # Sloan accrual should have positive risk weight
    sloan_feat = next(f for f in features if "Sloan" in f["feature"])
    assert sloan_feat["weight_coefficient"] > 0

    # Cash coverage should have negative risk weight
    cov_feat = next(f for f in features if "Coverage" in f["feature"])
    assert cov_feat["weight_coefficient"] < 0
