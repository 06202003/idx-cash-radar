"""
Automated tests for Fase 8 Telegram Bot (briefing, language compliance, IDX holiday calendar,
idempotent delivery, unknown ticker analytics, /stop UU PDP deletion, and canonical_facts parity).
"""

from __future__ import annotations

import asyncio
import random
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.briefing import (
    capture_universe_daily_snapshot,
    format_event_alert,
    format_volume_alert,
    format_watchlist_briefing_item,
    list_universe_tickers,
    load_canonical_ticker_record,
)
from src.bot.idx_calendar import WIB, is_idx_trading_day
from src.bot.pg_store import MAX_WATCHLIST_TICKERS, BotStateStore
from src.bot.worker import (
    build_about_text,
    build_briefing_message_for_user,
    create_fase8_router,
    format_unknown_ticker_message,
    run_scheduler_tick,
)
from src.db.repository import FinancialRepository
from src.renderer.formatter import format_idr_nominal
from tests.test_language_compliance import BLACKLISTED_WORDS


def _make_test_store() -> BotStateStore:
    return BotStateStore("sqlite:///:memory:", allow_sqlite_for_tests=True)


def test_production_rejects_sqlite_url() -> None:
    with pytest.raises(RuntimeError, match="SQLite dilarang"):
        BotStateStore("sqlite:///prod.db")


def test_briefing_and_alerts_no_blacklisted_words_and_no_sentiment_labels() -> None:
    repo = FinancialRepository()
    rec = load_canonical_ticker_record("WIKA", repo)
    assert rec is not None

    market = {"close_price": 200.0, "change_1d_pct": -1.5, "volume": 1000000, "vol_ratio_20d": 3.4}
    news = [{
        "title": "WIKA Laksanakan RUPO Berkelanjutan",
        "media": "Kontan",
        "url": "https://example.com/wika",
        "published_at": "18 Nov 2026",
    }]

    msg = format_watchlist_briefing_item(rec, market=market, news=news)
    vol_msg = format_volume_alert("WIKA", 3.4)
    ev_msg = format_event_alert("WIKA", {
        "event_type": "SUSPENSI",
        "title": "Pengumuman Suspensi Efek",
        "source": "BEI",
        "published_at": "18 Nov 2026",
        "url": "https://idx.co.id/dummy",
    })
    about_msg = build_about_text()

    combined = "\n".join([msg, vol_msg, ev_msg, about_msg]).lower()
    for bad in BLACKLISTED_WORDS:
        assert bad not in combined, f"Blacklisted word found: {bad}"

    import re
    # No RSI/MA conclusions, no sentiment labels, and report date is present
    assert re.search(r"\brsi\b", combined) is None
    assert re.search(r"\bma20\b", combined) is None
    assert "positif" not in combined
    assert "perhatian" not in combined
    assert "netral" not in combined
    assert "tanggal laporan:" in combined
    assert "volume 3,4x rata-rata 20 hari, data tertunda ±5-15 menit" in vol_msg.lower()


def test_canonical_facts_match_10_random_tickers() -> None:
    repo = FinancialRepository()
    universe = list_universe_tickers(repo)
    assert len(universe) >= 10

    rng = random.Random(42)
    sample = rng.sample(universe, 10)
    for t in sample:
        rec = load_canonical_ticker_record(t, repo)
        assert rec is not None, f"Missing canonical record for {t}"
        msg = format_watchlist_briefing_item(rec)

        assert rec["period_end_date"] in msg
        assert format_idr_nominal(Decimal(rec["cash_idr"])) in msg
        assert format_idr_nominal(Decimal(rec["st_debt_idr"])) in msg
        assert format_idr_nominal(Decimal(rec["cfo_ttm_idr"])) in msg
        assert format_idr_nominal(Decimal(rec["net_income_ttm_idr"])) in msg


def test_idx_holiday_calendar_and_scheduler_skip() -> None:
    assert is_idx_trading_day(date(2026, 8, 17)) is False  # Independence Day
    assert is_idx_trading_day(date(2026, 12, 25)) is False  # Christmas
    assert is_idx_trading_day(date(2026, 11, 21)) is False  # Saturday
    assert is_idx_trading_day(date(2026, 11, 19)) is True   # Thursday trading day

    store = _make_test_store()
    repo = FinancialRepository()
    store.add_watch(1001, "WIKA")

    bot = MagicMock()
    bot.send_message = AsyncMock()

    holiday_dt = datetime(2026, 8, 17, 8, 30, tzinfo=WIB)
    res = asyncio.run(run_scheduler_tick(bot, store, repo, now_dt=holiday_dt, fetch_external=False))
    assert res["skipped_holiday"] == 1
    assert res["morning_sent"] == 0
    bot.send_message.assert_not_called()


def test_idempotent_delivery_and_custom_schedule() -> None:
    store = _make_test_store()
    repo = FinancialRepository()
    store.add_watch(2002, "TOTL")
    assert store.set_morning_time(2002, "08:15") is True

    bot = MagicMock()
    bot.send_message = AsyncMock()
    trading_dt = datetime(2026, 11, 19, 8, 15, tzinfo=WIB)

    r1 = asyncio.run(run_scheduler_tick(bot, store, repo, now_dt=trading_dt, fetch_external=False))
    r2 = asyncio.run(run_scheduler_tick(bot, store, repo, now_dt=trading_dt, fetch_external=False))
    assert r1["morning_sent"] == 1
    assert r2["morning_sent"] == 0
    assert bot.send_message.call_count == 1


