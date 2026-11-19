"""Tests for FastAPI serverless webhook and cron endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.web_webhook import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mode"] == "serverless-webhook"
