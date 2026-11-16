"""
Deterministic SQLite3 repository for IDX Cash & Accrual Radar.
Strict adherence to standard library sqlite3 and Decimal string conversions.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from src.models.canonical import CanonicalFactModel, FilingModel, IssuerModel
from src.models.metrics import ComputedFilingMetrics

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class FinancialRepository:
    def __init__(self, db_path: Path | str = "./idx_cash_radar.db") -> None:
        self.db_path = Path(db_path)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager that guarantees transaction commit and connection close on Windows."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database with the relational DDL schema."""
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            ddl_script = f.read()
        with self.get_connection() as conn:
            conn.executescript(ddl_script)

    def save_issuer(self, issuer: IssuerModel) -> None:
        """Insert or replace issuer metadata."""
        query = """
        INSERT INTO issuers (ticker, company_name, idx_sub_industry, listing_status, delisted_date)
        VALUES (:ticker, :company_name, :idx_sub_industry, :listing_status, :delisted_date)
        ON CONFLICT(ticker) DO UPDATE SET
            company_name = excluded.company_name,
            idx_sub_industry = excluded.idx_sub_industry,
            listing_status = excluded.listing_status,
            delisted_date = excluded.delisted_date;
        """
        with self.get_connection() as conn:
            conn.execute(query, issuer.model_dump())

    def get_issuer(self, ticker: str) -> IssuerModel | None:
        """Fetch issuer by ticker symbol."""
        query = "SELECT * FROM issuers WHERE ticker = ?;"
        with self.get_connection() as conn:
            row = conn.execute(query, (ticker.upper(),)).fetchone()
            if row:
                return IssuerModel(**dict(row))
        return None

    def save_filing(self, filing: FilingModel) -> None:
        """Insert or update financial filing header record."""
        query = """
        INSERT INTO filings (
            filing_id, ticker, fiscal_year, period_code, period_end_date,
            filing_date, is_audited, is_restatement, reporting_currency,
            fx_rate_to_idr, sanity_check_passed, source_xbrl_hash
        ) VALUES (
            :filing_id, :ticker, :fiscal_year, :period_code, :period_end_date,
            :filing_date, :is_audited, :is_restatement, :reporting_currency,
            :fx_rate_to_idr, :sanity_check_passed, :source_xbrl_hash
        ) ON CONFLICT(filing_id) DO UPDATE SET
            sanity_check_passed = excluded.sanity_check_passed,
            source_xbrl_hash = excluded.source_xbrl_hash;
        """
        data = filing.model_dump()
        data["is_audited"] = 1 if filing.is_audited else 0
        data["is_restatement"] = 1 if filing.is_restatement else 0
        data["sanity_check_passed"] = 1 if filing.sanity_check_passed else 0
        data["fx_rate_to_idr"] = str(filing.fx_rate_to_idr)

        with self.get_connection() as conn:
            conn.execute(query, data)

    def get_filing(self, filing_id: str) -> FilingModel | None:
        """Retrieve filing record by unique filing_id."""
        query = "SELECT * FROM filings WHERE filing_id = ?;"
        with self.get_connection() as conn:
            row = conn.execute(query, (filing_id,)).fetchone()
            if row:
                d = dict(row)
                d["is_audited"] = bool(d["is_audited"])
                d["is_restatement"] = bool(d["is_restatement"])
                d["sanity_check_passed"] = bool(d["sanity_check_passed"])
                d["fx_rate_to_idr"] = Decimal(d["fx_rate_to_idr"])
                return FilingModel(**d)
        return None

    def save_canonical_facts(
        self, filing_id: str, facts: list[CanonicalFactModel]
    ) -> None:
        """Batch insert/replace canonical facts for a filing."""
        query = """
        INSERT INTO canonical_facts (
            filing_id, canonical_key, value_idr, raw_xbrl_tag,
            raw_context_ref, raw_unit_ref, raw_decimals, raw_lexical_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filing_id, canonical_key) DO UPDATE SET
            value_idr = excluded.value_idr,
            raw_xbrl_tag = excluded.raw_xbrl_tag,
            raw_context_ref = excluded.raw_context_ref,
            raw_decimals = excluded.raw_decimals,
            raw_lexical_value = excluded.raw_lexical_value;
        """
        rows = [
            (
                filing_id,
                f.canonical_key,
                str(f.value_idr),
                f.raw_xbrl_tag,
                f.raw_context_ref,
                f.raw_unit_ref,
                f.raw_decimals,
                f.raw_lexical_value,
            )
            for f in facts
        ]
        with self.get_connection() as conn:
            conn.executemany(query, rows)

    def get_canonical_facts(
        self, filing_id: str
    ) -> dict[str, CanonicalFactModel]:
        """Fetch all canonical facts for a filing indexed by canonical_key."""
        query = "SELECT * FROM canonical_facts WHERE filing_id = ?;"
        facts: dict[str, CanonicalFactModel] = {}
        with self.get_connection() as conn:
            for row in conn.execute(query, (filing_id,)).fetchall():
                d = dict(row)
                facts[d["canonical_key"]] = CanonicalFactModel(
                    canonical_key=d["canonical_key"],
                    value_idr=Decimal(d["value_idr"]),
                    raw_xbrl_tag=d["raw_xbrl_tag"],
                    raw_context_ref=d["raw_context_ref"],
                    raw_unit_ref=d["raw_unit_ref"],
                    raw_decimals=d["raw_decimals"],
                    raw_lexical_value=d["raw_lexical_value"],
                )
        return facts

    def log_demand(self, ticker: str) -> None:
        """Log ticker search request to demand_log."""
        query = "INSERT INTO demand_log (ticker) VALUES (?);"
        with self.get_connection() as conn:
            conn.execute(query, (ticker.upper(),))

    def save_computed_metrics(self, m: ComputedFilingMetrics) -> None:
        """Persists calculated metrics and safeguard flags to computed_metrics table."""
        query = """
        INSERT INTO computed_metrics (
            filing_id, ticker, period_end_date, is_audit_derived_q4,
            cfo_single_q_idr, cfo_ttm_idr, net_income_ttm_idr, revenue_ttm_idr,
            gross_contract_exposure_ratio, net_contract_exposure_ratio,
            gross_divergence_yoy_bps, sloan_ratio_ttm, cash_coverage_ratio,
            revenue_contraction_guard, debt_free_short_term,
            flag_accrual_divergence, flag_acute_liquidity
        ) VALUES (
            :filing_id, :ticker, :period_end_date, :is_audit_derived_q4,
            :cfo_single_q_idr, :cfo_ttm_idr, :net_income_ttm_idr, :revenue_ttm_idr,
            :gross_contract_exposure_ratio, :net_contract_exposure_ratio,
            :gross_divergence_yoy_bps, :sloan_ratio_ttm, :cash_coverage_ratio,
            :revenue_contraction_guard, :debt_free_short_term,
            :flag_accrual_divergence, :flag_acute_liquidity
        ) ON CONFLICT(filing_id) DO UPDATE SET
            cfo_single_q_idr = excluded.cfo_single_q_idr,
            cfo_ttm_idr = excluded.cfo_ttm_idr,
            net_income_ttm_idr = excluded.net_income_ttm_idr,
            revenue_ttm_idr = excluded.revenue_ttm_idr,
            gross_contract_exposure_ratio = excluded.gross_contract_exposure_ratio,
            net_contract_exposure_ratio = excluded.net_contract_exposure_ratio,
            gross_divergence_yoy_bps = excluded.gross_divergence_yoy_bps,
            sloan_ratio_ttm = excluded.sloan_ratio_ttm,
            cash_coverage_ratio = excluded.cash_coverage_ratio,
            revenue_contraction_guard = excluded.revenue_contraction_guard,
            debt_free_short_term = excluded.debt_free_short_term,
            flag_accrual_divergence = excluded.flag_accrual_divergence,
            flag_acute_liquidity = excluded.flag_acute_liquidity;
        """
        data = {
            "filing_id": m.filing_id,
            "ticker": m.ticker,
            "period_end_date": m.period_end_date,
            "is_audit_derived_q4": 1 if m.is_audit_derived_q4 else 0,
            "cfo_single_q_idr": str(m.cfo_single_q_idr) if m.cfo_single_q_idr else None,
            "cfo_ttm_idr": str(m.cfo_ttm_idr) if m.cfo_ttm_idr else None,
            "net_income_ttm_idr": str(m.net_income_ttm_idr) if m.net_income_ttm_idr else None,
            "revenue_ttm_idr": str(m.revenue_ttm_idr) if m.revenue_ttm_idr else None,
            "gross_contract_exposure_ratio": (
                str(m.contract_exposure.gross_contract_exposure_ratio)
                if m.contract_exposure.gross_contract_exposure_ratio
                else None
            ),
            "net_contract_exposure_ratio": (
                str(m.contract_exposure.net_contract_exposure_ratio)
                if m.contract_exposure.net_contract_exposure_ratio
                else None
            ),
            "gross_divergence_yoy_bps": (
                str(m.contract_exposure.gross_divergence_yoy_bps)
                if m.contract_exposure.gross_divergence_yoy_bps
                else None
            ),
            "sloan_ratio_ttm": (
                str(m.sloan_accrual.sloan_ratio_ttm)
                if m.sloan_accrual.sloan_ratio_ttm
                else None
            ),
            "cash_coverage_ratio": (
                str(m.cash_coverage.cash_coverage_ratio)
                if m.cash_coverage.cash_coverage_ratio
                else None
            ),
            "revenue_contraction_guard": (
                1 if m.contract_exposure.revenue_contraction_guard else 0
            ),
            "debt_free_short_term": 1 if m.cash_coverage.debt_free_short_term else 0,
            "flag_accrual_divergence": 1 if m.safeguards.flag_accrual_divergence else 0,
            "flag_acute_liquidity": 1 if m.safeguards.flag_acute_liquidity else 0,
        }
        with self.get_connection() as conn:
            conn.execute(query, data)

    def get_computed_metrics_row(self, filing_id: str) -> dict | None:
        """Fetch raw computed metrics row by filing_id."""
        query = "SELECT * FROM computed_metrics WHERE filing_id = ?;"
        with self.get_connection() as conn:
            row = conn.execute(query, (filing_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def add_to_watchlist(self, user_id: str, ticker: str) -> bool:
        """Adds ticker to user's personalized alert watchlist."""
        ticker = ticker.strip().upper()
        query = """
        INSERT OR IGNORE INTO user_watchlist (user_id, ticker)
        VALUES (?, ?);
        """
        with self.get_connection() as conn:
            cur = conn.execute(query, (str(user_id), ticker))
            return cur.rowcount > 0

    def remove_from_watchlist(self, user_id: str, ticker: str) -> bool:
        """Removes ticker from user's watchlist."""
        ticker = ticker.strip().upper()
        query = "DELETE FROM user_watchlist WHERE user_id = ? AND ticker = ?;"
        with self.get_connection() as conn:
            cur = conn.execute(query, (str(user_id), ticker))
            return cur.rowcount > 0

    def get_user_watchlist(self, user_id: str) -> list[str]:
        """Returns all tickers watched by a user."""
        query = "SELECT ticker FROM user_watchlist WHERE user_id = ? ORDER BY ticker ASC;"
        with self.get_connection() as conn:
            rows = conn.execute(query, (str(user_id),)).fetchall()
            return [r["ticker"] for r in rows]

    def get_subscribers_for_ticker(self, ticker: str) -> list[str]:
        """Returns all user_ids subscribed to a ticker."""
        ticker = ticker.strip().upper()
        query = "SELECT user_id FROM user_watchlist WHERE ticker = ?;"
        with self.get_connection() as conn:
            rows = conn.execute(query, (ticker,)).fetchall()
            return [str(r["user_id"]) for r in rows]
