"""
CLI Ingestion Pipeline for IDX Cash & Accrual Radar.
Extracts, normalizes, validates 4-way sanity check, and persists canonical facts to SQLite3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.db.repository import FinancialRepository  # noqa: E402
from src.models.canonical import IssuerModel  # noqa: E402
from src.parser.normalizer import TaxonomyNormalizer  # noqa: E402
from src.parser.xbrl_reader import read_xbrl_document  # noqa: E402

# Known issuers directory for metadata enrichment
KNOWN_ISSUERS: dict[str, dict[str, str]] = {
    "ADHI": {
        "company_name": "Adhi Karya (Persero) Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "PTPP": {
        "company_name": "PP (Persero) Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "WIKA": {
        "company_name": "Wijaya Karya (Persero) Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "WSKT": {
        "company_name": "Waskita Karya (Persero) Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "TOTL": {
        "company_name": "Total Bangun Persada Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "NRCA": {
        "company_name": "Nusa Raya Cipta Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "JKON": {
        "company_name": "Jaya Konstruksi Manggala Pratama Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "ACST": {
        "company_name": "Acset Indonusa Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "WEGE": {
        "company_name": "Wijaya Karya Bangunan Gedung Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "PPRE": {
        "company_name": "PP Presisi Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "DGIK": {
        "company_name": "Nusa Konstruksi Enjiniring Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
    "PBSA": {
        "company_name": "Paramita Bangun Sarana Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    },
}


def ingest_file(
    file_path: Path,
    repo: FinancialRepository,
    normalizer: TaxonomyNormalizer,
    strict: bool = False,
) -> bool:
    """Ingests a single XBRL filing into the database."""
    print(f"-> Processing: {file_path.name} ...")
    raw_doc = read_xbrl_document(file_path)
    res = normalizer.normalize(raw_doc)

    ticker = res.filing.ticker.upper()
    issuer_meta = KNOWN_ISSUERS.get(ticker, {
        "company_name": f"PT {ticker} Tbk.",
        "idx_sub_industry": "Konstruksi Bangunan & Rekayasa Sipil",
    })

    # Save issuer
    repo.save_issuer(
        IssuerModel(
            ticker=ticker,
            company_name=issuer_meta["company_name"],
            idx_sub_industry=issuer_meta["idx_sub_industry"],
            listing_status="ACTIVE",
        )
    )

    if not res.sanity_passed:
        print(f"   ⚠️ Sanity check failed for {ticker} ({res.filing.filing_id})")
        if strict:
            print("   ⛔ Skipped saving due to --strict flag.")
            return False

    # Save filing header and facts
    repo.save_filing(res.filing)
    repo.save_canonical_facts(res.filing.filing_id, res.facts)
    status_str = "PASSED" if res.sanity_passed else "FAILED"
    print(f"   ✅ Saved {len(res.facts)} canonical facts to database. (Sanity: {status_str})")

    # Automatically compute and store metrics into computed_metrics table
    try:
        from scripts.run_case_evaluation import evaluate_filing
        metrics = evaluate_filing(res.filing.filing_id, repo)
        if metrics:
            repo.save_computed_metrics(metrics)
            print(f"   📊 Computed and saved metrics for {ticker} ({res.filing.filing_id})")
    except Exception as exc:
        print(f"   ⚠️ Could not compute metrics for {ticker}: {exc}")

    return True


def ingest_directory(
    directory: Path | str,
    db_path: Path | str = "./idx_cash_radar.db",
    strict: bool = False,
    recursive: bool = True,
) -> dict[str, int]:
    """Ingests all .xbrl files in directory (and subdirectories) into the database."""
    dir_path = Path(directory)
    if recursive:
        xbrl_files = sorted(
            list(dir_path.rglob("*.xbrl")) + list(dir_path.rglob("*.xml"))
        )
    else:
        xbrl_files = sorted(
            list(dir_path.glob("*.xbrl")) + list(dir_path.glob("*.xml"))
        )

    # De-duplicate files if any
    unique_files = list({f.resolve(): f for f in xbrl_files}.values())

    repo = FinancialRepository(db_path=db_path)
    normalizer = TaxonomyNormalizer()

    print("=" * 80)
    print("🚀 IDX CASH & ACCRUAL RADAR — BATCH XBRL INGESTION PIPELINE")
    print(f"📁 Source Directory: {dir_path.resolve()}")
    print(f"💾 Target Database : {Path(db_path).resolve()}")
    print(f"📊 Files Found     : {len(unique_files)}")
    print("=" * 80)

    success_count = 0
    failed_count = 0

    for f in unique_files:
        try:
            ok = ingest_file(f, repo, normalizer, strict=strict)
            if ok:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"   ❌ Exception ingesting {f.name}: {e}")
            failed_count += 1

    print("=" * 80)
    summary_msg = (
        f"🎉 Ingestion Complete. Total: {len(unique_files)} | "
        f"Success: {success_count} | Failed: {failed_count}"
    )
    print(summary_msg)
    print("=" * 80)

    return {"total": len(unique_files), "success": success_count, "failed": failed_count}


def main() -> None:
    parser = argparse.ArgumentParser(description="IDX XBRL Filings Ingestion CLI")
    parser.add_argument(
        "--dir",
        default=None,
        help="Directory containing .xbrl files (default: data/raw_xbrl or spike_samples)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch process all files in data/raw_xbrl/",
    )
    parser.add_argument(
        "--db",
        default="./idx_cash_radar.db",
        help="SQLite database path (default: ./idx_cash_radar.db)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Reject filings that do not pass 4-Way Sanity Check",
    )
    args = parser.parse_args()

    target_dir = args.dir
    if not target_dir:
        has_raw = Path("./data/raw_xbrl").exists()
        target_dir = "./data/raw_xbrl" if args.batch or has_raw else "./spike_samples"

    res = ingest_directory(target_dir, args.db, strict=args.strict, recursive=True)
    if res["failed"] > 0 and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
