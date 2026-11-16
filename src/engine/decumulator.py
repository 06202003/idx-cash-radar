"""
Deterministic YTD Decumulation and Trailing Twelve Months (TTM) Engine.
Enforces Section 5.1 of AGENTS.md:
- Q1 = YTD_3M
- Q2 = YTD_6M - YTD_3M
- Q3 = YTD_9M - YTD_6M
- Q4 = FY_12M - YTD_9M (is_audit_derived_q4 = True)
- TTM_t = sum_{i=0}^3 Single_Quarter_{t-i} (with cross-check: YTD_t + FY_{t-1} - YTD_{t-4})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


@dataclass
class QuarterFlows:
    ticker: str
    fiscal_year: int
    period_code: Literal["Q1", "Q2", "Q3", "FY"]
    cfo_ytd: Decimal | None = None
    revenue_ytd: Decimal | None = None
    net_income_ytd: Decimal | None = None


@dataclass
class StandaloneQuarter:
    ticker: str
    fiscal_year: int
    period_code: Literal["Q1", "Q2", "Q3", "Q4"]
    cfo: Decimal | None = None
    revenue: Decimal | None = None
    net_income: Decimal | None = None
    is_audit_derived_q4: bool = False


@dataclass
class TTMResult:
    ticker: str
    fiscal_year: int
    period_code: Literal["Q1", "Q2", "Q3", "FY"]
    cfo_ttm: Decimal | None = None
    revenue_ttm: Decimal | None = None
    net_income_ttm: Decimal | None = None
    quarters_used: list[str] = field(default_factory=list)
    is_cross_check_verified: bool = False


def _diff_decimal(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is not None and b is not None:
        return a - b
    return None


def decumulate_year(
    q1: QuarterFlows | None,
    q2: QuarterFlows | None,
    q3: QuarterFlows | None,
    fy: QuarterFlows | None,
) -> dict[str, StandaloneQuarter]:
    """
    Decumulate YTD reports into Standalone Quarters Q1, Q2, Q3, Q4.
    If an interim quarter is missing, standalone quarter is set to None (no linear extrapolation).
    """
    base = q1 or q2 or q3 or fy
    if not base:
        return {}
    ticker = base.ticker
    year = base.fiscal_year
    result: dict[str, StandaloneQuarter] = {}

    # Q1 = YTD_3M
    if q1:
        result["Q1"] = StandaloneQuarter(
            ticker=ticker,
            fiscal_year=year,
            period_code="Q1",
            cfo=q1.cfo_ytd,
            revenue=q1.revenue_ytd,
            net_income=q1.net_income_ytd,
            is_audit_derived_q4=False,
        )

    # Q2 = YTD_6M - YTD_3M
    if q2 and q1:
        result["Q2"] = StandaloneQuarter(
            ticker=ticker,
            fiscal_year=year,
            period_code="Q2",
            cfo=_diff_decimal(q2.cfo_ytd, q1.cfo_ytd),
            revenue=_diff_decimal(q2.revenue_ytd, q1.revenue_ytd),
            net_income=_diff_decimal(q2.net_income_ytd, q1.net_income_ytd),
            is_audit_derived_q4=False,
        )

    # Q3 = YTD_9M - YTD_6M
    if q3 and q2:
        result["Q3"] = StandaloneQuarter(
            ticker=ticker,
            fiscal_year=year,
            period_code="Q3",
            cfo=_diff_decimal(q3.cfo_ytd, q2.cfo_ytd),
            revenue=_diff_decimal(q3.revenue_ytd, q2.revenue_ytd),
            net_income=_diff_decimal(q3.net_income_ytd, q2.net_income_ytd),
            is_audit_derived_q4=False,
        )

    # Q4 = FY_12M - YTD_9M (is_audit_derived_q4 = True)
    if fy and q3:
        result["Q4"] = StandaloneQuarter(
            ticker=ticker,
            fiscal_year=year,
            period_code="Q4",
            cfo=_diff_decimal(fy.cfo_ytd, q3.cfo_ytd),
            revenue=_diff_decimal(fy.revenue_ytd, q3.revenue_ytd),
            net_income=_diff_decimal(fy.net_income_ytd, q3.net_income_ytd),
            is_audit_derived_q4=True,
        )

    return result


def compute_ttm_from_quarters(
    target_ticker: str,
    target_year: int,
    target_period: Literal["Q1", "Q2", "Q3", "FY"],
    four_quarters: list[StandaloneQuarter],
    ytd_current: QuarterFlows | None = None,
    fy_prev: QuarterFlows | None = None,
    ytd_prev_same_q: QuarterFlows | None = None,
) -> TTMResult:
    """
    Computes TTM by summing the 4 consecutive standalone quarters ending on target period.
    Performs optional cross-check: TTM = YTD_t + FY_{t-1} - YTD_{t-4}.
    """
    if len(four_quarters) != 4:
        return TTMResult(
            ticker=target_ticker,
            fiscal_year=target_year,
            period_code=target_period,
            quarters_used=[],
            is_cross_check_verified=False,
        )

    # Sum components
    cfo_vals = [q.cfo for q in four_quarters if q.cfo is not None]
    rev_vals = [q.revenue for q in four_quarters if q.revenue is not None]
    ni_vals = [q.net_income for q in four_quarters if q.net_income is not None]

    cfo_ttm = sum(cfo_vals, Decimal("0")) if len(cfo_vals) == 4 else None
    rev_ttm = sum(rev_vals, Decimal("0")) if len(rev_vals) == 4 else None
    ni_ttm = sum(ni_vals, Decimal("0")) if len(ni_vals) == 4 else None

    # Cross-check validation if comparative filings available
    cross_check_ok = False
    if rev_ttm is not None and ytd_current and fy_prev and ytd_prev_same_q:
        if (
            ytd_current.revenue_ytd is not None
            and fy_prev.revenue_ytd is not None
            and ytd_prev_same_q.revenue_ytd is not None
        ):
            expected_rev = (
                ytd_current.revenue_ytd + fy_prev.revenue_ytd - ytd_prev_same_q.revenue_ytd
            )
            cross_check_ok = abs(rev_ttm - expected_rev) == Decimal("0")

    quarters_labels = [f"{q.fiscal_year}_{q.period_code}" for q in four_quarters]

    return TTMResult(
        ticker=target_ticker,
        fiscal_year=target_year,
        period_code=target_period,
        cfo_ttm=cfo_ttm,
        revenue_ttm=rev_ttm,
        net_income_ttm=ni_ttm,
        quarters_used=quarters_labels,
        is_cross_check_verified=cross_check_ok,
    )
