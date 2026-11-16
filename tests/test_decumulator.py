"""
Tests for YTD Decumulation and TTM Calculation Engine.
Verifies arithmetic accuracy, cross-check, and zero extrapolation on missing quarters.
"""

from __future__ import annotations

from decimal import Decimal

from src.engine.decumulator import (
    QuarterFlows,
    StandaloneQuarter,
    compute_ttm_from_quarters,
    decumulate_year,
)


def test_decumulate_full_year() -> None:
    """Verifies that full 4 quarters are decumulated correctly from YTD numbers."""
    q1 = QuarterFlows(
        "WIKA", 2023, "Q1",
        cfo_ytd=Decimal("-20"), revenue_ytd=Decimal("100"), net_income_ytd=Decimal("10")
    )
    q2 = QuarterFlows(
        "WIKA", 2023, "Q2",
        cfo_ytd=Decimal("-50"), revenue_ytd=Decimal("250"), net_income_ytd=Decimal("25")
    )
    q3 = QuarterFlows(
        "WIKA", 2023, "Q3",
        cfo_ytd=Decimal("-30"), revenue_ytd=Decimal("420"), net_income_ytd=Decimal("40")
    )
    fy = QuarterFlows(
        "WIKA", 2023, "FY",
        cfo_ytd=Decimal("80"), revenue_ytd=Decimal("650"), net_income_ytd=Decimal("60")
    )

    res = decumulate_year(q1, q2, q3, fy)

    assert "Q1" in res
    assert res["Q1"].revenue == Decimal("100")
    assert res["Q1"].cfo == Decimal("-20")
    assert res["Q1"].is_audit_derived_q4 is False

    assert "Q2" in res
    assert res["Q2"].revenue == Decimal("150")  # 250 - 100
    assert res["Q2"].cfo == Decimal("-30")      # -50 - (-20)
    assert res["Q2"].net_income == Decimal("15")

    assert "Q3" in res
    assert res["Q3"].revenue == Decimal("170")  # 420 - 250
    assert res["Q3"].cfo == Decimal("20")       # -30 - (-50)

    assert "Q4" in res
    assert res["Q4"].revenue == Decimal("230")  # 650 - 420
    assert res["Q4"].cfo == Decimal("110")      # 80 - (-30)
    assert res["Q4"].is_audit_derived_q4 is True  # Tagged audit derived as per Section 5.1


def test_decumulate_missing_interim_no_extrapolation() -> None:
    """Verifies that missing interim quarters do NOT result in linear extrapolation."""
    q1 = QuarterFlows("ADHI", 2023, "Q1", cfo_ytd=Decimal("-20"), revenue_ytd=Decimal("100"))
    # Q2 is missing
    q3 = QuarterFlows("ADHI", 2023, "Q3", cfo_ytd=Decimal("-30"), revenue_ytd=Decimal("420"))

    res = decumulate_year(q1, None, q3, None)
    assert "Q1" in res
    assert "Q2" not in res
    assert "Q3" not in res  # cannot compute Q3 without Q2


def test_ttm_calculation_and_cross_check() -> None:
    """Verifies TTM sum of 4 quarters and algebraic cross-check."""
    q_22_q4 = StandaloneQuarter(
        "PTPP", 2022, "Q4", cfo=Decimal("50"), revenue=Decimal("200"), net_income=Decimal("20")
    )
    q_23_q1 = StandaloneQuarter(
        "PTPP", 2023, "Q1", cfo=Decimal("-10"), revenue=Decimal("100"), net_income=Decimal("10")
    )
    q_23_q2 = StandaloneQuarter(
        "PTPP", 2023, "Q2", cfo=Decimal("-20"), revenue=Decimal("150"), net_income=Decimal("15")
    )
    q_23_q3 = StandaloneQuarter(
        "PTPP", 2023, "Q3", cfo=Decimal("15"), revenue=Decimal("180"), net_income=Decimal("25")
    )

    four_q = [q_22_q4, q_23_q1, q_23_q2, q_23_q3]

    ytd_current = QuarterFlows("PTPP", 2023, "Q3", revenue_ytd=Decimal("430"))
    fy_prev = QuarterFlows("PTPP", 2022, "FY", revenue_ytd=Decimal("600"))
    ytd_prev = QuarterFlows("PTPP", 2022, "Q3", revenue_ytd=Decimal("400"))

    ttm = compute_ttm_from_quarters(
        target_ticker="PTPP",
        target_year=2023,
        target_period="Q3",
        four_quarters=four_q,
        ytd_current=ytd_current,
        fy_prev=fy_prev,
        ytd_prev_same_q=ytd_prev,
    )

    assert ttm.revenue_ttm == Decimal("630")
    assert ttm.cfo_ttm == Decimal("35")
    assert ttm.net_income_ttm == Decimal("70")
    assert ttm.is_cross_check_verified is True
