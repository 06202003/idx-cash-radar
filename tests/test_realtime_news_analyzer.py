"""
Unit & Integration Tests for Real-Time News Link Sentiment + Accrual Radar Cross-Check.
Verifies SSRF safety, HTML extraction, ticker auto-detection, deterministic sentiment,
contextual isolation, and FastAPI endpoint POST /api/news/analyze-url.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.engine.llm_explainer import check_language_compliance
from src.engine.realtime_news_analyzer import (
    analyze_sentiment_deterministic,
    detect_ticker_in_article,
    extract_article_from_html,
    validate_public_url,
)
from src.web.app import app

client = TestClient(app)


def test_validate_public_url_blocks_ssrf_and_invalid_schemes() -> None:
    ok_bad_1, _ = validate_public_url("http://127.0.0.1:8000/api/health")
    ok_bad_2, _ = validate_public_url("http://localhost/admin")
    ok_bad_3, _ = validate_public_url("file:///etc/passwd")
    ok_bad_4, _ = validate_public_url("ftp://example.com/file")

    assert ok_bad_1 is False
    assert ok_bad_2 is False
    assert ok_bad_3 is False
    assert ok_bad_4 is False


def test_extract_article_from_html_handles_loading_title_and_captcha() -> None:
    sample_html = """
    <html>
      <head>
        <title>Loading...</title>
        <meta property="og:title" content="Waskita Karya Kantongi Kontrak Baru Rp5,6 Triliun" />
        <meta property="og:site_name" content="Infobanknews" />
      </head>
      <body>
        <article>
          <p>Jakarta - PT Waskita Karya (Persero) Tbk (WSKT) mencatat Nilai Kontrak Baru
          Rp5,6 triliun hingga Agustus 2026 dengan 49,2 persen proyek pemerintah pusat.</p>
          <p>Waskita tetap selektif memilih proyek, menghindari skema turnkey dan investasi,
          serta fokus pada proyek dengan pembayaran bulanan dan uang muka.</p>
        </article>
      </body>
    </html>
    """
    res = extract_article_from_html(sample_html, url="https://infobanknews.com/sample")
    assert res["blocked"] is False
    assert res["headline"] == "Waskita Karya Kantongi Kontrak Baru Rp5,6 Triliun"
    assert res["source"] == "Infobanknews"
    assert len(res["highlights"]) >= 1

    captcha_html = "<html><body><div>Attention Required! | Cloudflare</div></body></html>"
    blocked = extract_article_from_html(captcha_html, url="https://example.com/gated")
    assert blocked["blocked"] is True


def test_detect_ticker_and_sentiment_on_wskt_contract_news() -> None:
    issuers = [
        {"ticker": "WSKT", "company_name": "Waskita Karya (Persero) Tbk."},
        {"ticker": "BBRI", "company_name": "Bank Rakyat Indonesia (Persero) Tbk."},
    ]
    headline = "Waskita Karya Kantongi Kontrak Baru Rp5,6 Triliun, Ini Rincian Proyeknya"
    body = (
        "Waskita Karya mencatat Nilai Kontrak Baru (NKB) Rp5,6 triliun hingga Agustus 2026, "
        "dengan 49,2 persen berasal dari proyek pemerintah pusat. Waskita menghindari skema "
        "turnkey dan fokus pada proyek dengan pembayaran bulanan dan uang muka."
    )

    ticker = detect_ticker_in_article(f"{headline}\n{body}", issuers)
    assert ticker == "WSKT"

    # Headline-first priority: even if Waskita is mentioned in body, headline PT PP / Adhi wins
    merger_issuers = issuers + [
        {"ticker": "PTPP", "company_name": "PP (Persero) Tbk."},
        {"ticker": "ADHI", "company_name": "Adhi Karya (Persero) Tbk."},
    ]
    merger_headline = (
        "Danantara Percepat Merger BUMN Karya, PT PP dan Adhi Karya Digabung Tahun Ini"
    )
    merger_body = "Ketujuh BUMN karya termasuk Waskita Karya dan Wijaya Karya akan digabung."
    merger_ticker = detect_ticker_in_article(
        f"{merger_headline}\n{merger_body}",
        merger_issuers,
        url="https://kumparan.com/kumparanbisnis/danantara-percepat-merger-bumn-karya-pt-pp-dan-adhi-karya-digabung-tahun-ini-285mnXVZGsi",
    )
    assert merger_ticker == "PTPP"

    sent = analyze_sentiment_deterministic(headline, body)
    assert sent["sentiment"] == "POSITIF"
    assert "kontrak baru" in sent["matched_positive"]
    assert "pembayaran bulanan" in sent["matched_positive"]


def test_analyze_url_endpoint_with_raw_text_cross_checks_accrual_radar() -> None:
    payload = {
        "raw_text": (
            "Waskita Karya Kantongi Kontrak Baru Rp5,6 Triliun, Ini Rincian Proyeknya\n"
            "PT Waskita Karya (Persero) Tbk mencatat Nilai Kontrak Baru Rp5,6 triliun "
            "hingga Agustus 2026 dengan 49,2 persen berasal dari proyek pemerintah pusat. "
            "Perseroan fokus pada pembayaran bulanan dan uang muka."
        )
    }
    resp = client.post("/api/news/analyze-url", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert data["detected_ticker"] == "WSKT"
    assert data["sentiment"] == "POSITIF"
    assert data["fundamentals"] is not None
    assert data["fundamentals"]["net_income_ttm_idr"] < 0
    assert data["analysis_awam"]
    assert data["analysis_expert"]
    assert check_language_compliance(data["analysis_awam"]) is True
    assert check_language_compliance(data["analysis_expert"]) is True


def test_analyze_url_endpoint_rejects_empty_and_private_url() -> None:
    resp_empty = client.post("/api/news/analyze-url", json={})
    assert resp_empty.status_code == 400

    resp_ssrf = client.post("/api/news/analyze-url", json={"url": "http://127.0.0.1:8000/"})
    assert resp_ssrf.status_code == 422


def test_wika_whoosh_debt_news_classifies_warning_with_forward_forecast() -> None:
    payload = {
        "raw_text": (
            "WIKA Terbebani Utang Whoosh, Danantara Pastikan Tak Akan Dibiarkan\n"
            "Kerugian ini naik 45,73 persen dari rugi Rp 780,17 miliar di akhir Maret 2025. "
            "WIKA mencatat rugi sebesar Rp 483,80 miliar dari kepemilikan sahamnya di PT PSBI, "
            "pemegang saham mayoritas PT KCIC, dengan kerugian konsolidasi Rp 1,13 triliun."
        )
    }
    resp = client.post("/api/news/analyze-url", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["detected_ticker"] == "WIKA"
    assert data["sentiment"] == "PERHATIAN"
    assert "terbebani" in data["matched_warning"]
    assert data["outlook_stance"]
    assert data["forecast_awam"]
    assert data["forecast_expert"]
    assert len(data["watchpoints"]) >= 2
    assert data["ml_forecast"] is not None
    assert check_language_compliance(data["forecast_awam"]) is True
    assert check_language_compliance(data["forecast_expert"]) is True
