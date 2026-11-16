"""
Fast batch migration utility to copy local SQLite data (idx_cash_radar.db)
into Supabase PostgreSQL (via DATABASE_URL) using multi-row INSERTs.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.db.repository import FinancialRepository  # noqa: E402


def _batch_insert(
    pg: Any,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    conflict_target: str,
    update_cols: list[str],
    batch_size: int = 200,
) -> None:
    if not rows:
        return
    col_list = ", ".join(columns)
    row_ph = "(" + ", ".join(["?"] * len(columns)) + ")"
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)

    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        values_sql = ", ".join([row_ph] * len(chunk))
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES {values_sql} "
            f"ON CONFLICT({conflict_target}) DO UPDATE SET {update_clause};"
        )
        flat_params: list[Any] = []
        for r in chunk:
            flat_params.extend(r[c] for c in columns)
        pg.execute(sql, tuple(flat_params))


def main() -> int:
    load_dotenv(ROOT_DIR / ".env")
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        print("ERROR: DATABASE_URL is not set. Add your Supabase Postgres URI to .env first.")
        return 1

    sqlite_path = ROOT_DIR / "idx_cash_radar.db"
    if not sqlite_path.exists():
        print(f"ERROR: Local SQLite file not found at {sqlite_path}")
        return 1

    pg_repo = FinancialRepository()
    if not pg_repo.is_postgres:
        print("ERROR: Repository did not initialize in PostgreSQL mode.")
        return 1

    sq = sqlite3.connect(str(sqlite_path))
    sq.row_factory = sqlite3.Row

    with pg_repo.get_connection() as pg:
        issuers = [dict(r) for r in sq.execute("SELECT * FROM issuers").fetchall()]
        _batch_insert(
            pg,
            "issuers",
            ["ticker", "company_name", "idx_sub_industry", "listing_status", "delisted_date"],
            issuers,
            "ticker",
            ["company_name", "idx_sub_industry", "listing_status", "delisted_date"],
        )
        print(f"Migrated {len(issuers)} issuers.")

        filings = [dict(r) for r in sq.execute("SELECT * FROM filings").fetchall()]
        _batch_insert(
            pg,
            "filings",
            [
                "filing_id", "ticker", "fiscal_year", "period_code", "period_end_date",
                "filing_date", "is_audited", "is_restatement", "reporting_currency",
                "fx_rate_to_idr", "sanity_check_passed", "source_xbrl_hash",
            ],
            filings,
            "filing_id",
            ["sanity_check_passed", "source_xbrl_hash"],
        )
        print(f"Migrated {len(filings)} filings.")

        facts = [dict(r) for r in sq.execute("SELECT * FROM canonical_facts").fetchall()]
        _batch_insert(
            pg,
            "canonical_facts",
            [
                "filing_id", "canonical_key", "value_idr", "raw_xbrl_tag",
                "raw_context_ref", "raw_unit_ref", "raw_decimals", "raw_lexical_value",
            ],
            facts,
            "filing_id, canonical_key",
            [
                "value_idr", "raw_xbrl_tag", "raw_context_ref",
                "raw_unit_ref", "raw_decimals", "raw_lexical_value",
            ],
        )
        print(f"Migrated {len(facts)} canonical_facts.")

        metrics = [dict(r) for r in sq.execute("SELECT * FROM computed_metrics").fetchall()]
        _batch_insert(
            pg,
            "computed_metrics",
            [
                "filing_id", "ticker", "period_end_date", "is_audit_derived_q4",
                "cfo_single_q_idr", "cfo_ttm_idr", "net_income_ttm_idr", "revenue_ttm_idr",
                "gross_contract_exposure_ratio", "net_contract_exposure_ratio",
                "gross_divergence_yoy_bps", "sloan_ratio_ttm", "cash_coverage_ratio",
                "revenue_contraction_guard", "debt_free_short_term",
                "flag_accrual_divergence", "flag_acute_liquidity",
            ],
            metrics,
            "filing_id",
            [
                "cfo_single_q_idr", "cfo_ttm_idr", "net_income_ttm_idr", "revenue_ttm_idr",
                "gross_contract_exposure_ratio", "net_contract_exposure_ratio",
                "gross_divergence_yoy_bps", "sloan_ratio_ttm", "cash_coverage_ratio",
                "revenue_contraction_guard", "debt_free_short_term",
                "flag_accrual_divergence", "flag_acute_liquidity",
            ],
        )
        print(f"Migrated {len(metrics)} computed_metrics.")

    sq.close()
    print("Migration to Supabase PostgreSQL completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
