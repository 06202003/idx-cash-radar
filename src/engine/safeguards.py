"""
Safeguards Evaluation Engine for IDX Cash & Accrual Radar.
Strictly implements Section 5.5 of AGENTS.md and Section 3.3 of docs/PRE_REGISTRATION.md.
"""

from __future__ import annotations

from decimal import Decimal

from src.models.metrics import SafeguardEvaluation

SLOAN_ACCRUAL_THRESHOLD = Decimal("0.10")  # > +0.10 (+10% of Average Assets)
CASH_COVERAGE_THRESHOLD = Decimal("0.20")  # < 0.20x (Kas < 20% utang berbunga JP)


def evaluate_safeguards(
    net_income_ttm: Decimal,
    cfo_ttm: Decimal,
    cfo_single_q: Decimal | None,
    sloan_ratio_ttm: Decimal | None,
    st_debt: Decimal,
    debt_free_short_term: bool,
    cash_coverage: Decimal | None,
) -> SafeguardEvaluation:
    """
    Evaluates two independent boolean safeguard flags:
    1. flag_accrual_divergence (Paper Profits on Profitable Issuers)
    2. flag_acute_liquidity (Severe Cash Drain against ST Debt)
    """
    # 1. Accrual Divergence Flag
    flag_accrual = False
    if (
        net_income_ttm > Decimal("0")
        and cfo_ttm < Decimal("0")
        and (cfo_single_q is None or cfo_single_q < Decimal("0"))
        and sloan_ratio_ttm is not None
        and sloan_ratio_ttm > SLOAN_ACCRUAL_THRESHOLD
    ):
        flag_accrual = True

    # 2. Acute Liquidity Flag
    flag_liquidity = False
    if (
        cfo_ttm < Decimal("0")
        and not debt_free_short_term
        and st_debt > Decimal("0")
        and cash_coverage is not None
        and cash_coverage < CASH_COVERAGE_THRESHOLD
    ):
        flag_liquidity = True

    # Status summary
    if flag_accrual and flag_liquidity:
        status = "WASPADA: DIVERGENSI AKRUAL & TEKANAN LIKUIDITAS"
    elif flag_accrual:
        status = "PERHATIAN: DIVERGENSI AKRUAL (LABA TANPA KAS)"
    elif flag_liquidity:
        status = "PERHATIAN: TEKANAN LIKUIDITAS AKUT"
    else:
        status = "NORMAL / AMAN"

    return SafeguardEvaluation(
        flag_accrual_divergence=flag_accrual,
        flag_acute_liquidity=flag_liquidity,
        status_summary=status,
    )

