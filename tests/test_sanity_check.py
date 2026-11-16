"""
Tests for 4-Way Accounting Sanity Check module.
Verifies all reconciliation identities and <= Rp 1.000.000 tolerance.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.parser.sanity_check import (
    SANITY_TOLERANCE_IDR,
    SanityCheckFailure,
    run_4way_accounting_check,
)


def test_sanity_check_all_pass() -> None:
    """Verifies that balanced balance sheet and cash flow pass all 4 checks."""
    res = run_4way_accounting_check(
        assets=Decimal("100000000000"),
        liabilities=Decimal("70000000000"),
        equity=Decimal("30000000000"),
        current_assets=Decimal("40000000000"),
        non_current_assets=Decimal("60000000000"),
        current_liabilities=Decimal("30000000000"),
        non_current_liabilities=Decimal("40000000000"),
        cash_balance_sheet=Decimal("5000000000"),
        cash_flow_ending=Decimal("5000000000"),
    )
    assert res["all_passed"] is True
    for c in res["checks"]:
        assert c["passed"] is True


def test_sanity_check_tolerance_exact_boundary() -> None:
    """Verifies difference <= 1,000,000 passes, > 1,000,000 fails."""
    # Difference = 1,000,000 IDR (exactly on tolerance)
    res_ok = run_4way_accounting_check(
        assets=Decimal("100000000000"),
        liabilities=Decimal("70000000000"),
        equity=Decimal("30000000000") - SANITY_TOLERANCE_IDR,
        current_assets=Decimal("40000000000"),
        non_current_assets=Decimal("60000000000"),
        current_liabilities=Decimal("30000000000"),
        non_current_liabilities=Decimal("40000000000"),
        cash_balance_sheet=Decimal("5000000000"),
        cash_flow_ending=Decimal("5000000000"),
    )
    assert res_ok["all_passed"] is True

    # Difference = 1,000,001 IDR (exceeds tolerance by 1 Rupiah)
    res_fail = run_4way_accounting_check(
        assets=Decimal("100000000000"),
        liabilities=Decimal("70000000000"),
        equity=Decimal("30000000000") - (SANITY_TOLERANCE_IDR + Decimal("1")),
        current_assets=Decimal("40000000000"),
        non_current_assets=Decimal("60000000000"),
        current_liabilities=Decimal("30000000000"),
        non_current_liabilities=Decimal("40000000000"),
        cash_balance_sheet=Decimal("5000000000"),
        cash_flow_ending=Decimal("5000000000"),
    )
    assert res_fail["all_passed"] is False
    assert res_fail["checks"][0]["passed"] is False


def test_sanity_check_raises_on_error() -> None:
    """Verifies that raise_on_error=True raises SanityCheckFailure."""
    with pytest.raises(SanityCheckFailure):
        run_4way_accounting_check(
            assets=Decimal("100000000000"),
            liabilities=Decimal("70000000000"),
            equity=Decimal("20000000000"),  # 10B difference
            current_assets=Decimal("40000000000"),
            non_current_assets=Decimal("60000000000"),
            current_liabilities=Decimal("30000000000"),
            non_current_liabilities=Decimal("40000000000"),
            cash_balance_sheet=Decimal("5000000000"),
            cash_flow_ending=Decimal("5000000000"),
            raise_on_error=True,
        )
