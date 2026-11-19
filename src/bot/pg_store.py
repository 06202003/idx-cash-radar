"""PostgreSQL / Supabase state store for Telegram Bot (watchlists, schedules, idempotent alert logs, daily_snapshot)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

MAX_WATCHLIST_TICKERS = 20
TICKER_PATTERN = re.compile(r"^[A-Z0-9]{4,5}$")
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def normalize_database_url(raw_url: str | None = None, *, allow_sqlite_for_tests: bool = False) -> str:
    """Validates DATABASE_URL and enforces PostgreSQL in production."""
    url = (raw_url or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL belum diatur. Produksi wajib menggunakan PostgreSQL/Supabase (bukan SQLite)."
        )
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://"):]

    if url.startswith("sqlite") and not allow_sqlite_for_tests:
        raise RuntimeError("SQLite dilarang untuk produksi bot. Gunakan PostgreSQL/Supabase DATABASE_URL.")
    return url


class BotStateStore:
    """Thread-safe SQLAlchemy repository for bot watchlists, schedules, alerts, and evidence snapshots."""

    def __init__(self, database_url: str | None = None, *, allow_sqlite_for_tests: bool = False) -> None:
        url = normalize_database_url(database_url, allow_sqlite_for_tests=allow_sqlite_for_tests)
        self.engine: Engine = create_engine(url, future=True, pool_pre_ping=True)
        self.metadata = MetaData()

        self.user_watchlists = Table(
            "user_watchlists",
            self.metadata,
            Column("chat_id", BigInteger, primary_key=True),
            Column("ticker", String(10), primary_key=True),
            Column("created_at", String(40), nullable=False),
        )
        self.user_schedules = Table(
            "user_schedules",
            self.metadata,
            Column("chat_id", BigInteger, primary_key=True),
            Column("morning_time", String(5), nullable=False, default="08:30"),
            Column("updated_at", String(40), nullable=False),
        )
        self.alert_logs = Table(
            "alert_logs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("delivery_key", String(160), nullable=False, unique=True),
            Column("chat_id", BigInteger, nullable=True),
            Column("alert_date", Date, nullable=False),
            Column("alert_type", String(32), nullable=False),
            Column("ticker", String(16), nullable=False),
            Column("message_hash", String(64), nullable=False),
            Column("status", String(24), nullable=False),
            Column("error_detail", Text, nullable=True),
            Column("sent_at", String(40), nullable=False),
            Index("idx_alert_logs_chat_date_sqla", "chat_id", "alert_date"),
        )
        self.daily_snapshot = Table(
            "daily_snapshot",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("snapshot_date", Date, nullable=False),
            Column("ticker", String(10), nullable=False),
            Column("cash_status", String(48), nullable=False),
            Column("flags_json", Text, nullable=False),
            Column("close_price", Float, nullable=True),
            Column("volume", BigInteger, nullable=True),
            Column("news_items_json", Text, nullable=False),
            Column("idx_announcements_json", Text, nullable=False),
            Column("created_at", String(40), nullable=False),
            UniqueConstraint("snapshot_date", "ticker", name="uq_daily_snapshot_date_ticker"),
        )
        self.source_fetch_logs = Table(
            "source_fetch_logs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("fetched_at", String(40), nullable=False),
            Column("source_name", String(64), nullable=False),
            Column("ticker", String(16), nullable=True),
            Column("status", String(24), nullable=False),
            Column("detail", Text, nullable=True),
        )
        self.bot_analytics_events = Table(
            "bot_analytics_events",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("event_name", String(64), nullable=False),
            Column("ticker", String(16), nullable=True),
            Column("created_at", String(40), nullable=False),
        )
        self.metadata.create_all(self.engine)

    @staticmethod
    def validate_ticker(raw: str) -> str | None:
        t = (raw or "").strip().upper().replace(".JK", "")
        return t if TICKER_PATTERN.match(t) else None

    @staticmethod
    def validate_time_hhmm(raw: str) -> str | None:
        s = (raw or "").strip()
        return s if TIME_PATTERN.match(s) else None

    def add_watch(self, chat_id: int, ticker: str) -> tuple[bool, str]:
        clean_t = self.validate_ticker(ticker)
        if not clean_t:
            return False, "Format kode saham tidak valid."
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(self.user_watchlists.c.ticker).where(self.user_watchlists.c.chat_id == chat_id)
            ).scalars().all()
            if clean_t in existing:
                return True, f"{clean_t} sudah ada di watchlist Anda."
            if len(existing) >= MAX_WATCHLIST_TICKERS:
                return False, f"Batas maksimal {MAX_WATCHLIST_TICKERS} emiten per pengguna sudah tercapai."
            conn.execute(
                self.user_watchlists.insert().values(chat_id=chat_id, ticker=clean_t, created_at=now)
            )
            # Ensure default schedule row exists
            sched = conn.execute(
                select(self.user_schedules.c.chat_id).where(self.user_schedules.c.chat_id == chat_id)
            ).first()
            if not sched:
                conn.execute(
                    self.user_schedules.insert().values(
                        chat_id=chat_id, morning_time="08:30", updated_at=now
                    )
                )
        return True, f"{clean_t} ditambahkan ke watchlist."

    def remove_watch(self, chat_id: int, ticker: str) -> bool:
        clean_t = self.validate_ticker(ticker)
        if not clean_t:
            return False
        with self.engine.begin() as conn:
            res = conn.execute(
                delete(self.user_watchlists).where(
                    self.user_watchlists.c.chat_id == chat_id,
                    self.user_watchlists.c.ticker == clean_t,
                )
            )
            return (res.rowcount or 0) > 0

    def list_watch(self, chat_id: int) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self.user_watchlists.c.ticker)
                .where(self.user_watchlists.c.chat_id == chat_id)
                .order_by(self.user_watchlists.c.ticker)
            ).scalars().all()
        return list(rows)

    def set_morning_time(self, chat_id: int, hhmm: str) -> bool:
        valid = self.validate_time_hhmm(hhmm)
        if not valid:
            return False
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(self.user_schedules.c.chat_id).where(self.user_schedules.c.chat_id == chat_id)
            ).first()
            if existing:
                conn.execute(
                    self.user_schedules.update()
                    .where(self.user_schedules.c.chat_id == chat_id)
                    .values(morning_time=valid, updated_at=now)
                )
            else:
                conn.execute(
                    self.user_schedules.insert().values(
                        chat_id=chat_id, morning_time=valid, updated_at=now
                    )
                )
        return True

    def get_morning_time(self, chat_id: int) -> str:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.user_schedules.c.morning_time).where(self.user_schedules.c.chat_id == chat_id)
            ).scalar_one_or_none()
        return str(row) if row else "08:30"

    def list_subscribers_for_time(self, hhmm: str) -> dict[int, list[str]]:
        """Returns {chat_id: [tickers]} for users whose morning_time matches hhmm (or default 08:30)."""
        with self.engine.connect() as conn:
            wl_rows = conn.execute(
                select(self.user_watchlists.c.chat_id, self.user_watchlists.c.ticker)
                .order_by(self.user_watchlists.c.chat_id, self.user_watchlists.c.ticker)
            ).all()
            sched_rows = conn.execute(
                select(self.user_schedules.c.chat_id, self.user_schedules.c.morning_time)
            ).all()
        sched_map = {int(r.chat_id): str(r.morning_time) for r in sched_rows}
        out: dict[int, list[str]] = {}
        for r in wl_rows:
            cid = int(r.chat_id)
            if sched_map.get(cid, "08:30") == hhmm:
                out.setdefault(cid, []).append(str(r.ticker))
        return out

    def list_all_subscribers(self) -> dict[int, list[str]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self.user_watchlists.c.chat_id, self.user_watchlists.c.ticker)
                .order_by(self.user_watchlists.c.chat_id, self.user_watchlists.c.ticker)
            ).all()
        out: dict[int, list[str]] = {}
        for r in rows:
            out.setdefault(int(r.chat_id), []).append(str(r.ticker))
        return out

    def delete_user_data(self, chat_id: int) -> dict[str, int]:
        """Deletes all personal data (watchlist, schedule, alert_logs) for chat_id (/stop, UU PDP)."""
        with self.engine.begin() as conn:
            r_wl = conn.execute(delete(self.user_watchlists).where(self.user_watchlists.c.chat_id == chat_id))
            r_sc = conn.execute(delete(self.user_schedules).where(self.user_schedules.c.chat_id == chat_id))
            r_al = conn.execute(delete(self.alert_logs).where(self.alert_logs.c.chat_id == chat_id))
        return {
            "watchlists_deleted": r_wl.rowcount or 0,
            "schedules_deleted": r_sc.rowcount or 0,
            "alert_logs_deleted": r_al.rowcount or 0,
        }

    @staticmethod
    def build_delivery_key(chat_id: int, alert_date: date, alert_type: str, scope: str) -> str:
        return f"{chat_id}:{alert_date.isoformat()}:{alert_type}:{scope.upper()}"

    def has_delivered(self, delivery_key: str) -> bool:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.alert_logs.c.id).where(self.alert_logs.c.delivery_key == delivery_key)
            ).first()
        return row is not None

    def record_alert_delivery(
        self,
        delivery_key: str,
        chat_id: int | None,
        alert_date: date,
        alert_type: str,
        ticker: str,
        message_text: str,
        status: str = "SENT",
        error_detail: str | None = None,
    ) -> bool:
        """Idempotently records alert delivery; returns False if delivery_key already exists."""
        msg_hash = hashlib.sha256(message_text.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    self.alert_logs.insert().values(
                        delivery_key=delivery_key,
                        chat_id=chat_id,
                        alert_date=alert_date,
                        alert_type=alert_type,
                        ticker=ticker.upper(),
                        message_hash=msg_hash,
                        status=status,
                        error_detail=error_detail,
                        sent_at=now,
                    )
                )
            return True
        except IntegrityError:
            return False

    def upsert_daily_snapshot(
        self,
        snapshot_date: date,
        ticker: str,
        cash_status: str,
        flags: dict[str, Any],
        close_price: float | None,
        volume: int | None,
        news_items: list[dict[str, Any]],
        idx_announcements: list[dict[str, Any]],
    ) -> None:
        clean_t = ticker.strip().upper()
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            existing = conn.execute(
                select(self.daily_snapshot.c.id).where(
                    self.daily_snapshot.c.snapshot_date == snapshot_date,
                    self.daily_snapshot.c.ticker == clean_t,
                )
            ).first()
            payload = {
                "cash_status": cash_status,
                "flags_json": json.dumps(flags, ensure_ascii=False),
                "close_price": close_price,
                "volume": volume,
                "news_items_json": json.dumps(news_items, ensure_ascii=False),
                "idx_announcements_json": json.dumps(idx_announcements, ensure_ascii=False),
                "created_at": now,
            }
            if existing:
                conn.execute(
                    self.daily_snapshot.update()
                    .where(self.daily_snapshot.c.id == existing.id)
                    .values(**payload)
                )
            else:
                conn.execute(
                    self.daily_snapshot.insert().values(
                        snapshot_date=snapshot_date,
                        ticker=clean_t,
                        **payload,
                    )
                )

    def count_snapshots(self, snapshot_date: date) -> int:
        with self.engine.connect() as conn:
            cnt = conn.execute(
                select(func.count()).select_from(self.daily_snapshot).where(
                    self.daily_snapshot.c.snapshot_date == snapshot_date
                )
            ).scalar_one()
        return int(cnt or 0)

    def log_source_fetch(self, source_name: str, status: str, ticker: str | None = None, detail: str | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                self.source_fetch_logs.insert().values(
                    fetched_at=now,
                    source_name=source_name,
                    ticker=ticker,
                    status=status,
                    detail=detail,
                )
            )

    def record_analytics_event(self, event_name: str, ticker: str | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                self.bot_analytics_events.insert().values(
                    event_name=event_name,
                    ticker=ticker.upper() if ticker else None,
                    created_at=now,
                )
            )

    def count_analytics_events(self, event_name: str) -> int:
        with self.engine.connect() as conn:
            cnt = conn.execute(
                select(func.count()).select_from(self.bot_analytics_events).where(
                    self.bot_analytics_events.c.event_name == event_name
                )
            ).scalar_one()
        return int(cnt or 0)
