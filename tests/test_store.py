"""Tests for SQLite AlertStore (watchlists and alert_logs)."""

from __future__ import annotations

from pathlib import Path

from src.db.store import AlertStore


def test_watchlist_and_logging(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "test_alerts.db")
    store.add_watch(12345, "adro.jk")
    store.add_watch(12345, "BBRI")
    assert store.list_watch(12345) == ["ADRO", "BBRI"]

    assert store.remove_watch(12345, "ADRO") is True
    assert store.list_watch(12345) == ["BBRI"]

    store.log_alert(
        ticker="BBRI",
        alert_type="morning",
        price_close=4850.0,
        p_up_pct=62.5,
        composite_score=67.5,
        badge="🟢 SENTIMEN NAIK",
        news_sentiment="POSITIF",
        chat_id=12345,
    )
    assert store.count_logs() == 1


def test_mm_event_recording_and_pattern_report(tmp_path: Path) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    store = AlertStore(db_path=tmp_path / "test_mm.db")
    dt = datetime(2026, 11, 19, 14, 45, 23, tzinfo=ZoneInfo("Asia/Jakarta"))
    store.log_mm_event("BBRI", "WALL_ADDED", side="BID", price=3050, lot_delta=10000, freq_delta=1, now_wib=dt)
    store.log_mm_event("BBRI", "WALL_EATEN", side="BID", price=3050, lot_delta=-11642, freq_delta=-106, detail="Dimakan HAKI/HAKA", now_wib=dt)
    store.log_mm_event("BBRI", "HAKI_1M", side="HAKI", lot_delta=-13000, value_idr=4_021_000_000, detail="93.7%", now_wib=dt)

    events = store.get_mm_events("BBRI", day_wib="2026-11-19")
    assert len(events) == 3
    report = store.format_mm_pattern_report("BBRI", day_wib="2026-11-19")
    assert "REKAMAN POLA MARKET MAKER | BBRI" in report
    assert "Wall Dipasang: `1x`" in report
    assert "Dimakan HAKA/HAKI: `1x`" in report
    assert "14:45:23" in report
