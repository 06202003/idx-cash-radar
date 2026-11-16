"""
Deterministic Mathematical Calculation Engine.
Strictly implements Sections 5.2, 5.3, and 5.4 of AGENTS.md.
Zero floating point hallucinations; uses Decimal throughout.
"""

from __future__ import annotations

from decimal import Decimal

from src.models.metrics import (
    CashCoverageMetrics,
    ContractExposureMetrics,
    SloanAccrualMetrics,
)


def calculate_contract_exposure(
    trade_receivables_3rd: Decimal,
    trade_receivables_related: Decimal,
    contract_assets_current: Decimal,
    contract_assets_non_current: Decimal,
    contract_liabilities_current: Decimal,
    contract_liabilities_non_current: Decimal,
    revenue_ttm: Decimal | None,
    revenue_ttm_prev_year: Decimal | None = None,
    gross_ratio_prev_year: Decimal | None = None,
) -> ContractExposureMetrics:
    """
    Computes PSAK 72 Gross & Net Contract Exposure Ratios with Revenue Contraction Guard.
    """
    gross_exposure = (
        trade_receivables_3rd
        + trade_receivables_related
        + contract_assets_current
        + contract_assets_non_current
    )
    net_exposure = gross_exposure - (
        contract_liabilities_current + contract_liabilities_non_current
    )

    # Zero-denominator and contraction guard evaluation:
    # If Revenue_TTM <= 0 OR Revenue dropped > 50% YoY
    is_contraction = False
    if revenue_ttm is None or revenue_ttm <= Decimal("0"):
        is_contraction = True
    elif revenue_ttm_prev_year is not None and revenue_ttm_prev_year > Decimal("0"):
        yoy_change = (revenue_ttm - revenue_ttm_prev_year) / revenue_ttm_prev_year
        if yoy_change < Decimal("-0.50"):
            is_contraction = True

    if is_contraction or revenue_ttm is None or revenue_ttm <= Decimal("0"):
        return ContractExposureMetrics(
            gross_exposure_idr=gross_exposure,
            net_exposure_idr=net_exposure,
            revenue_ttm_idr=revenue_ttm,
            gross_contract_exposure_ratio=None,
            net_contract_exposure_ratio=None,
            gross_divergence_yoy_bps=None,
            revenue_contraction_guard=True,
        )

    gross_ratio = gross_exposure / revenue_ttm
    net_ratio = net_exposure / revenue_ttm

    divergence_bps = None
    if gross_ratio_prev_year is not None:
        # Divergence in percentage points * 100 = basis points (bps)
        divergence_bps = (gross_ratio - gross_ratio_prev_year) * Decimal("10000")

    return ContractExposureMetrics(
        gross_exposure_idr=gross_exposure,
        net_exposure_idr=net_exposure,
        revenue_ttm_idr=revenue_ttm,
        gross_contract_exposure_ratio=gross_ratio,
        net_contract_exposure_ratio=net_ratio,
        gross_divergence_yoy_bps=divergence_bps,
        revenue_contraction_guard=False,
    )


def calculate_sloan_accrual(
    net_income_ttm: Decimal,
    cfo_ttm: Decimal,
    total_assets_current: Decimal,
    total_assets_prev_year: Decimal | None = None,
) -> SloanAccrualMetrics:
    """
    Computes Sloan Accrual Ratio (TTM): (NI_TTM - CFO_TTM) / Average_Assets.
    """
    if total_assets_prev_year is not None and total_assets_prev_year > Decimal("0"):
        average_assets = (total_assets_current + total_assets_prev_year) / Decimal("2")
    else:
        average_assets = total_assets_current

    if average_assets <= Decimal("0"):
        return SloanAccrualMetrics(
            net_income_ttm_idr=net_income_ttm,
            cfo_ttm_idr=cfo_ttm,
            average_assets_idr=average_assets,
            sloan_ratio_ttm=None,
        )

    sloan_ratio = (net_income_ttm - cfo_ttm) / average_assets
    return SloanAccrualMetrics(
        net_income_ttm_idr=net_income_ttm,
        cfo_ttm_idr=cfo_ttm,
        average_assets_idr=average_assets,
        sloan_ratio_ttm=sloan_ratio,
    )


def calculate_cash_coverage(
    cash_and_equivalents: Decimal,
    st_bank_loans: Decimal,
    current_maturities_bank_loans: Decimal,
    current_maturities_bonds_sukuk_mtn: Decimal,
    current_portion_lease: Decimal,
) -> CashCoverageMetrics:
    """
    Computes Cash-to-Short-Term Interest-Bearing Debt Coverage.
    Excludes Trade Payables and Accrued Expenses.
    Guards division by zero via debt_free_short_term.
    """
    st_debt = (
        st_bank_loans
        + current_maturities_bank_loans
        + current_maturities_bonds_sukuk_mtn
        + current_portion_lease
    )

    if st_debt == Decimal("0"):
        return CashCoverageMetrics(
            cash_idr=cash_and_equivalents,
            st_debt_idr=st_debt,
            cash_coverage_ratio=None,
            debt_free_short_term=True,
        )

    coverage = cash_and_equivalents / st_debt
    return CashCoverageMetrics(
        cash_idr=cash_and_equivalents,
        st_debt_idr=st_debt,
        cash_coverage_ratio=coverage,
        debt_free_short_term=False,
    )

