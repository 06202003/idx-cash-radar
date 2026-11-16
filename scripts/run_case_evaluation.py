"""
Retrospective Case Evaluation Matrix CLI (2020–2025).
Strictly implements Section 4 of docs/PRE_REGISTRATION.md.
Evaluates Known Distress (Tabel A), False Alarms (Tabel B), and Control Peers (Tabel C).
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.db.repository import FinancialRepository  # noqa: E402
from src.engine.calculator import (  # noqa: E402
    calculate_cash_coverage,
    calculate_contract_exposure,
    calculate_sloan_accrual,
)
from src.engine.safeguards import evaluate_safeguards  # noqa: E402
from src.models.metrics import ComputedFilingMetrics  # noqa: E402

# Locked Ground Truth Official Events (PRE_REGISTRATION Section 4.1)
GROUND_TRUTH_EVENTS = {
    "WIKA": {
        "event_type": "Suspensi Gagal Bayar Obligasi/Sukuk",
        "official_ref": "Peng-SPT-00021/BEI.PP1/12-2023 (18 Des 2023)",
        "t0_quarter": "2023-Q4",
    },
    "WSKT": {
        "event_type": "Suspensi Gagal Bayar Obligasi Berkelanjutan III",
        "official_ref": "Peng-SPT-00006/BEI.PP3/05-2023 (8 Mei 2023)",
        "t0_quarter": "2023-Q2",
    },
}


def evaluate_filing(
    filing_id: str, repo: FinancialRepository
) -> ComputedFilingMetrics | None:
    """Calculates all metrics and safeguard flags for an ingested filing."""
    filing = repo.get_filing(filing_id)
    if not filing:
        return None

    facts = repo.get_canonical_facts(filing_id)

    # Helper to get fact decimal value
    def get_val(key: str) -> Decimal:
        f = facts.get(key)
        return f.value_idr if f else Decimal("0")

    # 1. Contract Exposure
    rev_ttm = get_val("revenue")  # For FY filings, duration is 12M TTM
    contract_metrics = calculate_contract_exposure(
        trade_receivables_3rd=get_val("trade_receivables_third_parties"),
        trade_receivables_related=get_val("trade_receivables_related_parties"),
        contract_assets_current=get_val("contract_assets_current"),
        contract_assets_non_current=get_val("contract_assets_non_current"),
        contract_liabilities_current=get_val("contract_liabilities_current"),
        contract_liabilities_non_current=get_val("contract_liabilities_non_current"),
        revenue_ttm=rev_ttm,
    )

    # 2. Sloan Accrual
    cfo_ttm = get_val("cfo")
    ni_ttm = get_val("net_income")
    assets_curr = get_val("total_assets")
    sloan_metrics = calculate_sloan_accrual(
        net_income_ttm=ni_ttm,
        cfo_ttm=cfo_ttm,
        total_assets_current=assets_curr,
    )

    # 3. Cash Coverage
    st_bank = get_val("st_debt_bank_loans")
    cm_bank = get_val("st_debt_current_maturities_bank_loans")
    cm_bonds = get_val("st_debt_current_maturities_bonds_sukuk_mtn")
    cm_lease = get_val("st_debt_current_portion_lease_liabilities")
    cash_val = get_val("cash_and_equivalents")

    coverage_metrics = calculate_cash_coverage(
        cash_and_equivalents=cash_val,
        st_bank_loans=st_bank,
        current_maturities_bank_loans=cm_bank,
        current_maturities_bonds_sukuk_mtn=cm_bonds,
        current_portion_lease=cm_lease,
    )

    # 4. Safeguards Evaluation
    cfo_single = cfo_ttm if filing.period_code == "Q1" else None
    safeguards = evaluate_safeguards(
        net_income_ttm=ni_ttm,
        cfo_ttm=cfo_ttm,
        cfo_single_q=cfo_single,
        sloan_ratio_ttm=sloan_metrics.sloan_ratio_ttm,
        st_debt=coverage_metrics.st_debt_idr,
        debt_free_short_term=coverage_metrics.debt_free_short_term,
        cash_coverage=coverage_metrics.cash_coverage_ratio,
    )

    computed = ComputedFilingMetrics(
        filing_id=filing_id,
        ticker=filing.ticker,
        period_end_date=filing.period_end_date,
        is_audit_derived_q4=(filing.period_code == "FY"),
        cfo_single_q_idr=cfo_single,
        cfo_ttm_idr=cfo_ttm,
        net_income_ttm_idr=ni_ttm,
        revenue_ttm_idr=rev_ttm,
        contract_exposure=contract_metrics,
        sloan_accrual=sloan_metrics,
        cash_coverage=coverage_metrics,
        safeguards=safeguards,
    )

    repo.save_computed_metrics(computed)
    return computed


def run_evaluation(db_path: Path | str = "./idx_cash_radar.db") -> None:
    """Runs case evaluation across all filings in the database and prints the matrix."""
    repo = FinancialRepository(db_path=db_path)

    query = (
        "SELECT filing_id, ticker, fiscal_year, period_code "
        "FROM filings ORDER BY ticker, fiscal_year, period_code;"
    )
    with repo.get_connection() as conn:
        filing_rows = conn.execute(query).fetchall()

    if not filing_rows:
        print("⚠️ No filings found in database. Ingest filings first via scripts/ingest_filings.py.")
        return

    evaluations: list[ComputedFilingMetrics] = []
    for r in filing_rows:
        m = evaluate_filing(r["filing_id"], repo)
        if m:
            evaluations.append(m)

    print("\n" + "=" * 90)
    print("📊 MATRIKS EVALUASI STUDI KASUS RETROSPEKTIF (2020–2025)")
    print("   Sesuai Spesifikasi Terkunci: docs/PRE_REGISTRATION.md Bagian 4.2")
    print("=" * 90)

    # 1. TABEL A: Known Distress & Restatement Cases
    print("\n### TABEL A — Known Distress & Restatement Cases (Lead Time & Detection Rate)")
    tbl_a_header = (
        "| Emiten | Peristiwa Ground Truth | No. Pengumuman BEI/OJK | "
        "T0 | Kuartal Sinyal | Lead Time | Status Deteksi |"
    )
    print(tbl_a_header)
    print("|:---|:---|:---|:---|:---|:---|:---|")
    for ticker, info in GROUND_TRUTH_EVENTS.items():
        issuer_evals = [e for e in evaluations if e.ticker == ticker]
        flagged_periods = [
            e.period_end_date[:7]
            for e in issuer_evals
            if e.safeguards.flag_accrual_divergence or e.safeguards.flag_acute_liquidity
        ]
        if flagged_periods:
            first_flag = flagged_periods[0]
            cov = issuer_evals[0].cash_coverage.cash_coverage_ratio
            cov_str = f"{cov:.2f}x" if cov else "N/A"
            sig_col = f"{first_flag} (Cov: {cov_str})"
            row_a = (
                f"| **{ticker}** | {info['event_type']} | {info['official_ref']} | "
                f"{info['t0_quarter']} | {sig_col} | Aktif | **TRUE POSITIVE** |"
            )
            print(row_a)
        else:
            if any(e.ticker == ticker for e in evaluations):
                row_fn = (
                    f"| **{ticker}** | {info['event_type']} | {info['official_ref']} | "
                    f"{info['t0_quarter']} | Tidak Terdeteksi | 0 | **FALSE NEGATIVE (MISSED)** |"
                )
                print(row_fn)
            else:
                row_pend = (
                    f"| **{ticker}** | {info['event_type']} | {info['official_ref']} | "
                    f"{info['t0_quarter']} | *(Berkas belum dimuat)* | - | PENDING DATA |"
                )
                print(row_pend)

    # 2. TABEL B: Flagged Non-Distress Cases (False Alarms Inspection)
    print("\n### TABEL B — Flagged Non-Distress Cases (Inspeksi False Alarms)")
    tbl_b_hdr = (
        "| Emiten | Periode | Laba Bersih TTM | CFO TTM | "
        "Sloan Ratio | Cash Coverage | Analisis Objektif |"
    )
    print(tbl_b_hdr)
    print("|:---|:---|:---|:---|:---|:---|:---|")
    non_distress_flags = 0
    for e in evaluations:
        if e.ticker not in GROUND_TRUTH_EVENTS:
            if e.safeguards.flag_accrual_divergence or e.safeguards.flag_acute_liquidity:
                non_distress_flags += 1
                c_cov = e.cash_coverage.cash_coverage_ratio
                cov = f"{c_cov:.2f}x" if c_cov else "N/A"
                s_ratio = e.sloan_accrual.sloan_ratio_ttm
                sloan = f"{s_ratio:.3f}" if s_ratio else "N/A"
                row_b = (
                    f"| {e.ticker} | {e.period_end_date} | Rp {e.net_income_ttm_idr:,} | "
                    f"Rp {e.cfo_ttm_idr:,} | {sloan} | {cov} | Arus kas operasi tertekan |"
                )
                print(row_b)
    if non_distress_flags == 0:
        print("| *(Tidak ada false alarm pada sampel emiten kontrol)* | - | - | - | - | - | - |")

    # 3. TABEL C: Unflagged Control Peers
    print("\n### TABEL C — Unflagged Control Peers (Statistik Emiten Sehat)")
    tbl_c_hdr = (
        "| Emiten | Periode | Gross Exposure Ratio | "
        "Sloan Ratio TTM | Cash Coverage | Status Safeguard |"
    )
    print(tbl_c_hdr)
    print("|:---|:---|:---|:---|:---|:---|")
    control_count = 0
    for e in evaluations:
        if not (e.safeguards.flag_accrual_divergence or e.safeguards.flag_acute_liquidity):
            control_count += 1
            c_cov = e.cash_coverage.cash_coverage_ratio
            cov = f"{c_cov:.2f}x" if c_cov else "N/A"
            s_ratio = e.sloan_accrual.sloan_ratio_ttm
            sloan = f"{s_ratio:.3f}" if s_ratio else "N/A"
            gross_r = (
                f"{e.contract_exposure.gross_contract_exposure_ratio * Decimal('100'):.1f}%"
                if e.contract_exposure.gross_contract_exposure_ratio
                else "N/A"
            )
            row_c = (
                f"| {e.ticker} | {e.period_end_date} | {gross_r} | "
                f"{sloan} | {cov} | {e.safeguards.status_summary} |"
            )
            print(row_c)
    if control_count == 0:
        print("| *(Seluruh emiten yang diuji menyalakan bendera perhatian)* | - | - | - | - | - |")
    print("=" * 90 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="IDX Retrospective Case Evaluation CLI")
    parser.add_argument(
        "--db",
        default="./idx_cash_radar.db",
        help="Path to SQLite database (default: ./idx_cash_radar.db)",
    )
    args = parser.parse_args()
    run_evaluation(args.db)


if __name__ == "__main__":
    main()
