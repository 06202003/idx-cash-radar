"""
Tests for IDX Cash Radar's self-trained proprietary Solvency & Indonesian News NLP models.
"""

from __future__ import annotations

from src.engine.ml_models import FinancialMLSuite
from src.engine.realtime_news_analyzer import predict_news_sentiment_nb


def test_solvency_model_loads_trained_artifact_and_outputs_money_metrics() -> None:
    suite = FinancialMLSuite()
    assert suite.trained_artifact is not None
    assert suite.trained_artifact["model_name"] == "idx_solvency_l2_logit_v1"
    assert suite.trained_artifact["cv_roc_auc"] >= 0.90

    # Distressed profile (e.g. thin coverage 0.15x + negative CFO)
    distress = suite.compute_distress_probability(
        {
            "cash_coverage_ratio": 0.15,
            "debt_free_short_term": False,
            "sloan_ratio_ttm": -0.07,
            "cfo_ttm_idr": -2_931_000_000_000,
            "net_income_ttm_idr": -7_825_000_000_000,
            "revenue_ttm_idr": 20_000_000_000_000,
            "cash_idr": 1_500_000_000_000,
            "st_debt_idr": 10_000_000_000_000,
        }
    )
    assert distress["distress_probability_pct"] > 50.0
    assert distress["credit_classification"] == "HIGH_DISTRESS_RISK"
    assert distress["money_metrics"]["cash_surplus_deficit_idr"] == -8_500_000_000_000
    assert distress["money_metrics"]["cash_needed_for_1x_idr"] == 8_500_000_000_000
    assert distress["money_metrics"]["cash_runway_months"] is not None
    assert distress["model_telemetry"]["model_name"] == "idx_solvency_l2_logit_v1"

    # Healthy debt-free profile
    healthy = suite.compute_distress_probability(
        {
            "cash_coverage_ratio": None,
            "debt_free_short_term": True,
            "sloan_ratio_ttm": -0.005,
            "cfo_ttm_idr": 435_000_000_000,
            "net_income_ttm_idr": 415_000_000_000,
            "revenue_ttm_idr": 3_000_000_000_000,
            "cash_idr": 1_200_000_000_000,
            "st_debt_idr": 0,
        }
    )
    assert healthy["distress_probability_pct"] < 10.0
    assert healthy["synthetic_rating"] == "AAA"
    assert healthy["money_metrics"]["cash_surplus_deficit_idr"] == 1_200_000_000_000
    assert healthy["money_metrics"]["cash_runway_months"] is None


def test_indonesian_news_nb_classifier_outputs_bounded_probabilities() -> None:
    caution = predict_news_sentiment_nb(
        "Suspensi perdagangan saham akibat penundaan pembayaran kupon sukuk dan PKPU"
    )
    assert caution["label"] == "PERHATIAN"
    assert caution["confidence_pct"] > 50.0
    total = sum(caution["class_probs_pct"].values())
    assert 99.0 <= total <= 101.0

    pos = predict_news_sentiment_nb(
        "Pembagian dividen tunai interim didukung arus kas operasi menguat dan rekor laba"
    )
    assert pos["label"] == "POSITIF"
    assert pos["confidence_pct"] > 50.0


def test_neural_mlp_capital_stress_simulator() -> None:
    suite = FinancialMLSuite()
    assert suite.mlp_artifact is not None
    assert suite.mlp_artifact["architecture"] == [5, 16, 8, 1]

    res = suite.run_neural_capital_stress(
        {
            "cash_coverage_ratio": 0.23,
            "debt_free_short_term": False,
            "sloan_ratio_ttm": -0.055,
            "cfo_ttm_idr": -559_700_000_000,
            "revenue_ttm_idr": 10_000_000_000_000,
            "cash_idr": 1_000_000_000_000,
            "st_debt_idr": 4_347_000_000_000,
        },
        capital_idr=10_000_000,
        cash_shock_pct=20.0,
        debt_shock_pct=30.0,
    )
    assert res["capital_idr"] == 10_000_000
    assert res["stressed_risk_pct"] >= res["base_risk_pct"]
    assert res["stressed_capital_at_risk_idr"] + res["stressed_buffered_capital_idr"] == 10_000_000
    assert res["model_telemetry"]["model_name"] == "idx_solvency_mlp_5_16_8_1_v1"
