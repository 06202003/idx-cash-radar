"""
Tests for Self-Growing Knowledge Database Ingestor, API endpoints,
and dynamic RAG Chatbot recognition for newly added BEI tickers.
"""

from __future__ import annotations

import base64
import io
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.engine.knowledge_ingestor as ki
import src.web.app as web_app
from src.db.repository import FinancialRepository
from src.engine.news_radar import CURATED_DISCLOSURES
from src.engine.rag_chat import RAGFinancialChatbot
from tests.fixtures.synthetic_xbrl.generator import generate_mock_xbrl


@pytest.fixture()
def isolated_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FinancialRepository:
    """Provides a clean temporary SQLite repository without touching production DB."""
    db_path = tmp_path / "test_knowledge.db"
    repo = FinancialRepository(db_path=db_path)

    monkeypatch.setattr(ki, "CUSTOM_DISCLOSURES_PATH", tmp_path / "custom_disclosures.json")
    monkeypatch.setattr(ki, "USER_XBRL_DIR", tmp_path / "user_xbrl")
    return repo


def test_validate_ticker_rules() -> None:
    """Accepts 4-letter BEI ticker codes and rejects invalid lengths/characters."""
    assert ki.validate_ticker(" asii ") == "ASII"
    with pytest.raises(ValueError):
        ki.validate_ticker("AS")
    with pytest.raises(ValueError):
        ki.validate_ticker("1234")
    with pytest.raises(ValueError):
        ki.validate_ticker("ASII1")


def test_ingest_structured_issuer_deterministic_flags(
    isolated_repo: FinancialRepository,
) -> None:
    """Verifies Decimal computations for acute liquidity, accrual divergence, and debt-free."""
    # Case 1: Profitable on paper, negative CFO, high accrual, tight cash coverage
    res_risk = ki.ingest_structured_issuer(
        repo=isolated_repo,
        ticker="ZZZX",
        company_name="PT Uji Risiko Tbk.",
        idx_sub_industry="Sektor Uji",
        fiscal_year=2025,
        cash_idr=Decimal("100000000000"),          # 100B
        st_debt_bank_idr=Decimal("900000000000"),  # 900B
        st_debt_bonds_idr=Decimal("100000000000"), # 100B -> Total ST Debt 1000B -> Cov 0.10x
        cfo_ttm_idr=Decimal("-300000000000"),      # -300B
        net_income_ttm_idr=Decimal("500000000000"),# +500B -> NI - CFO = 800B
        revenue_ttm_idr=Decimal("2000000000000"),
        total_assets_idr=Decimal("5000000000000"), # 5T -> Sloan = 800B / 5T = 16.0%
        total_liabilities_idr=Decimal("3000000000000"),
        receivables_idr=Decimal("400000000000"),
        source_note="Kontrak baru proyek percontohan Rp 1,2 Triliun",
    )
    assert res_risk["status"] == "success"
    assert res_risk["ticker"] == "ZZZX"
    assert res_risk["cash_coverage"] == "0.10x"
    assert res_risk["sloan_ratio_pct"] == 16.0
    assert res_risk["safeguard_status"] == "WASPADA: DIVERGENSI AKRUAL & TEKANAN LIKUIDITAS"
    with isolated_repo.get_connection() as conn:
        flags_row = conn.execute(
            "SELECT flag_acute_liquidity, flag_accrual_divergence "
            "FROM computed_metrics WHERE ticker = ?",
            ("ZZZX",),
        ).fetchone()
    assert flags_row["flag_acute_liquidity"] == 1
    assert flags_row["flag_accrual_divergence"] == 1

    # Custom disclosure persisted as secondary context
    assert "ZZZX" in CURATED_DISCLOSURES
    CURATED_DISCLOSURES.pop("ZZZX", None)

    # Case 2: Zero short-term interest-bearing debt -> Debt-Free guard
    res_safe = ki.ingest_structured_issuer(
        repo=isolated_repo,
        ticker="ZZZY",
        company_name="PT Uji Bebas Utang Tbk.",
        idx_sub_industry="Sektor Uji",
        fiscal_year=2025,
        cash_idr=Decimal("500000000000"),
        st_debt_bank_idr=Decimal("0"),
        st_debt_bonds_idr=Decimal("0"),
        cfo_ttm_idr=Decimal("400000000000"),
        net_income_ttm_idr=Decimal("350000000000"),
        revenue_ttm_idr=Decimal("1500000000000"),
        total_assets_idr=Decimal("3000000000000"),
    )
    assert res_safe["cash_coverage"] == "Bebas Utang"
    assert res_safe["safeguard_status"] == "NORMAL / AMAN"


