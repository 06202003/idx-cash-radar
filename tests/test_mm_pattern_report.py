"""Tests for human-readable /pola MM pattern report & short analysis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.db.store import WIB, AlertStore


def _dt(h: int, m: int, s: int) -> datetime:
    return datetime(2026, 11, 23, h, m, s, tzinfo=WIB)


def test_format_mm_pattern_report_bearish_advice(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "test_mm.db")
    day = "2026-11-23"

    store.log_mm_event("VKTR", "HAKI_1M", side="HAKI", lot_delta=-4141, value_idr=124_000_000, detail="99.6% (11:27)", now_wib=_dt(11, 27, 31))
    store.log_mm_event("VKTR", "HAKI_1M", side="HAKI", lot_delta=-2000, value_idr=60_000_000, detail="90.0% (11:30)", now_wib=_dt(11, 30, 0))
    store.log_mm_event("VKTR", "WALL_EATEN", side="BID", price=296, lot_delta=-8705, detail="Dimakan HAKI/HAKA", now_wib=_dt(11, 33, 20))
    store.log_mm_event("VKTR", "BROKER_FLIP", side="DISTRIBUSI_KE_RITEL", value_idr=4_060_000_000, detail="Non-Ritel: KI,AZ,YU", now_wib=_dt(11, 33, 23))
    store.log_mm_event("VKTR", "WALL_ADDED", side="OFFER", price=302, lot_delta=6098, now_wib=_dt(11, 39, 41))
    store.log_mm_event("VKTR", "WALL_PULLED", side="OFFER", price=302, lot_delta=-6718, now_wib=_dt(11, 40, 25))
    store.log_mm_event("VKTR", "WALL_ADDED", side="BID", price=296, lot_delta=5390, now_wib=_dt(11, 43, 57))

    report = store.format_mm_pattern_report("VKTR", day_wib=day)

    assert "Dominan Jual" in report
    assert "Distribusi ke ritel" in report
    assert "Bid dijaga @296" in report
    assert "Offer @302 dicabut" in report
    assert "Jangan buy/kejar dulu" in report
    assert "_" not in report


def test_format_mm_pattern_report_bullish_advice(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "test_mm_bull.db")
    day = "2026-11-23"

    store.log_mm_event("BBCA", "HAKA_1M", side="HAKA", lot_delta=3000, value_idr=200_000_000, detail="88.0% (10:15)", now_wib=_dt(10, 15, 0))
    store.log_mm_event("BBCA", "HAKA_1M", side="HAKA", lot_delta=2500, value_idr=180_000_000, detail="92.0% (10:20)", now_wib=_dt(10, 20, 0))
    store.log_mm_event("BBCA", "BROKER_FLIP", side="SERAPAN_NON_RITEL", value_idr=1_500_000_000, detail="Non-Ritel: BK,AK,ZP", now_wib=_dt(10, 25, 0))

    report = store.format_mm_pattern_report("BBCA", day_wib=day)

    assert "Dominan Beli" in report
    assert "Jangan buru-buru sell" in report
    assert "_" not in report
