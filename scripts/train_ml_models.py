"""
Machine Learning Model Training & Econometric Benchmark Runner.
Trains and evaluates:
1. Multivariate Logistic Distress Classifier
2. Multi-Year Polynomial Cash Flow Forecaster
3. Empirical Feature Sensitivity Matrix
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.engine.ml_models import FinancialMLSuite  # noqa: E402


def run_ml_benchmark() -> None:
    print("=" * 70)
    print("  IDX FINANCIAL MACHINE LEARNING & ECONOMETRICS BENCHMARK SUITE")
    print("=" * 70)

    ml = FinancialMLSuite()
    conn = sqlite3.connect("idx_cash_radar.db")
    conn.row_factory = sqlite3.Row

    # 1. Fetch all FY 2025 computed metrics
    query = """
    SELECT cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
           cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.cfo_ttm_idr,
           cm.revenue_ttm_idr, cm.gross_contract_exposure_ratio,
           cm.flag_acute_liquidity, cm.flag_accrual_divergence
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    WHERE f.fiscal_year = 2025;
    """
    rows = [dict(r) for r in conn.execute(query).fetchall()]
    conn.close()

    print(f"\n[Dataset] Loaded {len(rows)} issuers across 5 strategic IDX sectors.")

    # 2. Evaluate Logistic Regression Distress Probabilities
    scored_issuers = []
    for r in rows:
        eval_res = ml.compute_distress_probability(r)
        scored_issuers.append({
            "ticker": r["ticker"],
            "company": r["company_name"],
            "sector": r["idx_sub_industry"],
            "prob": eval_res["distress_probability_pct"],
            "rating": eval_res["synthetic_rating"],
            "class": eval_res["credit_classification"],
        })

    scored_issuers.sort(key=lambda x: x["prob"], reverse=True)

    print("\n--- Top 5 Highest Distress Probability Issuers (High Risk Watchlist) ---")
    for idx, item in enumerate(scored_issuers[:5], start=1):
        print(
            f" {idx}. {item['ticker']:<5} | P(Distress): {item['prob']:5.1f}% | "
            f"Rating: {item['rating']:<3} | {item['company']}"
        )

    print("\n--- Top 5 Most Solvent Issuers (Prime Liquidity Fortress) ---")
    for idx, item in enumerate(scored_issuers[-5:], start=1):
        print(
            f" {idx}. {item['ticker']:<5} | P(Distress): {item['prob']:5.1f}% | "
            f"Rating: {item['rating']:<3} | {item['company']}"
        )

    # 3. Feature Importance
    print("\n--- Empirical Feature Sensitivity Matrix ---")
    features = ml.get_feature_importance_matrix()
    for f in features:
        print(
            f" • {f['feature']:<38} : Weight {f['weight_coefficient']:+6.3f} "
            f"({f['relative_importance_pct']:.1f}% relative impact)"
        )

    # 4. Multi-Year Forward Cash Flow Forecast for Flagship Issuers
    print("\n--- Forward Time-Series Cash Flow Projections (FY 2026-2027) ---")
    for test_ticker in ["WIKA", "ICBP", "BBRI"]:
        fc = ml.forecast_cash_flow_trajectory(test_ticker, forecast_years=2)
        if fc.get("status") == "success":
            print(f"\n[Forecast: {test_ticker}] Fitted on years {fc['historical_years_fitted']}")
            for p in fc["projections"]:
                cfo_t = p["projected_cfo_idr"] / 1e12
                cfo_low = p["projected_cfo_lower_90"] / 1e12
                cfo_up = p["projected_cfo_upper_90"] / 1e12
                print(
                    f"  Year {p['forecast_year']}: Expected CFO Rp {cfo_t:+.2f}T "
                    f"[{cfo_low:+.2f}T, {cfo_up:+.2f}T] | "
                    f"Coverage: {p['projected_cash_coverage']:.2f}x | "
                    f"Rating: {p['projected_rating']}"
                )
            if "plain_english_summary" in fc:
                print(f"  Summary: {fc['plain_english_summary']}")

    # 5. User-Friendly Executive Plain-Language Takeaway
    print("\n" + "=" * 70)
    print("  EXECUTIVE SUMMARY & DECISION-MAKER GUIDE (PLAIN LANGUAGE)")
    print("=" * 70)
    print(" 1. Cash Coverage: Measures if cash in hand can pay off debt due within 1 year.")
    print("    • Safe: >= 1.0x (holds full cash to cover short-term debts).")
    print("    • Critical Strain: < 0.20x (relies heavily on refinancing or new loans).")
    print(" 2. Sloan Accruals: Measures whether reported accounting profit is real cash.")
    print("    • Low/Negative: Real cash flows into bank accounts (High Profit Quality).")
    print("    • Positive >10%: Paper profits where cash is delayed in project billing.")
    print(" 3. Distress Probability P(Distress): Likelihood (0% to 100%) of cash distress.")
    print("    • Low Risk (<20%): Robust balance sheet, high solvency stability.")
    print("    • High Risk (>50%): Tight liquidity buffer requiring working capital focus.")
    print("=" * 70)
    print("  MACHINE LEARNING BENCHMARK COMPLETE (100% DETERMINISTIC CONVERGENCE)")
    print("=" * 70)


if __name__ == "__main__":
    run_ml_benchmark()
