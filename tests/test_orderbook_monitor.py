"""Tests for Orderbook Wall & Big-Lot (low-freq) delta detector."""

from __future__ import annotations

from src.data.stockbit_feed import parse_orderbook_levels
from src.engine.orderbook_monitor import detect_orderbook_wall_deltas, format_orderbook_wall_alert


def test_detect_offer_wall_10k_lot_1_freq() -> None:
    prev_raw = {
        "data": {
            "bid": [{"price": "5675", "volume": "1343300", "que_num": "120"}],
            "offer": [{"price": "5700", "volume": "100000", "que_num": "10"}],
        }
    }
    curr_raw = {
        "data": {
            "bid": [{"price": "5675", "volume": "1343300", "que_num": "120"}],
            "offer": [{"price": "5700", "volume": "1100000", "que_num": "11"}],
        }
    }
    prev_ob = parse_orderbook_levels(prev_raw)
    curr_ob = parse_orderbook_levels(curr_raw)

    walls = detect_orderbook_wall_deltas(prev_ob, curr_ob, min_delta_lot=5000, max_delta_freq=2)
    assert len(walls) == 1
    w = walls[0]
    assert w["side"] == "OFFER"
    assert w["price"] == 5700
    assert w["delta_lot"] == 10000
    assert w["delta_freq"] == 1

    msg = format_orderbook_wall_alert("BBCA", w)
    assert "OFFER WALL" in msg
    assert "BBCA" in msg
    assert "5.700" in msg
    assert "+10.000 lot" in msg
    assert "+1" in msg
