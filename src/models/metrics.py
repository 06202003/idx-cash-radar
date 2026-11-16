"""
Pydantic schemas for calculated metrics, zero-denominator guards, and safeguard flags.
Locked in AGENTS.md Section 5 and docs/PRE_REGISTRATION.md Section 3.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ContractExposureMetrics(BaseModel):
    gross_exposure_idr: Decimal
    net_exposure_idr: Decimal
    revenue_ttm_idr: Decimal | None
    gross_contract_exposure_ratio: Decimal | None = None
    net_contract_exposure_ratio: Decimal | None = None
    gross_divergence_yoy_bps: Decimal | None = None
    revenue_contraction_guard: bool = False


class SloanAccrualMetrics(BaseModel):
    net_income_ttm_idr: Decimal
    cfo_ttm_idr: Decimal
    average_assets_idr: Decimal
    sloan_ratio_ttm: Decimal | None = None


class CashCoverageMetrics(BaseModel):
    cash_idr: Decimal
    st_debt_idr: Decimal
    cash_coverage_ratio: Decimal | None = None
    debt_free_short_term: bool = False


class SafeguardEvaluation(BaseModel):
    flag_accrual_divergence: bool = False
    flag_acute_liquidity: bool = False
    status_summary: str = "NORMAL"


class CohortRankResult(BaseModel):
    metric_name: str
    peer_count: int
    small_n_guard: bool = False
    issuer_value: Decimal | None = None
    industry_median: Decimal | None = None
    exact_rank: int | None = None  # 1 (lowest/best or highest depending on metric)
    total_peers: int | None = None
    quartile: str | None = None    # "Q1", "Q2", "Q3", "Q4" or None if small_n_guard


class ComputedFilingMetrics(BaseModel):
    filing_id: str
    ticker: str
    period_end_date: str
    is_audit_derived_q4: bool = False
    cfo_single_q_idr: Decimal | None = None
    cfo_ttm_idr: Decimal | None = None
    net_income_ttm_idr: Decimal | None = None
    revenue_ttm_idr: Decimal | None = None
    contract_exposure: ContractExposureMetrics
    sloan_accrual: SloanAccrualMetrics
    cash_coverage: CashCoverageMetrics
    safeguards: SafeguardEvaluation
    cohort_ranks: dict[str, CohortRankResult] = Field(default_factory=dict)

