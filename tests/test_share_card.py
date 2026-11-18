"""
Tests for Shareable Deterministic Fact Cards (Fase 3).
Verifies PNG generation (1:1 & 9:16), retail-language compliance,
presence of report date, XBRL source, disclaimer, and absence of ML/prediction claims.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from src.engine.llm_explainer import check_language_compliance
from src.web.app import app

client = TestClient(app)


def test_share_card_json_and_compliance() -> None:
    for ticker in ("WIKA", "BBRI", "ADRO", "WSKT", "TOWR"):
        resp = client.get(f"/api/card/{ticker}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["ticker"] == ticker
        assert data["period_end_date"]
        assert "XBRL" in data["xbrl_source"]
        assert "Bukan rekomendasi investasi" in data["disclaimer"]
        assert len(data["metrics"]) == 3

        full_text = " ".join([
            data["ticker"],
            data["company_name"],
            data["period_end_date"],
            data["xbrl_source"],
            data["disclaimer"],
            *[f"{m['label']} {m['value']}" for m in data["metrics"]],
        ])
        assert check_language_compliance(full_text) is True
        # Ensure zero ML/prediction claims on share card
        low = full_text.lower()
        assert "auc" not in low
        assert "p(distress)" not in low
        assert "prediksi harga" not in low


def test_share_card_png_1x1_and_9x16() -> None:
    r1 = client.get("/api/card/WIKA.png?ratio=1:1")
    assert r1.status_code == 200
    assert r1.headers["content-type"] == "image/png"
    img1 = Image.open(io.BytesIO(r1.content))
    assert img1.size == (1080, 1080)

    r2 = client.get("/api/card/BBRI.png?ratio=9:16")
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "image/png"
    img2 = Image.open(io.BytesIO(r2.content))
    assert img2.size == (1080, 1920)
