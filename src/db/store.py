"""SQLite repository for watchlists and alert audit logs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.config import DB_PATH


class AlertStore:
    """Manages watchlists and alert_logs in SQLite."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
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
                """
            )

    def add_watch(self, chat_id: int, ticker: str) -> None:
        clean_t = ticker.strip().upper().replace(".JK", "")
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO watchlists (chat_id, ticker, created_at) VALUES (?, ?, ?)",
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
            rows = conn.execute(
                "SELECT ticker FROM watchlists WHERE chat_id = ? ORDER BY ticker",
                (chat_id,),
            ).fetchall()
        return [str(r["ticker"]) for r in rows]

    def list_all_subscribers(self) -> dict[int, list[str]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT chat_id, ticker FROM watchlists ORDER BY chat_id, ticker").fetchall()
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
            row = conn.execute("SELECT COUNT(*) AS c FROM alert_logs").fetchone()
        return int(row["c"]) if row else 0
