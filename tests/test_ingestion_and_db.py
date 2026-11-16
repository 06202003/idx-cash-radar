"""
Tests for Database Repository and Ingestion Pipeline.
Verifies persistence to SQLite3, unique constraints, and canonical fact retrieval.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from scripts.ingest_filings import ingest_directory
from src.db.repository import FinancialRepository
from src.models.canonical import CanonicalFactModel, FilingModel, IssuerModel
from tests.fixtures.synthetic_xbrl.generator import generate_mock_xbrl


def test_repository_crud() -> None:
    """Verifies SQLite3 database CRUD operations for issuers, filings, and canonical facts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        repo = FinancialRepository(db_path=db_path)

        # 1. Issuer test
        issuer = IssuerModel(
            ticker="WIKA",
            company_name="Wijaya Karya (Persero) Tbk.",
            idx_sub_industry="Konstruksi Bangunan & Rekayasa Sipil",
        )
        repo.save_issuer(issuer)
        fetched_issuer = repo.get_issuer("WIKA")
        assert fetched_issuer is not None
        assert fetched_issuer.company_name == "Wijaya Karya (Persero) Tbk."

        # 2. Filing test
        filing = FilingModel(
            filing_id="WIKA_2023_FY_FIRST",
            ticker="WIKA",
            fiscal_year=2023,
            period_code="FY",
            period_end_date="2023-12-31",
            is_audited=True,
            sanity_check_passed=True,
            source_xbrl_hash="abc123hash",
        )
        repo.save_filing(filing)
        fetched_filing = repo.get_filing("WIKA_2023_FY_FIRST")
        assert fetched_filing is not None
        assert fetched_filing.is_audited is True
        assert fetched_filing.sanity_check_passed is True

        # 3. Canonical facts test
        facts = [
            CanonicalFactModel(
                canonical_key="cash_and_equivalents",
                value_idr=Decimal("3233071377000"),
                raw_xbrl_tag="CashAndCashEquivalents",
                raw_context_ref="CurrentYearInstant",
                raw_unit_ref="IDR",
                raw_decimals="0",
                raw_lexical_value="3233071377000",
            ),
            CanonicalFactModel(
                canonical_key="revenue",
                value_idr=Decimal("22530000000000"),
                raw_xbrl_tag="SalesAndRevenue",
                raw_context_ref="CurrentYearDuration",
                raw_unit_ref="IDR",
                raw_decimals="0",
                raw_lexical_value="22530000000000",
            ),
        ]
        repo.save_canonical_facts("WIKA_2023_FY_FIRST", facts)
        fetched_facts = repo.get_canonical_facts("WIKA_2023_FY_FIRST")
        assert len(fetched_facts) == 2
        assert fetched_facts["cash_and_equivalents"].value_idr == Decimal("3233071377000")


def test_full_ingestion_pipeline() -> None:
    """Verifies end-to-end ingestion from synthetic XBRL into SQLite."""
    mock_xml = generate_mock_xbrl(ticker="ADHI")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        xbrl_path = tmp_path / "instance_ADHI.xbrl"
        xbrl_path.write_text(mock_xml, encoding="utf-8")

        db_path = tmp_path / "radar_test.db"
        res = ingest_directory(directory=tmp_path, db_path=db_path)

        assert res["total"] == 1
        assert res["success"] == 1

        repo = FinancialRepository(db_path=db_path)
        issuer = repo.get_issuer("ADHI")
        assert issuer is not None
        assert "Adhi Karya" in issuer.company_name

        facts = repo.get_canonical_facts("ADHI_2023_FY_FIRST")
        assert "cash_and_equivalents" in facts
        assert "total_assets" in facts
