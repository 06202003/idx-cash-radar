"""
Unit tests for FastAPI Web Application & Financial Radar REST API.
Phase 2 Implementation verifying PRD Section 10.2.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.web.app import app

client = TestClient(app)


def test_health_endpoint() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "v2.0" in data["system"]


def test_issuers_endpoint() -> None:
    resp = client.get("/api/issuers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 8
    tickers = [item["ticker"] for item in data]
    assert "WIKA" in tickers
    assert "TOTL" in tickers


def test_leaderboard_endpoint() -> None:
    resp = client.get("/api/leaderboard?fiscal_year=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 8
    assert "rank" in data[0]
    assert data[0]["rank"] == 1


def test_radar_matrix_endpoint() -> None:
    resp = client.get("/api/radar?fiscal_year=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 8
    assert "x_cash_coverage" in data[0]
    assert "y_sloan_accrual" in data[0]
    assert "category" in data[0]
    assert "color" in data[0]


def test_issuer_metrics_endpoint() -> None:
    resp = client.get("/api/metrics/WIKA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "WIKA"
    assert len(data["history"]) >= 1

    # Invalid ticker 404
    resp_invalid = client.get("/api/metrics/XYZ99")
    assert resp_invalid.status_code == 404


def test_calk_api_endpoint() -> None:
    resp = client.get("/api/calk/WIKA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "WIKA"
    assert data["is_grounding_verified"] is True
    assert len(data["audit_trail"]) == 5


def test_dashboard_html_endpoint() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "IDX Cash & Accrual" in resp.text
    assert "radarScatterChart" in resp.text


def test_regression_analytics_endpoint() -> None:
    resp = client.get("/api/analytics/regression?fiscal_year=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "parameters" in data
    assert "slope" in data["parameters"]
    assert "r_squared" in data["parameters"]
    assert len(data["trendline"]) > 0

    # With predictive inference
    resp_pred = client.get("/api/analytics/regression?fiscal_year=2025&predict_x=2.0")
    assert resp_pred.status_code == 200
    pred_data = resp_pred.json()
    assert pred_data["forecast"] is not None
    assert pred_data["forecast"]["input_cash_coverage"] == 2.0
    assert "predicted_sloan_accrual" in pred_data["forecast"]


def test_ml_distress_rankings_endpoint() -> None:
    resp = client.get("/api/ml/distress-rankings?fiscal_year=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 8
    assert "distress_probability" in data[0]
    assert "credit_classification" in data[0]
    assert "synthetic_rating" in data[0]


def test_ml_forecast_endpoint() -> None:
    resp = client.get("/api/ml/forecast/WIKA?years=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["ticker"] == "WIKA"
    assert len(data["projections"]) == 2


def test_ml_feature_importance_endpoint() -> None:
    resp = client.get("/api/ml/feature-importance")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    assert any("Sloan" in item["feature"] for item in data)


def test_chat_endpoint() -> None:
    resp = client.post("/api/chat", json={"message": "Bagaimana kondisi kas WIKA sekarang?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["response"]) > 0
    assert "kas" in data["response"].lower()

    # Empty query 400
    resp_empty = client.post("/api/chat", json={"message": "   "})
    assert resp_empty.status_code == 400


def test_screener_endpoint() -> None:
    resp = client.get("/api/screener?fiscal_year=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 8
    first = data[0]
    assert "ticker" in first
    assert "cash_idr" in first
    assert "st_debt_idr" in first
    assert "cash_coverage_display" in first
    assert "status_label" in first
