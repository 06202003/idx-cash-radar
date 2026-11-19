"""Tests for Broker Flow Flip, Wall Pulled, and 1m Trade-Book HAKA/HAKI Dominance."""

from __future__ import annotations

from src.data.stockbit_feed import (
    parse_broker_distribution,
    parse_marketdetectors_summary,
    parse_orderbook_levels,
)
from src.engine.anomaly_detectors import (
    build_instant_signal_analysis,
    detect_broker_flow_anomaly,
    detect_tradebook_dominance,
    detect_wall_pulled,
    format_broker_flow_alert,
    format_tradebook_dominance_alert,
    format_wall_pulled_alert,
)


def test_detect_broker_distribution_to_retail() -> None:
    payload = {
        "data": {
            "bandar_detector": {"broker_accdist": "Dist", "total_buyer": 40, "total_seller": 12},
            "broker_summary": {
                "brokers_buy": [
                    {"netbs_broker_code": "XL", "bval": "8.0e+08", "blot": "1400", "type": "Lokal"},
                    {"netbs_broker_code": "YP", "bval": "6.0e+08", "blot": "1050", "type": "Asing"},
                ],
                "brokers_sell": [
                    {"netbs_broker_code": "AK", "sval": "-9.0e+08", "slot": "-1570", "type": "Asing"},
                    {"netbs_broker_code": "ZP", "sval": "-7.0e+08", "slot": "-1220", "type": "Asing"},
                ],
            },
        }
    }
    res = detect_broker_flow_anomaly("BBCA", payload, min_net_idr=500_000_000)
    assert res is not None
    assert res["signal"] == "DISTRIBUSI_KE_RITEL"
    assert res["foreign_net_idr"] == -1_000_000_000.0
    msg = format_broker_flow_alert(res)
    assert "DISTRIBUSI KE RITEL" in msg
    assert "AK, ZP" in msg
    assert "Asing Net" in msg

    summary = parse_marketdetectors_summary(payload)
    assert summary["top_sellers"][0]["code"] == "AK"
    assert summary["top_sellers"][0]["value_idr"] == 900_000_000.0
    assert summary["foreign_net_idr"] == -1_000_000_000.0


def test_parse_broker_distribution_crossing() -> None:
    payload = {
        "data": {
            "date_info": "2026-11-18",
            "by_value": {
                "top_broker_buy": [
                    {
                        "detail": {"code": "AK", "type": "Asing", "amount": 460849157500},
                        "distribute_to": [
                            {"code": "CC", "type": "Pemerintah", "amount": 165077422500},
                            {"code": "XL", "type": "Lokal", "amount": 36767665000},
                        ],
                    }
                ],
                "top_broker_sell": [
                    {
                        "detail": {"code": "CC", "type": "Pemerintah", "amount": 477260017500},
                        "distribute_to": [
                            {"code": "AK", "type": "Asing", "amount": 165077422500},
                        ],
                    }
                ],
            },
        }
    }
    parsed = parse_broker_distribution(payload)
    assert parsed["date_info"] == "2026-11-18"
    assert parsed["top_buyers"][0]["code"] == "AK"
    assert parsed["top_sellers"][0]["code"] == "CC"
    assert parsed["top_sellers"][0]["peers"][0]["code"] == "AK"


def test_detect_wall_pulled() -> None:
    prev_ob = parse_orderbook_levels({"data": {"offer": [{"price": "5700", "volume": "1200000", "que_num": "15"}]}})
    curr_ob = parse_orderbook_levels({"data": {"offer": [{"price": "5700", "volume": "200000", "que_num": "13"}]}})
    pulled = detect_wall_pulled(prev_ob, curr_ob, min_pulled_lot=5000, trade_lots={"buy_lot": 100, "sell_lot": 50})
    assert len(pulled) == 1
    assert pulled[0]["pulled_lot"] == 10000
    assert pulled[0]["eaten_by_trade"] is False
    msg = format_wall_pulled_alert("BBCA", pulled[0])
    assert "WALL DICABUT" in msg
    assert "5.700" in msg

    # If bid drop coincides with large HAKI (>= 40% of dropped lot), mark eaten_by_trade=True
    prev_bid = parse_orderbook_levels({"data": {"bid": [{"price": "3050", "volume": "1500000", "que_num": "189"}]}})
    curr_bid = parse_orderbook_levels({"data": {"bid": [{"price": "3050", "volume": "335800", "que_num": "83"}]}})
    eaten = detect_wall_pulled(prev_bid, curr_bid, min_pulled_lot=5000, trade_lots={"buy_lot": 200, "sell_lot": 12000})
    assert len(eaten) == 1
    assert eaten[0]["eaten_by_trade"] is True


def test_detect_tradebook_haki_dominance_and_noise_filter() -> None:
    # Noise under Rp100jt in 1-minute cumulative delta should be ignored
    noise_payload = {
        "data": {
            "buy": [
                {"time": "09:00", "lot": {"raw": "100"}, "value": {"raw": "1000000000"}},
                {"time": "09:01", "lot": {"raw": "102"}, "value": {"raw": "1010000000"}},
            ],
            "sell": [
                {"time": "09:00", "lot": {"raw": "200"}, "value": {"raw": "2000000000"}},
                {"time": "09:01", "lot": {"raw": "210"}, "value": {"raw": "2050000000"}},
            ],
        }
    }
    assert detect_tradebook_dominance("BBCA", noise_payload) is None

    # Real >Rp100jt HAKI dominance in 1-minute cumulative delta
    real_payload = {
        "data": {
            "buy": [
                {"time": "13:39", "lot": {"raw": "450000"}, "value": {"raw": "258000000000"}},
                {"time": "13:40", "lot": {"raw": "450090"}, "value": {"raw": "258050000000"}},
            ],
            "sell": [
                {"time": "13:39", "lot": {"raw": "337000"}, "value": {"raw": "191000000000"}},
                {"time": "13:40", "lot": {"raw": "337450"}, "value": {"raw": "191250000000"}},
            ],
        }
    }
    res = detect_tradebook_dominance("BBCA", real_payload)
    assert res is not None
    assert res["side"] == "HAKI"
    assert res["dominance_pct"] >= 80.0
    assert res["time"] == "13:40"
    assert res["sell_lot"] == 450
    msg = format_tradebook_dominance_alert(res)
    assert "HAKI DOMINAN 1M" in msg
    assert "13:40 WIB" in msg


def test_build_instant_signal_analysis_context() -> None:
    ob = parse_orderbook_levels({
        "data": {
            "bid": [{"price": "3050", "volume": "1500000", "que_num": "120"}],
            "offer": [{"price": "3060", "volume": "3000000", "que_num": "200"}],
        }
    })
    md = {
        "data": {
            "bandar_detector": {"broker_accdist": "Dist"},
            "broker_summary": {
                "brokers_buy": [{"netbs_broker_code": "YP", "bval": "9.0e+08", "type": "Lokal"}],
                "brokers_sell": [{"netbs_broker_code": "AK", "sval": "-1.2e+09", "type": "Asing"}],
            },
        }
    }
    haka_ctx = build_instant_signal_analysis("BBRI", "HAKA", curr_ob=ob, md_raw=md)
    assert "Waspada Pantulan Sesaat" in haka_ctx
    assert "Offer lebih tebal" in haka_ctx

    haki_ctx = build_instant_signal_analysis("BBRI", "HAKI", curr_ob=ob, md_raw=md)
    assert "Tekanan Searah" in haki_ctx
