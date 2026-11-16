"""
Tests for Mathematical Calculator and Zero-Denominator Guards.
Strictly verifies Section 5 of AGENTS.md.
"""

from __future__ import annotations

from decimal import Decimal

from src.engine.calculator import (
    calculate_cash_coverage,
    calculate_contract_exposure,
    calculate_sloan_accrual,
)


def test_contract_exposure_normal_and_divergence() -> None:
    """Verifies Gross & Net Contract Exposure Ratios and YoY Divergence in bps."""
    res = calculate_contract_exposure(
        trade_receivables_3rd=Decimal("300"),
        trade_receivables_related=Decimal("100"),
        contract_assets_current=Decimal("200"),
        contract_assets_non_current=Decimal("50"),
        contract_liabilities_current=Decimal("150"),
        contract_liabilities_non_current=Decimal("50"),
        revenue_ttm=Decimal("1000"),
        revenue_ttm_prev_year=Decimal("900"),
        gross_ratio_prev_year=Decimal("0.60"),
    )
    # Gross Exposure = 300 + 100 + 200 + 50 = 650
    # Net Exposure = 650 - (150 + 50) = 450
    # Gross Ratio = 650 / 1000 = 0.65 (65%)
    # Net Ratio = 450 / 1000 = 0.45 (45%)
    # Divergence bps = (0.65 - 0.60) * 10000 = 500 bps (+5.0 percentage points)
    assert res.gross_exposure_idr == Decimal("650")
    assert res.net_exposure_idr == Decimal("450")
    assert res.gross_contract_exposure_ratio == Decimal("0.65")
    assert res.net_contract_exposure_ratio == Decimal("0.45")
    assert res.gross_divergence_yoy_bps == Decimal("500")
    assert res.revenue_contraction_guard is False


def test_contract_exposure_revenue_contraction_guards() -> None:
    """Verifies that Revenue <= 0 or Revenue drop > 50% YoY activates the guard."""
    # Case 1: Revenue <= 0
    res_zero = calculate_contract_exposure(
        trade_receivables_3rd=Decimal("300"),
        trade_receivables_related=Decimal("100"),
        contract_assets_current=Decimal("200"),
        contract_assets_non_current=Decimal("0"),
        contract_liabilities_current=Decimal("100"),
        contract_liabilities_non_current=Decimal("0"),
        revenue_ttm=Decimal("0"),
    )
    assert res_zero.revenue_contraction_guard is True
    assert res_zero.gross_contract_exposure_ratio is None

    # Case 2: Revenue collapsed > 50% YoY (from 1000 to 400 = -60%)
    res_drop = calculate_contract_exposure(
        trade_receivables_3rd=Decimal("300"),
        trade_receivables_related=Decimal("100"),
        contract_assets_current=Decimal("200"),
        contract_assets_non_current=Decimal("0"),
        contract_liabilities_current=Decimal("100"),
        contract_liabilities_non_current=Decimal("0"),
        revenue_ttm=Decimal("400"),
        revenue_ttm_prev_year=Decimal("1000"),
    )
    assert res_drop.revenue_contraction_guard is True
    assert res_drop.gross_contract_exposure_ratio is None


def test_sloan_accrual_calculation() -> None:
    """Verifies Sloan Accrual Ratio = (NI_TTM - CFO_TTM) / Average_Assets."""
    # NI = 100, CFO = -50, Current Assets = 1000, Prev Year Assets = 1000 (Average = 1000)
    # Sloan = (100 - (-50)) / 1000 = 150 / 1000 = 0.15 (15% of assets)
    res = calculate_sloan_accrual(
        net_income_ttm=Decimal("100"),
        cfo_ttm=Decimal("-50"),
        total_assets_current=Decimal("1000"),
        total_assets_prev_year=Decimal("1000"),
    )
    assert res.average_assets_idr == Decimal("1000")
    assert res.sloan_ratio_ttm == Decimal("0.15")


def test_cash_coverage_and_debt_free_guard() -> None:
    """Verifies Cash Coverage ratio and zero-debt guard."""
    # Case 1: Standard coverage
    # Cash = 200, ST Debt = 1000 (Coverage = 0.20x)
    res = calculate_cash_coverage(
        cash_and_equivalents=Decimal("200"),
        st_bank_loans=Decimal("500"),
        current_maturities_bank_loans=Decimal("300"),
        current_maturities_bonds_sukuk_mtn=Decimal("150"),
        current_portion_lease=Decimal("50"),
    )
    assert res.st_debt_idr == Decimal("1000")
    assert res.cash_coverage_ratio == Decimal("0.20")
    assert res.debt_free_short_term is False

    # Case 2: Zero short-term debt (Debt-free)
    res_zero_debt = calculate_cash_coverage(
        cash_and_equivalents=Decimal("200"),
        st_bank_loans=Decimal("0"),
        current_maturities_bank_loans=Decimal("0"),
        current_maturities_bonds_sukuk_mtn=Decimal("0"),
        current_portion_lease=Decimal("0"),
    )
    assert res_zero_debt.st_debt_idr == Decimal("0")
    assert res_zero_debt.cash_coverage_ratio is None
    assert res_zero_debt.debt_free_short_term is True