def test_ingest_xbrl_xml_and_zip(isolated_repo: FinancialRepository) -> None:
    """Parses synthetic BEI XBRL XML and ZIP archives into SQLite deterministically."""
    mock_xml = generate_mock_xbrl(
        ticker="XBRZ",
        instant_date="2024-12-31",
        start_date="2024-01-01",
        end_date="2024-12-31",
        assets=200_000_000_000,
        cash_bs=12_000_000_000,
        cash_cf=12_000_000_000,
        revenue=120_000_000_000,
        profit_loss=10_000_000_000,
        cfo=-5_000_000_000,
    )

    res_xml = ki.ingest_xbrl_file_bytes(
        repo=isolated_repo,
        ticker="XBRZ",
        company_name="PT XBRL XML Tbk.",
        idx_sub_industry="Infrastruktur",
        fiscal_year=2024,
        filename="xbrz_2024.xml",
        file_bytes=mock_xml.encode("utf-8"),
    )
    assert res_xml["status"] == "success"
    assert res_xml["ticker"] == "XBRZ"
    assert len(res_xml["xbrl_hash"]) == 64

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("instance.xml", mock_xml.encode("utf-8"))

    res_zip = ki.ingest_xbrl_file_bytes(
        repo=isolated_repo,
        ticker="XBRW",
        company_name="PT XBRL ZIP Tbk.",
        idx_sub_industry="Infrastruktur",
        fiscal_year=2024,
        filename="xbrw_2024.zip",
        file_bytes=buf.getvalue(),
    )
    assert res_zip["status"] == "success"
    assert res_zip["ticker"] == "XBRW"
    CURATED_DISCLOSURES.pop("XBRZ", None)
    CURATED_DISCLOSURES.pop("XBRW", None)


def test_rag_chatbot_recognizes_newly_added_ticker(isolated_repo: FinancialRepository) -> None:
    """Verifies RAGFinancialChatbot dynamically picks up new tickers and non-2025 filings."""
    ki.ingest_structured_issuer(
        repo=isolated_repo,
        ticker="DYNM",
        company_name="PT Dinamis Nusantara Tbk.",
        idx_sub_industry="Teknologi",
        fiscal_year=2024,
        cash_idr=Decimal("900000000000"),
        st_debt_bank_idr=Decimal("300000000000"),
        st_debt_bonds_idr=Decimal("0"),
        cfo_ttm_idr=Decimal("450000000000"),
        net_income_ttm_idr=Decimal("400000000000"),
        revenue_ttm_idr=Decimal("2100000000000"),
        total_assets_idr=Decimal("3500000000000"),
    )
    bot = RAGFinancialChatbot(repository=isolated_repo)
    assert "DYNM" in bot.get_all_known_tickers()
    assert bot.extract_tickers_from_query("Bagaimana posisi kas DYNM?") == ["DYNM"]

    ctx = bot.retrieve_context_for_query("Analisis fundamental DYNM")
    answer = bot.generate_deterministic_fallback_answer("Analisis fundamental DYNM", ctx)
    assert "DYNM" in answer
    assert "PT Dinamis Nusantara Tbk." in answer
    assert "FY 2024" in answer


def test_api_ingest_and_query_end_to_end(
    isolated_repo: FinancialRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests POST /api/issuers/ingest and /api/issuers/ingest-xbrl end-to-end cleanly."""
    monkeypatch.setattr(web_app, "repo", isolated_repo)
    monkeypatch.setattr(web_app.rag_chatbot, "repo", isolated_repo)
    monkeypatch.setattr(web_app.rag_chatbot, "_client", None)
    monkeypatch.setattr(web_app.ml_suite, "repo", isolated_repo)

    client = TestClient(web_app.app)

    # 1. Ingest via structured JSON form endpoint (values in Miliar IDR -> unit_multiplier=1e9)
    resp = client.post(
        "/api/issuers/ingest",
        json={
            "ticker": "NEWS",
            "company_name": "PT Saham Baru Mandiri Tbk.",
            "idx_sub_industry": "Konsumer & Ritel",
            "fiscal_year": 2025,
            "cash": 1200.0,
            "st_debt_bank": 400.0,
            "st_debt_bonds": 0.0,
            "cfo_ttm": 850.0,
            "net_income_ttm": 720.0,
            "revenue_ttm": 5400.0,
            "total_assets": 9000.0,
            "total_liabilities": 3500.0,
            "receivables": 600.0,
            "unit_multiplier": 1000000000.0,
            "source_note": "Ekspansi gerai ritel tahun berjalan",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "NEWS"
    assert body["cash_coverage"] == "3.00x"
    assert body["safeguard_status"] == "NORMAL / AMAN"

    # 2. Verify immediately searchable in /api/screener, /api/radar, and /api/chat
    screener = client.get("/api/screener").json()
    assert any(row["ticker"] == "NEWS" for row in screener)

    radar = client.get("/api/radar").json()
    assert any(row["ticker"] == "NEWS" for row in radar)

    chat_res = client.post("/api/chat", json={"message": "Cek kas NEWS"}).json()
    assert "NEWS" in chat_res["response"]

    # 3. Ingest via base64 XBRL endpoint
    mock_xml = generate_mock_xbrl(ticker="XBAPI", instant_date="2024-12-31")
    b64_payload = base64.b64encode(mock_xml.encode("utf-8")).decode("ascii")
    xbrl_resp = client.post(
        "/api/issuers/ingest-xbrl",
        json={
            "ticker": "XBAP",
            "company_name": "PT XBRL API Tbk.",
            "idx_sub_industry": "Energi & Tambang",
            "fiscal_year": 2024,
            "filename": "xbap_2024.xml",
            "content_base64": b64_payload,
        },
    )
    assert xbrl_resp.status_code == 200
    assert xbrl_resp.json()["ticker"] == "XBAP"
    CURATED_DISCLOSURES.pop("NEWS", None)
    CURATED_DISCLOSURES.pop("XBAP", None)
