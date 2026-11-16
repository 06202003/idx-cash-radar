"""
Deterministic 4-Way Accounting Sanity Check Validator.
Enforces tolerance <= Rp 1.000.000 as strictly mandated in AGENTS.md Section 6.3.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

SANITY_TOLERANCE_IDR = Decimal("1000000")  # Rp 1.000.000


class SanityCheckFailure(Exception):
    """Raised when an XBRL filing fails accounting reconciliation checks."""
    pass


def run_4way_accounting_check(
    assets: Decimal | None,
    liabilities: Decimal | None,
    equity: Decimal | None,
    current_assets: Decimal | None,
    non_current_assets: Decimal | None,
    current_liabilities: Decimal | None,
    non_current_liabilities: Decimal | None,
    cash_balance_sheet: Decimal | None,
    cash_flow_ending: Decimal | None,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """
    Executes the 4-Way Sanity Check:
    1. Assets == Liabilities + Equity
    2. Assets == Current Assets + Non-Current Assets
    3. Liabilities == Current Liabilities + Non-Current Liabilities
    4. Cash Flow Ending Cash == Balance Sheet Cash
    """
    checks = []
    all_passed = True

    # 1. Assets == Liabilities + Equity
    if assets is not None and liabilities is not None and equity is not None:
        expected_assets = liabilities + equity
        diff1 = abs(assets - expected_assets)
        passed1 = diff1 <= SANITY_TOLERANCE_IDR
        if not passed1:
            all_passed = False
        checks.append({
            "check": "Assets == Liabilities + Equity",
            "passed": passed1,
            "difference": str(diff1),
            "left": str(assets),
            "right": str(expected_assets),
        })
    else:
        all_passed = False
        checks.append({
            "check": "Assets == Liabilities + Equity",
            "passed": False,
            "difference": "N/A",
            "notes": "Missing balance sheet components",
        })

    # 2. Assets == Current + Non-Current Assets
    if (
        assets is not None
        and current_assets is not None
        and non_current_assets is not None
    ):
        sum_ca_nca = current_assets + non_current_assets
        diff2 = abs(assets - sum_ca_nca)
        passed2 = diff2 <= SANITY_TOLERANCE_IDR
        if not passed2:
            all_passed = False
        checks.append({
            "check": "Assets == Current Assets + Non-Current Assets",
            "passed": passed2,
            "difference": str(diff2),
            "left": str(assets),
            "right": str(sum_ca_nca),
        })
    else:
        all_passed = False
        checks.append({
            "check": "Assets == Current Assets + Non-Current Assets",
            "passed": False,
            "difference": "N/A",
            "notes": "Missing Current or Non-Current Assets",
        })

    # 3. Liabilities == Current + Non-Current Liabilities
    if (
        liabilities is not None
        and current_liabilities is not None
        and non_current_liabilities is not None
    ):
        sum_cl_ncl = current_liabilities + non_current_liabilities
        diff3 = abs(liabilities - sum_cl_ncl)
        passed3 = diff3 <= SANITY_TOLERANCE_IDR
        if not passed3:
            all_passed = False
        checks.append({
            "check": "Liabilities == Current + Non-Current Liabilities",
            "passed": passed3,
            "difference": str(diff3),
            "left": str(liabilities),
            "right": str(sum_cl_ncl),
        })
    else:
        all_passed = False
        checks.append({
            "check": "Liabilities == Current + Non-Current Liabilities",
            "passed": False,
            "difference": "N/A",
            "notes": "Missing Current or Non-Current Liabilities",
        })

    # 4. Cash Flow Ending Cash == Balance Sheet Cash
    if cash_balance_sheet is not None and cash_flow_ending is not None:
        diff4 = abs(cash_balance_sheet - cash_flow_ending)
        passed4 = diff4 <= SANITY_TOLERANCE_IDR
        if not passed4:
            all_passed = False
        checks.append({
            "check": "Cash Flow Ending Cash == Balance Sheet Cash",
            "passed": passed4,
            "difference": str(diff4),
            "left": str(cash_flow_ending),
            "right": str(cash_balance_sheet),
        })
    else:
        all_passed = False
        checks.append({
            "check": "Cash Flow Ending Cash == Balance Sheet Cash",
            "passed": False,
            "difference": "N/A",
            "notes": "Missing Cash Balance Sheet or Cash Flow ending cash",
        })

    if raise_on_error and not all_passed:
        failed_checks = [c["check"] for c in checks if not c["passed"]]
        raise SanityCheckFailure(
            f"4-Way Accounting Sanity Check failed on: {', '.join(failed_checks)}"
        )

    return {
        "all_passed": all_passed,
        "checks": checks,
    }
