"""
Tests for Sub-Industry Peer Cohort Analytics Engine.
Verifies Small-N Guard (N < 8) and exact rank / quartile assignments.
"""

from __future__ import annotations

from decimal import Decimal

from src.engine.cohort import evaluate_cohort_rank


def test_cohort_small_n_guard() -> None:
    """Verifies that when active peers N < 8, small_n_guard is activated."""
    # Only 5 peers available
    peers = {
        "WIKA": Decimal("0.65"),
        "ADHI": Decimal("0.50"),
        "PTPP": Decimal("0.55"),
        "TOTL": Decimal("0.25"),
        "WEGE": Decimal("0.35"),
    }
    res = evaluate_cohort_rank(
        metric_name="gross_contract_exposure_ratio",
        target_ticker="WIKA",
        peer_values=peers,
    )
    assert res.small_n_guard is True
    assert res.peer_count == 5
    assert res.industry_median == Decimal("0.50")
    assert res.exact_rank is None
    assert res.quartile is None


def test_cohort_n_ge_8_ranks_and_quartiles() -> None:
    """Verifies that when N >= 8, exact rank and integer quartile are computed."""
    # 8 peers available
    peers = {
        "P1": Decimal("0.10"),
        "P2": Decimal("0.20"),
        "P3": Decimal("0.30"),
        "P4": Decimal("0.40"),
        "P5": Decimal("0.50"),
        "P6": Decimal("0.60"),
        "P7": Decimal("0.70"),
        "P8": Decimal("0.80"),  # Highest
    }
    # For metric where higher = higher risk (e.g. gross exposure), rank 1 is highest (P8)
    res_p8 = evaluate_cohort_rank("gross_exposure", "P8", peers, higher_is="higher")
    assert res_p8.small_n_guard is False
    assert res_p8.exact_rank == 1
    assert res_p8.quartile == "Q1"  # Top 25% (highest exposure)

    # P1 should be lowest (rank 8 of 8)
    res_p1 = evaluate_cohort_rank("gross_exposure", "P1", peers, higher_is="higher")
    assert res_p1.small_n_guard is False
    assert res_p1.exact_rank == 8
    assert res_p1.quartile == "Q4"

