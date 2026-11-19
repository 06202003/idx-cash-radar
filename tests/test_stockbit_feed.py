"""Tests for Stockbit Bearer JWT manager and marketdetectors broker summary parser."""

from __future__ import annotations

import base64
import json
import time

from src.data.stockbit_feed import parse_marketdetectors_summary
from src.data.stockbit_token_manager import decode_jwt_expiry, get_token_remaining_seconds


def _make_dummy_jwt(exp_ts: int) -> str:
    hdr = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode("ascii")
    pay = base64.urlsafe_b64encode(json.dumps({"exp": exp_ts}).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"{hdr}.{pay}.sig"


def test_jwt_expiry_decoding() -> None:
    future_exp = int(time.time()) + 3600
    tok = _make_dummy_jwt(future_exp)
    assert decode_jwt_expiry(f"Bearer {tok}") == future_exp
    rem = get_token_remaining_seconds(tok)
    assert rem is not None and 3500 <= rem <= 3605


def test_parse_marketdetectors_summary() -> None:
    sample_payload = {
        "data": {
            "bandar_detector": {"broker_accdist": "Acc"},
            "broker_summary": {
                "brokers_buy": [
                    {"netbs_broker_code": "AK", "bval": 120_000_000_000, "blot": 200000},
                    {"netbs_broker_code": "ZP", "bval": 80_000_000_000, "blot": 140000},
                ],
                "brokers_sell": [
                    {"netbs_broker_code": "YP", "bval": -95_000_000_000, "blot": -160000},
                ],
            },
        }
    }
    res = parse_marketdetectors_summary(sample_payload)
    assert res["bandar_action"] == "Acc"
    assert res["buyer_codes"] == ["AK", "ZP"]
    assert res["seller_codes"] == ["YP"]
