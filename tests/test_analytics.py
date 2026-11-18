"""
Tests for Privacy-Preserving Analytics Endpoints & Dashboard (Fase 4).
Verifies minimum events, Top 5 most-checked tickers, prioritized metrics
(kartu_dibagikan & ticker_dicek), and strict rejection of unsupported events / PII.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.web.app import app

client = TestClient(app)


def test_analytics_event_allowlist_and_top5_dashboard() -> None:
    # Record prioritized events
    for t in ("WIKA", "WIKA", "BBRI", "ADRO"):
        r = client.post("/api/analytics/event", json={"event_name": "ticker_dicek", "ticker": t})
        assert r.status_code == 200
        assert r.json()["status"] == "recorded"

    for ev in (
        "kartu_dibagikan",
        "kartu_dibuat",
        "link_berita_ditempel",
        "mode_expert_dibuka",
        "fitur_pro_dibuka",
    ):
        r = client.post("/api/analytics/event", json={"event_name": ev, "ticker": "WIKA"})
        assert r.status_code == 200

    # Reject unknown event
    bad = client.post("/api/analytics/event", json={"event_name": "arbitrary_pii_event"})
    assert bad.status_code == 400

    # Summary includes counts and Top 5 tickers
    sum_resp = client.get("/api/analytics/summary")
    assert sum_resp.status_code == 200
    data = sum_resp.json()
    assert data["counts"]["ticker_dicek"] >= 4
    assert data["counts"]["kartu_dibagikan"] >= 1
    assert len(data["top_5_tickers"]) >= 1
    assert len(data["top_5_tickers"]) <= 5

    # HTML dashboard renders cleanly
    dash = client.get("/analytics")
    assert dash.status_code == 200
    assert "Top 5 Ticker Paling Sering Dicek" in dash.text
    assert "kartu_dibagikan" in dash.text
