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
