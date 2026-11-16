"""
Sub-Industry Peer Cohort Analytics Engine.
Strictly implements Small-N Guard (N < 8) and exact rank / quartile assignments.
Zero pseudo-precision decimal percentiles as mandated in Section 5.6 of AGENTS.md.
"""

from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Literal

from src.models.metrics import CohortRankResult

MIN_PEER_COUNT = 8  # Locked threshold in PRE_REGISTRATION.md


def evaluate_cohort_rank(
    metric_name: str,
    target_ticker: str,
    peer_values: dict[str, Decimal | None],
    higher_is: Literal["higher", "lower"] = "higher",
) -> CohortRankResult:
    """
    Ranks target_ticker among peer cohort for a specific quarter.
    - If active peers N < 8: activates small_n_guard (reports median only, no quartiles).
    - If N >= 8: assigns exact rank (k of N) and integer quartile (Q1, Q2, Q3, Q4).
    """
    # 1. Filter valid non-None values
    valid_peers: dict[str, Decimal] = {}
    for t, val in peer_values.items():
        if val is not None:
            try:
                valid_peers[t.upper()] = Decimal(str(val))
            except Exception:
                continue
    n = len(valid_peers)

    target_val = valid_peers.get(target_ticker.upper())

    if n == 0 or target_val is None:
        return CohortRankResult(
            metric_name=metric_name,
            peer_count=n,
            small_n_guard=True,
            issuer_value=target_val,
            industry_median=None,
            exact_rank=None,
            total_peers=n,
            quartile=None,
        )

    # Compute median
    median_val = statistics.median(valid_peers.values())
    if isinstance(median_val, (int, float)):
        median_dec = Decimal(str(median_val))
    else:
        median_dec = median_val

    # Check Small-N Guard
    if n < MIN_PEER_COUNT:
        return CohortRankResult(
            metric_name=metric_name,
            peer_count=n,
            small_n_guard=True,
            issuer_value=target_val,
            industry_median=median_dec,
            exact_rank=None,
            total_peers=n,
            quartile=None,
        )

    # N >= 8: Sort peers
    # If higher_is == "higher", rank 1 is highest value
    # If higher_is == "lower", rank 1 is lowest value
    reverse_sort = (higher_is == "higher")
    sorted_peers = sorted(
        valid_peers.items(), key=lambda item: item[1], reverse=reverse_sort
    )

    rank = None
    for idx, (t, _) in enumerate(sorted_peers, start=1):
        if t == target_ticker.upper():
            rank = idx
            break

    # Assign integer quartile (Q1 = top 25%, Q2 = 25-50%, Q3 = 50-75%, Q4 = 75-100%)
    if rank is not None:
        fraction = Decimal(rank) / Decimal(n)
        if fraction <= Decimal("0.25"):
            quartile = "Q1"
        elif fraction <= Decimal("0.50"):
            quartile = "Q2"
        elif fraction <= Decimal("0.75"):
            quartile = "Q3"
        else:
            quartile = "Q4"
    else:
        quartile = None

    return CohortRankResult(
        metric_name=metric_name,
        peer_count=n,
        small_n_guard=False,
        issuer_value=target_val,
        industry_median=median_dec,
        exact_rank=rank,
        total_peers=n,
        quartile=quartile,
    )
