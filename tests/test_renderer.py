"""
Unit tests for DiagnosticCardRenderer.
Strictly verifies Section 8 of AGENTS.md.
"""

from decimal import Decimal
from pathlib import Path

from src.db.repository import FinancialRepository
from src.models.metrics import (
    CashCoverageMetrics,
    CohortRankResult,
    ComputedFilingMetrics,
    ContractExposureMetrics,
    SafeguardEvaluation,
    SloanAccrualMetrics,
)
from src.renderer.card_renderer import DiagnosticCardRenderer


def test_render_construction_card_mock_data():
    renderer = DiagnosticCardRenderer()

    metrics = ComputedFilingMetrics(
        filing_id="WIKA_2023_FY_FIRST",
        ticker="WIKA",
        period_end_date="2023-12-31",
        is_audit_derived_q4=True,
        contract_exposure=ContractExposureMetrics(
            gross_exposure_idr=Decimal("15000000000000"),
            net_exposure_idr=Decimal("12000000000000"),
            revenue_ttm_idr=Decimal("21400000000000"),
            gross_contract_exposure_ratio=Decimal("0.70"),
            net_contract_exposure_ratio=Decimal("0.56"),
            gross_divergence_yoy_bps=Decimal("520"),
        ),
        sloan_accrual=SloanAccrualMetrics(
            sloan_ratio_ttm=Decimal("0.085"),
            net_income_ttm_idr=Decimal("-7120000000000"),
            cfo_ttm_idr=Decimal("-2900000000000"),
            average_assets_idr=Decimal("65000000000000"),
        ),
        cash_coverage=CashCoverageMetrics(
            cash_idr=Decimal("1300000000000"),
            st_debt_idr=Decimal("8900000000000"),
            cash_coverage_ratio=Decimal("0.15"),
        ),
        safeguards=SafeguardEvaluation(
            flag_accrual_divergence=False,
            flag_acute_liquidity=True,
            status_summary="⚠️ TEKANAN LIKUIDITAS AKUT: Kas menutup < 20% kewajiban jangka pendek",
        ),
        cohort_ranks={
            "contract_exposure": CohortRankResult(
                metric_name="gross_contract_exposure_ratio",
                issuer_value=Decimal("0.70"),
                peer_count=3,
                small_n_guard=True,
                industry_median=Decimal("0.65"),
            ),
            "sloan_accrual": CohortRankResult(
                metric_name="sloan_ratio_ttm",
                issuer_value=Decimal("0.085"),
                peer_count=3,
                small_n_guard=True,
                industry_median=Decimal("0.040"),
            ),
            "cash_coverage": CohortRankResult(
                metric_name="cash_coverage_ratio",
                issuer_value=Decimal("0.15"),
                peer_count=3,
                small_n_guard=True,
                industry_median=Decimal("0.45"),
            ),
        },
    )

    rendered = renderer.render_construction_card(
        metrics=metrics,
        company_name="Wijaya Karya (Persero) Tbk",
    )

    # Assertions
    assert "DIAGNOSTIK KAS & AKRUAL EMITEN" in rendered
    assert "Wijaya Karya (Persero) Tbk (WIKA)" in rendered
    assert "TEKANAN LIKUIDITAS AKUT" in rendered
    assert "Intensitas Eksposur Kontrak (PSAK 72)" in rendered
    assert "70,0%" in rendered
    assert "56,0%" in rendered
    assert "+520 bps YoY" in rendered
    assert "vs. Median: 0,65" in rendered
    assert "Sloan Accrual TTM" in rendered
    assert "0,085" in rendered
    assert "Solvabilitas Utang Jangka Pendek" in rendered
    assert "0,15x" in rendered
    assert "AUDIT TRAIL DATA BEI (instance.xbrl)" in rendered
    assert "TradeReceivablesThirdParties" in rendered


def test_render_empty_state_card():
    renderer = DiagnosticCardRenderer()
    rendered = renderer.render_empty_state_card("BBCA")

    assert "INFORMASI CAKUPAN EMITEN" in rendered
    assert "BBCA" in rendered
    assert "Di Luar Cakupan Sektor Konstruksi" in rendered
    assert "Konstruksi Bangunan & Rekayasa Sipil" in rendered
    # Must NOT contain PSAK 72 contract metrics
    assert "Intensitas Eksposur Kontrak (PSAK 72)" not in rendered
    assert "Sloan Accrual TTM" not in rendered


def test_render_with_real_database_if_available():
    db_path = Path("idx_cash_radar.db")
    if not db_path.exists():
        return

    repo = FinancialRepository(db_path=db_path)
    renderer = DiagnosticCardRenderer()

    issuer = repo.get_issuer("WIKA")
    if not issuer:
        return

    # Check that repo facts are loaded into audit trail
    facts = repo.get_canonical_facts("WIKA_2023_FY_FIRST")
    if facts:
        from scripts.run_case_evaluation import evaluate_filing
        metrics = evaluate_filing("WIKA_2023_FY_FIRST", repo)
        assert metrics is not None

        rendered = renderer.render_construction_card(
            metrics=metrics,
            company_name=issuer.company_name,
            repo=repo,
        )
        assert "WIKA" in rendered
        assert "AUDIT TRAIL DATA BEI (instance.xbrl)" in rendered
