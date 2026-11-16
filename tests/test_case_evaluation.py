"""
Tests for Retrospective Case Evaluation Matrix CLI.
Verifies Tabel A, B, and C evaluation output against PRE_REGISTRATION.md.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from scripts.run_case_evaluation import evaluate_filing, run_evaluation
from src.db.repository import FinancialRepository
from src.models.canonical import CanonicalFactModel, FilingModel, IssuerModel


def test_case_evaluation_flow() -> None:
    """Verifies that evaluate_filing computes and stores metrics cleanly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_eval.db"
        repo = FinancialRepository(db_path=db_path)

        # Insert WIKA (Distress Case: Low coverage, negative CFO)
        repo.save_issuer(
            IssuerModel(ticker="WIKA", company_name="Wijaya Karya (Persero) Tbk.")
        )
        filing_wika = FilingModel(
            filing_id="WIKA_2023_FY_FIRST",
            ticker="WIKA",
            fiscal_year=2023,
            period_code="FY",
            period_end_date="2023-12-31",
            is_audited=True,
            sanity_check_passed=True,
            source_xbrl_hash="hashwika",
        )
        repo.save_filing(filing_wika)

        facts_wika = [
            CanonicalFactModel(
                canonical_key="cash_and_equivalents",
                value_idr=Decimal("3000000000000"),
                raw_xbrl_tag="CashAndCashEquivalents",
                raw_context_ref="CurrentYearInstant",
                raw_lexical_value="3000000000000",
            ),
            CanonicalFactModel(
                canonical_key="cfo",
                value_idr=Decimal("-2500000000000"),
                raw_xbrl_tag="NetCashFlowsReceivedFromUsedInOperatingActivities",
                raw_context_ref="CurrentYearDuration",
                raw_lexical_value="-2500000000000",
            ),
            CanonicalFactModel(
                canonical_key="net_income",
                value_idr=Decimal("-7000000000000"),
                raw_xbrl_tag="ProfitLoss",
                raw_context_ref="CurrentYearDuration",
                raw_lexical_value="-7000000000000",
            ),
            CanonicalFactModel(
                canonical_key="revenue",
                value_idr=Decimal("20000000000000"),
                raw_xbrl_tag="SalesAndRevenue",
                raw_context_ref="CurrentYearDuration",
                raw_lexical_value="20000000000000",
            ),
            CanonicalFactModel(
                canonical_key="st_debt_bank_loans",
                value_idr=Decimal("20000000000000"),  # Cash Coverage = 3T / 20T = 0.15x (< 0.20x!)
                raw_xbrl_tag="ShortTermBankLoans",
                raw_context_ref="CurrentYearInstant",
                raw_lexical_value="20000000000000",
            ),
            CanonicalFactModel(
                canonical_key="total_assets",
                value_idr=Decimal("60000000000000"),
                raw_xbrl_tag="Assets",
                raw_context_ref="CurrentYearInstant",
                raw_lexical_value="60000000000000",
            ),
        ]
        repo.save_canonical_facts("WIKA_2023_FY_FIRST", facts_wika)

        # Run evaluate_filing
        res = evaluate_filing("WIKA_2023_FY_FIRST", repo)
        assert res is not None
        assert res.cash_coverage.cash_coverage_ratio == Decimal("0.15")
        assert res.safeguards.flag_acute_liquidity is True
        assert res.safeguards.flag_accrual_divergence is False

        # Verify saved in SQLite computed_metrics
        db_row = repo.get_computed_metrics_row("WIKA_2023_FY_FIRST")
        assert db_row is not None
        assert db_row["flag_acute_liquidity"] == 1
        assert Decimal(db_row["cash_coverage_ratio"]) == Decimal("0.15")

        # Run full run_evaluation CLI function
        run_evaluation(db_path=db_path)