def test_max_20_tickers_limit_and_unknown_ticker_event() -> None:
    store = _make_test_store()
    repo = FinancialRepository()
    universe = list_universe_tickers(repo)
    for t in universe[:MAX_WATCHLIST_TICKERS]:
        ok, _ = store.add_watch(3003, t)
        assert ok is True
    ok_extra, msg_extra = store.add_watch(3003, universe[MAX_WATCHLIST_TICKERS])
    assert ok_extra is False
    assert "20" in msg_extra

    # Unknown ticker message + analytics
    unknown_msg = format_unknown_ticker_message("ZZZZ")
    assert "belum ada di data kami" in unknown_msg.lower()
    store.record_analytics_event("ticker_tidak_ditemukan", "ZZZZ")
    assert store.count_analytics_events("ticker_tidak_ditemukan") == 1


def test_stop_deletes_all_user_data() -> None:
    store = _make_test_store()
    store.add_watch(4004, "WIKA")
    store.set_morning_time(4004, "08:45")
    store.record_alert_delivery(
        delivery_key="4004:2026-11-19:morning_briefing:08:45",
        chat_id=4004,
        alert_date=date(2026, 11, 19),
        alert_type="morning_briefing",
        ticker="WATCHLIST",
        message_text="test",
    )

    deleted = store.delete_user_data(4004)
    assert deleted["watchlists_deleted"] == 1
    assert deleted["schedules_deleted"] == 1
    assert deleted["alert_logs_deleted"] == 1
    assert store.list_watch(4004) == []


def test_daily_snapshot_captures_entire_universe() -> None:
    store = _make_test_store()
    repo = FinancialRepository()
    snap_date = date(2026, 11, 19)
    cnt = capture_universe_daily_snapshot(store, repo, snapshot_date=snap_date, fetch_external=False)
    assert cnt == len(list_universe_tickers(repo))
    assert store.count_snapshots(snap_date) == cnt


def test_forward_to_check_url_and_ticker_extraction() -> None:
    from src.bot.worker import extract_url_or_ticker

    universe = {"ADRO", "BBRI", "TLKM", "WIKA"}
    u, t = extract_url_or_ticker("Cek berita ini https://kontan.co.id/news/adro-2026 ya", universe=universe)
    assert u == "https://kontan.co.id/news/adro-2026"
    assert t is None

    u2, t2 = extract_url_or_ticker("Menurut kalian saham TLKM gimana?", universe=universe)
    assert u2 is None
    assert t2 == "TLKM"


def test_group_cooldown_anti_spam() -> None:
    store = _make_test_store()
    assert store.check_and_set_group_cooldown(-100123, "TLKM", cooldown_seconds=60.0, now_ts=1000.0) is True
    assert store.check_and_set_group_cooldown(-100123, "TLKM", cooldown_seconds=60.0, now_ts=1025.0) is False
    assert store.check_and_set_group_cooldown(-100123, "TLKM", cooldown_seconds=60.0, now_ts=1065.0) is True
    assert store.check_and_set_group_cooldown(-100123, "BBRI", cooldown_seconds=60.0, now_ts=1025.0) is True


def test_filing_change_alert_detection_and_formatting() -> None:
    from src.bot.briefing import detect_filing_change_for_ticker, format_filing_change_alert

    store = _make_test_store()
    repo = FinancialRepository()
    # Seed older filing as last seen for WIKA so the newest filing triggers a change alert
    with repo.get_connection() as conn:
        rows = conn.execute(
            "SELECT filing_id FROM filings WHERE ticker = 'WIKA' ORDER BY fiscal_year DESC, period_end_date DESC LIMIT 2"
        ).fetchall()
    if len(rows) < 2:
        return

    store.set_last_seen_filing("WIKA", str(rows[1]["filing_id"]))
    change = detect_filing_change_for_ticker("WIKA", store, repo)
    assert change is not None
    assert change["new_filing_id"] == str(rows[0]["filing_id"])

    msg = format_filing_change_alert(change)
    assert "WIKA" in msg
    assert change["new_period_end_date"] in msg
    assert "Arus kas operasi 12 bulan" in msg
    low = msg.lower()
    for bad in BLACKLISTED_WORDS:
        assert bad not in low


def test_north_star_4_metrics() -> None:
    from datetime import timedelta

    store = _make_test_store()
    now = datetime(2026, 11, 19, 10, 0, tzinfo=WIB)
    store.record_analytics_event("bot_start")
    store.record_analytics_event("bot_start")
    store.add_watch(5001, "TLKM")
    store.touch_user(5001, seen_at=now - timedelta(days=7))
    store.touch_user(5001, seen_at=now)
    store.record_analytics_event("kartu_dibagikan", "TLKM")

    metrics = store.get_north_star_metrics()
    assert metrics["total_start"] == 2
    assert metrics["activated_users"] == 1
    assert metrics["d7_retained_users"] == 1
    assert metrics["cards_shared_to_group"] == 1
