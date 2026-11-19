"""SQLite repository for watchlists and alert audit logs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.config import DB_PATH

WIB = ZoneInfo("Asia/Jakarta")


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
            rows = conn.execute(
                """
                SELECT ts_wib, day_wib, ticker, event_type, side, price,
                       lot_delta, freq_delta, value_idr, detail
                FROM mm_events
                WHERE ticker = ? AND day_wib = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (clean_t, target_day, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

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
