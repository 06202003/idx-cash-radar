"""SQLite & Supabase PostgreSQL repository for watchlists, alert logs, and broker history."""

from __future__ import annotations

import os
import sqlite3
import ssl
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from src.config import DATABASE_URL, DB_PATH

WIB = ZoneInfo("Asia/Jakarta")


def _build_pg_engine(raw_url: str) -> Any:
    """Builds a SQLAlchemy Engine for Supabase PostgreSQL using pg8000 with SSL."""
    from sqlalchemy import create_engine

    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql+pg8000://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+pg8000" not in url and "+psycopg" not in url:
        url = "postgresql+pg8000://" + url[len("postgresql://"):]

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return create_engine(url, future=True, pool_pre_ping=True, connect_args={"ssl_context": ctx})


class _UnifiedConn:
    """Thin wrapper normalizing `?` placeholders & dict-row results across SQLite and PostgreSQL."""

    def __init__(self, conn: Any, is_pg: bool) -> None:
        self._conn = conn
        self._is_pg = is_pg

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        if not self._is_pg:
            return self._conn.execute(sql, params)
        from sqlalchemy import text

        # Convert positional `?` to `:p0`, `:p1`, ... for SQLAlchemy text()
        parts = sql.split("?")
        if len(parts) > 1:
            rebuilt = []
            bind: dict[str, Any] = {}
            for idx, chunk in enumerate(parts[:-1]):
                key = f"p{idx}"
                rebuilt.append(chunk + f":{key}")
                bind[key] = params[idx]
            rebuilt.append(parts[-1])
            sql_pg = "".join(rebuilt)
        else:
            sql_pg = sql
            bind = {}
        return self._conn.execute(text(sql_pg), bind)

    def fetchall_dicts(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]:
        res = self.execute(sql, params)
        if not self._is_pg:
            return [dict(r) for r in res.fetchall()]
        return [dict(r._mapping) for r in res.fetchall()]

    def fetchone_dict(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> dict[str, Any] | None:
        res = self.execute(sql, params)
        if not self._is_pg:
            row = res.fetchone()
            return dict(row) if row is not None else None
        row = res.fetchone()
        return dict(row._mapping) if row is not None else None


class AlertStore:
    """Manages watchlists, alert_logs, mm_events, and broker_daily_history in SQLite or Supabase."""

    def __init__(self, db_path: Path = DB_PATH, database_url: str | None = None) -> None:
        self.db_path = db_path
        resolved_url = (database_url if database_url is not None else (DATABASE_URL or os.getenv("DATABASE_URL", ""))).strip()
        # Use PostgreSQL only when explicitly provided or using default DB_PATH (so tests with tmp_path stay SQLite)
        use_pg = bool(resolved_url) and (database_url is not None or db_path == DB_PATH)
        self.is_postgres = use_pg
        self._pg_engine = _build_pg_engine(resolved_url) if use_pg else None
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[_UnifiedConn]:
        if self.is_postgres and self._pg_engine is not None:
            with self._pg_engine.begin() as conn:
                yield _UnifiedConn(conn, is_pg=True)
            return
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield _UnifiedConn(conn, is_pg=False)
        finally:
            conn.close()

    def _init_schema(self) -> None:
        if self.is_postgres:
            stmts = [
                """
                CREATE TABLE IF NOT EXISTS watchlists (
                    chat_id BIGINT NOT NULL,
                    ticker TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, ticker)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS alert_logs (
                    id SERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    chat_id BIGINT,
                    ticker TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    price_close DOUBLE PRECISION,
                    p_up_pct DOUBLE PRECISION,
                    composite_score DOUBLE PRECISION,
                    badge TEXT,
                    news_sentiment TEXT
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS mm_events (
                    id SERIAL PRIMARY KEY,
                    ts_wib TEXT NOT NULL,
                    day_wib TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    side TEXT,
                    price INTEGER,
                    lot_delta INTEGER,
                    freq_delta INTEGER,
                    value_idr DOUBLE PRECISION,
                    detail TEXT
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_mm_events_ticker_day ON mm_events (ticker, day_wib)",
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    chat_id BIGINT PRIMARY KEY,
                    capital_idr DOUBLE PRECISION NOT NULL DEFAULT 100000000.0,
                    risk_pct DOUBLE PRECISION NOT NULL DEFAULT 0.01,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS broker_daily_history (
                    day_wib TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    broker_code TEXT NOT NULL,
                    broker_type TEXT NOT NULL DEFAULT '',
                    side TEXT NOT NULL,
                    net_val_idr DOUBLE PRECISION NOT NULL,
                    net_lot BIGINT NOT NULL DEFAULT 0,
                    avg_price DOUBLE PRECISION,
                    PRIMARY KEY (day_wib, ticker, broker_code)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_broker_hist_ticker_day ON broker_daily_history (ticker, day_wib)",
                """
                CREATE TABLE IF NOT EXISTS tradebook_daily_summary (
                    day_wib TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    haka_lot BIGINT NOT NULL DEFAULT 0,
                    haki_lot BIGINT NOT NULL DEFAULT 0,
                    haka_val_idr DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    haki_val_idr DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    close_price DOUBLE PRECISION,
                    PRIMARY KEY (day_wib, ticker)
                )
                """,
            ]
            with self._connect() as conn:
                for s in stmts:
                    conn.execute(s)
            return

        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS watchlists (
                        chat_id INTEGER NOT NULL,
                        ticker TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (chat_id, ticker)
                    );

                    CREATE TABLE IF NOT EXISTS alert_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        chat_id INTEGER,
                        ticker TEXT NOT NULL,
                        alert_type TEXT NOT NULL,
                        price_close REAL,
                        p_up_pct REAL,
                        composite_score REAL,
                        badge TEXT,
                        news_sentiment TEXT
                    );

                    CREATE TABLE IF NOT EXISTS mm_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts_wib TEXT NOT NULL,
                        day_wib TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        side TEXT,
                        price INTEGER,
                        lot_delta INTEGER,
                        freq_delta INTEGER,
                        value_idr REAL,
                        detail TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_mm_events_ticker_day
                        ON mm_events (ticker, day_wib);

                    CREATE TABLE IF NOT EXISTS user_settings (
                        chat_id INTEGER PRIMARY KEY,
                        capital_idr REAL NOT NULL DEFAULT 100000000.0,
                        risk_pct REAL NOT NULL DEFAULT 0.01,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS broker_daily_history (
                        day_wib TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        broker_code TEXT NOT NULL,
                        broker_type TEXT NOT NULL DEFAULT '',
                        side TEXT NOT NULL,
                        net_val_idr REAL NOT NULL,
                        net_lot INTEGER NOT NULL DEFAULT 0,
                        avg_price REAL,
                        PRIMARY KEY (day_wib, ticker, broker_code)
                    );
                    CREATE INDEX IF NOT EXISTS idx_broker_hist_ticker_day
                        ON broker_daily_history (ticker, day_wib);

                    CREATE TABLE IF NOT EXISTS tradebook_daily_summary (
                        day_wib TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        haka_lot INTEGER NOT NULL DEFAULT 0,
                        haki_lot INTEGER NOT NULL DEFAULT 0,
                        haka_val_idr REAL NOT NULL DEFAULT 0.0,
                        haki_val_idr REAL NOT NULL DEFAULT 0.0,
                        close_price REAL,
                        PRIMARY KEY (day_wib, ticker)
                    );
                    """
                )
        finally:
            conn.close()

    def add_watch(self, chat_id: int, ticker: str) -> None:
        clean_t = ticker.strip().upper().replace(".JK", "")
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlists (chat_id, ticker, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id, ticker) DO NOTHING
                """,
                (chat_id, clean_t, now),
            )

    def remove_watch(self, chat_id: int, ticker: str) -> bool:
        clean_t = ticker.strip().upper().replace(".JK", "")
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM watchlists WHERE chat_id = ? AND ticker = ?",
                (chat_id, clean_t),
            )
            return cur.rowcount > 0

    def list_watch(self, chat_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.fetchall_dicts(
                "SELECT ticker FROM watchlists WHERE chat_id = ? ORDER BY ticker",
                (chat_id,),
            )
        return [str(r["ticker"]) for r in rows]

    def list_all_subscribers(self) -> dict[int, list[str]]:
        with self._connect() as conn:
            rows = conn.fetchall_dicts("SELECT chat_id, ticker FROM watchlists ORDER BY chat_id, ticker")
        out: dict[int, list[str]] = {}
        for r in rows:
            out.setdefault(int(r["chat_id"]), []).append(str(r["ticker"]))
        return out

    def log_alert(
        self,
        ticker: str,
        alert_type: str,
        price_close: float | None,
        p_up_pct: float | None,
        composite_score: float | None,
        badge: str,
        news_sentiment: str,
        chat_id: int | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_logs (
                    created_at, chat_id, ticker, alert_type,
                    price_close, p_up_pct, composite_score, badge, news_sentiment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, chat_id, ticker.upper(), alert_type, price_close, p_up_pct, composite_score, badge, news_sentiment),
            )

    def count_logs(self) -> int:
        with self._connect() as conn:
            row = conn.fetchone_dict("SELECT COUNT(*) AS c FROM alert_logs")
        return int(row["c"]) if row else 0

    def log_mm_event(
        self,
        ticker: str,
        event_type: str,
        side: str | None = None,
        price: int | None = None,
        lot_delta: int | None = None,
        freq_delta: int | None = None,
        value_idr: float | None = None,
        detail: str = "",
        now_wib: datetime | None = None,
    ) -> None:
        dt = now_wib or datetime.now(WIB)
        clean_t = ticker.strip().upper().replace(".JK", "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mm_events (
                    ts_wib, day_wib, ticker, event_type, side, price,
                    lot_delta, freq_delta, value_idr, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dt.strftime("%H:%M:%S"),
                    dt.strftime("%Y-%m-%d"),
                    clean_t,
                    event_type,
                    side,
                    price,
                    lot_delta,
                    freq_delta,
                    value_idr,
                    detail,
                ),
            )

    def get_mm_events(
        self,
        ticker: str,
        day_wib: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        clean_t = ticker.strip().upper().replace(".JK", "")
        target_day = day_wib or datetime.now(WIB).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.fetchall_dicts(
                """
                SELECT ts_wib, day_wib, ticker, event_type, side, price,
                       lot_delta, freq_delta, value_idr, detail
                FROM mm_events
                WHERE ticker = ? AND day_wib = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (clean_t, target_day, limit),
            )
        return list(reversed(rows))

    def format_mm_pattern_report(self, ticker: str, day_wib: str | None = None) -> str:
        clean_t = ticker.strip().upper().replace(".JK", "")
        target_day = day_wib or datetime.now(WIB).strftime("%Y-%m-%d")
        events = self.get_mm_events(clean_t, day_wib=target_day, limit=100)
        if not events:
            return (
                f"📊 *POLA MARKET MAKER | {clean_t} ({target_day})*\n"
                "Belum ada rekaman event orderbook/tape hari ini.\n"
                "Pastikan saham sudah masuk `/watch` saat jam bursa (09:00–16:00 WIB)."
            )

        counts: dict[str, int] = {}
        for ev in events:
            et = ev["event_type"]
            counts[et] = counts.get(et, 0) + 1

        summary_lines = [
            f"• Wall Dipasang: `{counts.get('WALL_ADDED', 0)}x` | Wall Dicabut: `{counts.get('WALL_PULLED', 0)}x`",
            f"• Dimakan HAKA/HAKI: `{counts.get('WALL_EATEN', 0)}x` | Dominan 1M: HAKA `{counts.get('HAKA_1M', 0)}x` / HAKI `{counts.get('HAKI_1M', 0)}x`",
            f"• Broker Flip: `{counts.get('BROKER_FLIP', 0)}x`",
        ]

        timeline: list[str] = []
        for ev in events[-10:]:
            px = f"@{ev['price']:,}".replace(",", ".") if ev.get("price") else ""
            lot = f"{ev['lot_delta']:+,} lot".replace(",", ".") if ev.get("lot_delta") is not None else ""
            val = ""
            if ev.get("value_idr"):
                v = float(ev["value_idr"])
                val = f"Rp {v/1e9:.2f}M" if abs(v) >= 1e9 else f"Rp {v/1e6:.0f}Jt"
            parts = [p for p in (ev["event_type"], ev.get("side") or "", px, lot, val, ev.get("detail") or "") if p]
            timeline.append(f"`{ev['ts_wib']}` {' '.join(parts)}")

        return (
            f"📊 *REKAMAN POLA MARKET MAKER | {clean_t} ({target_day})*\n"
            + "\n".join(summary_lines)
            + "\n\n*Timeline Terakhir:*\n"
            + "\n".join(timeline)
        )

    def set_capital(self, chat_id: int, capital_idr: float, risk_pct: float = 0.01) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (chat_id, capital_idr, risk_pct, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    capital_idr = excluded.capital_idr,
                    risk_pct = excluded.risk_pct,
                    updated_at = excluded.updated_at
                """,
                (chat_id, max(100_000.0, float(capital_idr)), float(risk_pct), now),
            )

    def get_capital(self, chat_id: int, default: float = 100_000_000.0) -> float:
        with self._connect() as conn:
            row = conn.fetchone_dict(
                "SELECT capital_idr FROM user_settings WHERE chat_id = ?",
                (chat_id,),
            )
        return float(row["capital_idr"]) if row else default

    def upsert_broker_daily(
        self,
        day_wib: str,
        ticker: str,
        rows: list[dict[str, Any]],
    ) -> int:
        """Stores daily net broker summary rows (both BUY and SELL sides) for a ticker & date."""
        if not rows:
            return 0
        clean_t = ticker.strip().upper().replace(".JK", "")
        saved = 0
        with self._connect() as conn:
            for r in rows:
                code = str(r.get("broker_code") or r.get("code") or "").strip().upper()
                if not code or code == "?":
                    continue
                side = str(r.get("side") or "BUY").strip().upper()
                net_val = float(r.get("net_val_idr") or 0.0)
                net_lot = int(r.get("net_lot") or 0)
                avg_px = r.get("avg_price")
                btype = str(r.get("broker_type") or r.get("type") or "")
                conn.execute(
                    """
                    INSERT INTO broker_daily_history (
                        day_wib, ticker, broker_code, broker_type, side,
                        net_val_idr, net_lot, avg_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(day_wib, ticker, broker_code) DO UPDATE SET
                        broker_type = excluded.broker_type,
                        side = excluded.side,
                        net_val_idr = excluded.net_val_idr,
                        net_lot = excluded.net_lot,
                        avg_price = excluded.avg_price
                    """,
                    (day_wib, clean_t, code, btype, side, net_val, net_lot, avg_px),
                )
                saved += 1
        return saved

    def list_broker_history_days(self, ticker: str, lookback_days: int = 60) -> list[str]:
        clean_t = ticker.strip().upper().replace(".JK", "")
        cutoff = (datetime.now(WIB) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.fetchall_dicts(
                """
                SELECT DISTINCT day_wib
                FROM broker_daily_history
                WHERE ticker = ? AND day_wib >= ?
                ORDER BY day_wib ASC
                """,
                (clean_t, cutoff),
            )
        return [str(r["day_wib"]) for r in rows]

    def get_broker_daily_history(self, ticker: str, lookback_days: int = 60) -> list[dict[str, Any]]:
        clean_t = ticker.strip().upper().replace(".JK", "")
        cutoff = (datetime.now(WIB) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            return conn.fetchall_dicts(
                """
                SELECT day_wib, ticker, broker_code, broker_type, side,
                       net_val_idr, net_lot, avg_price
                FROM broker_daily_history
                WHERE ticker = ? AND day_wib >= ?
                ORDER BY day_wib ASC, net_val_idr DESC
                """,
                (clean_t, cutoff),
            )

    def upsert_tradebook_daily(
        self,
        day_wib: str,
        ticker: str,
        haka_lot: int,
        haki_lot: int,
        haka_val_idr: float,
        haki_val_idr: float,
        close_price: float | None = None,
    ) -> None:
        clean_t = ticker.strip().upper().replace(".JK", "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tradebook_daily_summary (
                    day_wib, ticker, haka_lot, haki_lot, haka_val_idr, haki_val_idr, close_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day_wib, ticker) DO UPDATE SET
                    haka_lot = excluded.haka_lot,
                    haki_lot = excluded.haki_lot,
                    haka_val_idr = excluded.haka_val_idr,
                    haki_val_idr = excluded.haki_val_idr,
                    close_price = excluded.close_price
                """,
                (day_wib, clean_t, int(haka_lot), int(haki_lot), float(haka_val_idr), float(haki_val_idr), close_price),
            )

    def get_tradebook_daily_history(self, ticker: str, lookback_days: int = 30) -> list[dict[str, Any]]:
        clean_t = ticker.strip().upper().replace(".JK", "")
        cutoff = (datetime.now(WIB) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            return conn.fetchall_dicts(
                """
                SELECT day_wib, ticker, haka_lot, haki_lot, haka_val_idr, haki_val_idr, close_price
                FROM tradebook_daily_summary
                WHERE ticker = ? AND day_wib >= ?
                ORDER BY day_wib ASC
                """,
                (clean_t, cutoff),
            )
