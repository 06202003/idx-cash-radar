"""
Deterministic repository for IDX Cash & Accrual Radar.
Supports local SQLite3 (default/offline) and Supabase PostgreSQL via DATABASE_URL.
"""

from __future__ import annotations

import os
import re
import sqlite3
import ssl
import sys
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.models.canonical import CanonicalFactModel, FilingModel, IssuerModel
from src.models.metrics import ComputedFilingMetrics

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
POSTGRES_SCHEMA_PATH = Path(__file__).parent / "schema_postgres.sql"
_DEFAULT_DB_PATH = "./idx_cash_radar.db"


class _PgRow(dict):
    """Row wrapper supporting both dict['col'] and tuple-style row[0] indexing."""

    def __init__(self, columns: list[str], values: tuple[Any, ...]) -> None:
        super().__init__(zip(columns, values, strict=False))
        self._values = values

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _adapt_sql_for_postgres(sql: str, params: Any = None) -> tuple[str, Any]:
    """Converts SQLite '?' and ':name' placeholders to PostgreSQL '%s' and ordered tuple."""
    parts = re.split(r"('(?:''|[^'])*')", sql)
    out: list[str] = []
    ordered_values: list[Any] = []
    use_dict = isinstance(params, dict)

    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
            continue
        if use_dict:
            def _sub_named(m: re.Match[str]) -> str:
                ordered_values.append(params[m.group(1)])
                return "%s"

            part = re.sub(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)", _sub_named, part)
        else:
            part = part.replace("?", "%s")
        out.append(part)

    adapted_sql = "".join(out)
    if use_dict:
        return adapted_sql, tuple(ordered_values)
    return adapted_sql, params


class _PgCursorWrapper:
    """Thin cursor wrapper returning _PgRow objects."""

    def __init__(self, raw_cursor: Any) -> None:
        self._cur = raw_cursor

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount)

    def fetchone(self) -> _PgRow | None:
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in (self._cur.description or [])]
        return _PgRow(cols, tuple(row))

    def fetchall(self) -> list[_PgRow]:
        rows = self._cur.fetchall()
        cols = [d[0] for d in (self._cur.description or [])]
        return [_PgRow(cols, tuple(r)) for r in rows]


class _PgConnectionWrapper:
    """Thin connection wrapper mimicking sqlite3.Connection.execute()."""

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn

    def execute(self, sql: str, params: Any = None) -> _PgCursorWrapper:
        cur = self._conn.cursor()
        pg_sql, pg_params = _adapt_sql_for_postgres(sql, params)
        if pg_params is None:
            cur.execute(pg_sql)
        else:
            cur.execute(pg_sql, pg_params)
        return _PgCursorWrapper(cur)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _connect_postgres(database_url: str) -> _PgConnectionWrapper:
    import pg8000.dbapi

    parsed = urllib.parse.urlparse(database_url)
    ssl_ctx: ssl.SSLContext | None = ssl.create_default_context()
    if "localhost" in (parsed.hostname or "") or "127.0.0.1" in (parsed.hostname or ""):
        ssl_ctx = None
    elif ssl_ctx is not None:
        # Supabase pooler uses a custom/self-signed cert chain
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    raw_conn = pg8000.dbapi.connect(
        user=urllib.parse.unquote(parsed.username or "postgres"),
        password=urllib.parse.unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/postgres").lstrip("/"),
        ssl_context=ssl_ctx,
        timeout=15,
    )
    return _PgConnectionWrapper(raw_conn)


class FinancialRepository:
    def __init__(self, db_path: Path | str = _DEFAULT_DB_PATH) -> None:
        env_db_url = os.getenv("DATABASE_URL", "").strip()
        is_default_path = str(db_path) == _DEFAULT_DB_PATH
        in_pytest = bool(os.getenv("PYTEST_CURRENT_TEST")) or ("pytest" in sys.modules)
        self.database_url = env_db_url if (env_db_url and is_default_path and not in_pytest) else ""
        self.is_postgres = bool(self.database_url)
        self.db_path = Path(db_path)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Iterator[Any]:
        """Context manager guaranteeing transaction commit and connection close."""
        if self.is_postgres:
            conn = _connect_postgres(self.database_url)
        else:
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
        if self.is_postgres:
            # Fast-path: avoid 10 sequential DDL round-trips on every serverless cold start
            try:
                with self.get_connection() as conn:
                    conn.execute("SELECT 1 FROM issuers LIMIT 1")
                return
            except Exception:
                pass
            with open(POSTGRES_SCHEMA_PATH, encoding="utf-8") as f:
                ddl_script = f.read()
            statements = [s.strip() for s in ddl_script.split(";") if s.strip()]
            with self.get_connection() as conn:
                for stmt in statements:
                    conn.execute(stmt)
        else:
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
        INSERT INTO user_watchlist (user_id, ticker)
        VALUES (?, ?)
        ON CONFLICT(user_id, ticker) DO NOTHING;
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
