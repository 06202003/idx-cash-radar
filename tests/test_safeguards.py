"""
Tests for Safeguard Evaluation Engine.
Strictly verifies Section 5.5 of AGENTS.md and Section 3.3 of docs/PRE_REGISTRATION.md.
"""

from __future__ import annotations

from decimal import Decimal

from src.engine.safeguards import evaluate_safeguards


def test_flag_accrual_divergence_triggers_on_paper_profits() -> None:
    """Verifies accrual flag trips when NI > 0, CFO < 0, and Sloan > 0.10."""
    res = evaluate_safeguards(
        net_income_ttm=Decimal("50000000000"),    # Profitable
        cfo_ttm=Decimal("-30000000000"),          # Negative operating cash flow
        cfo_single_q=Decimal("-10000000000"),     # Negative current quarter CFO
        sloan_ratio_ttm=Decimal("0.15"),          # > +0.10 (+15% of assets)
        st_debt=Decimal("100000000000"),
        debt_free_short_term=False,
        cash_coverage=Decimal("0.40"),            # Sufficient coverage (so liquidity flag is False)
    )
    assert res.flag_accrual_divergence is True
    assert res.flag_acute_liquidity is False
    assert "DIVERGENSI AKRUAL" in res.status_summary


def test_flag_accrual_divergence_ignores_unprofitable_issuers() -> None:
    """Verifies accrual divergence flag does NOT trip if net income is <= 0."""
    res = evaluate_safeguards(
        net_income_ttm=Decimal("-50000000000"),   # Unprofitable (Loss)
        cfo_ttm=Decimal("-30000000000"),
        cfo_single_q=Decimal("-10000000000"),
        sloan_ratio_ttm=Decimal("0.15"),
        st_debt=Decimal("100000000000"),
        debt_free_short_term=False,
        cash_coverage=Decimal("0.40"),
    )
    # Accrual divergence is specifically for paper profits masking cash drain
    assert res.flag_accrual_divergence is False


def test_flag_acute_liquidity_triggers_on_low_coverage_and_burn() -> None:
    """Verifies liquidity flag trips when CFO < 0 and Cash Coverage < 0.20x."""
    # Sub-case A: Loss-making company with acute liquidity crisis (like WIKA 2023)
    res_loss = evaluate_safeguards(
        net_income_ttm=Decimal("-7000000000000"),
        cfo_ttm=Decimal("-2500000000000"),
        cfo_single_q=None,
        sloan_ratio_ttm=Decimal("-0.05"),
        st_debt=Decimal("20000000000000"),
        debt_free_short_term=False,
        cash_coverage=Decimal("0.15"),  # < 0.20x
    )
    assert res_loss.flag_acute_liquidity is True
    assert res_loss.flag_accrual_divergence is False
    assert "TEKANAN LIKUIDITAS" in res_loss.status_summary

    # Sub-case B: Profitable company also suffering acute liquidity crisis
    res_both = evaluate_safeguards(
        net_income_ttm=Decimal("100000000000"),
        cfo_ttm=Decimal("-2500000000000"),
        cfo_single_q=Decimal("-500000000000"),
        sloan_ratio_ttm=Decimal("0.12"),  # > 0.10
        st_debt=Decimal("20000000000000"),
        debt_free_short_term=False,
        cash_coverage=Decimal("0.10"),    # < 0.20x
    )
    assert res_both.flag_accrual_divergence is True
    assert res_both.flag_acute_liquidity is True
    assert "WASPADA" in res_both.status_summary


def test_healthy_issuer_has_no_flags() -> None:
    """Verifies healthy company (positive CFO, adequate cash coverage) has zero flags."""
    res = evaluate_safeguards(
        net_income_ttm=Decimal("100000000000"),
        cfo_ttm=Decimal("120000000000"),  # Positive cash flow
        cfo_single_q=Decimal("30000000000"),
        sloan_ratio_ttm=Decimal("-0.02"),
        st_debt=Decimal("50000000000"),
        debt_free_short_term=False,
        cash_coverage=Decimal("1.50"),   # 1.50x coverage
    )
    assert res.flag_accrual_divergence is False
    assert res.flag_acute_liquidity is False
    assert "NORMAL" in res.status_summary
