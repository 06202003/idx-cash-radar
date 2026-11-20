"""Real-time Stockbit Exodus API client (marketdetectors broker summary, daily & intraday price)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from src.data.market_feed import parse_safe_float
from src.data.stockbit_token_manager import load_active_token


class StockbitAuthError(RuntimeError):
    """Raised when Stockbit returns 401/403 (Bearer token expired or invalid)."""


def _build_headers(token: str) -> dict[str, str]:
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "origin": "https://stockbit.com",
        "referer": "https://stockbit.com/",
        "x-platform": "web",
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Edg/157.0.0.0 Mobile Safari/537.36"
        ),
    }


def _get_json(url: str, token: str, timeout: float = 8.0) -> dict[str, Any]:
    if not token:
        raise StockbitAuthError("STOCKBIT_BEARER_TOKEN belum tersedia.")
    req = urllib.request.Request(url, headers=_build_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise StockbitAuthError(f"Stockbit HTTP {exc.code}: token expired atau tidak valid") from exc
        raise


def fetch_stockbit_daily(ticker: str, token: str | None = None, timeframe: str = "today") -> dict[str, Any]:
    """Calls https://exodus.stockbit.com/charts/{TICKER}/daily?timeframe={timeframe}."""
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = f"https://exodus.stockbit.com/charts/{urllib.parse.quote(clean_t)}/daily?timeframe={urllib.parse.quote(timeframe)}"
    return _get_json(url, tok)


def fetch_stockbit_intraday(
    ticker: str,
    token: str | None = None,
    lookback_days: int = 5,
) -> pd.DataFrame:
    """
    Calls https://exodus.stockbit.com/chartbit/{TICKER}/price/intraday
    and returns DataFrame of intraday price bars.
    """
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    now_ts = int(time.time())
    from_ts = now_ts - (lookback_days * 86400)
    url = (
        f"https://exodus.stockbit.com/chartbit/{urllib.parse.quote(clean_t)}/price/intraday"
        f"?from={now_ts}&to={from_ts}&limit=0"
    )
    payload = _get_json(url, tok)
    data_block = payload.get("data") or {}
    bars = data_block.get("chartbit") or data_block.get("prices") or []
    rows: list[dict[str, Any]] = []
    for b in bars:
        c = parse_safe_float(b.get("close") or b.get("value"))
        if c is None or c <= 0:
            continue
        rows.append({
            "date": str(b.get("date") or b.get("unixdate") or ""),
            "open": parse_safe_float(b.get("open")) or c,
            "high": parse_safe_float(b.get("high")) or c,
            "low": parse_safe_float(b.get("low")) or c,
            "close": c,
            "volume": parse_safe_float(b.get("volume")) or 0.0,
        })
    return pd.DataFrame(rows)


def parse_marketdetectors_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Extracts Top Net Buyers, Top Net Sellers, foreign net flow, and bandar summary from marketdetectors JSON."""
    data = payload.get("data") or {}
    bandar = data.get("bandar_detector") or {}
    broksum = data.get("broker_summary") or {}

    buyers_raw = broksum.get("brokers_buy") or []
    sellers_raw = broksum.get("brokers_sell") or []

    def _fmt_broker(b: dict[str, Any], side: str) -> dict[str, Any]:
        code = str(b.get("netbs_broker_code") or b.get("broker_code") or "?")
        if side == "sell":
            raw_val = b.get("sval") if b.get("sval") is not None else b.get("bval")
            raw_lot = b.get("slot") if b.get("slot") is not None else b.get("blot")
            avg_price = parse_safe_float(b.get("netbs_sell_avg_price"))
        else:
            raw_val = b.get("bval")
            raw_lot = b.get("blot")
            avg_price = parse_safe_float(b.get("netbs_buy_avg_price"))
        val = parse_safe_float(raw_val) or 0.0
        lot = parse_safe_float(raw_lot) or 0.0
        return {
            "code": code,
            "type": str(b.get("type") or ""),
            "value_idr": abs(val),
            "lot": abs(lot),
            "avg_price": avg_price,
        }

    top_buyers = [_fmt_broker(b, "buy") for b in buyers_raw[:3]]
    top_sellers = [_fmt_broker(s, "sell") for s in sellers_raw[:3]]

    foreign_buy = sum(
        abs(parse_safe_float(b.get("bval")) or 0.0)
        for b in buyers_raw
        if str(b.get("type") or "").lower() == "asing"
    )
    foreign_sell = sum(
        abs(parse_safe_float(s.get("sval") if s.get("sval") is not None else s.get("bval")) or 0.0)
        for s in sellers_raw
        if str(s.get("type") or "").lower() == "asing"
    )

    return {
        "bandar_action": bandar.get("broker_accdist") or bandar.get("top3_accdist") or "-",
        "total_buyer": bandar.get("total_buyer"),
        "total_seller": bandar.get("total_seller"),
        "foreign_net_idr": foreign_buy - foreign_sell,
        "top_buyers": top_buyers,
        "top_sellers": top_sellers,
        "buyer_codes": [b["code"] for b in top_buyers],
        "seller_codes": [s["code"] for s in top_sellers],
    }


def parse_broker_distribution(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Parses Stockbit /order-trade/broker/distribution JSON to show top buyer & seller
    crossing networks (who distributed to whom).
    """
    data = payload.get("data") or {}
    by_val = data.get("by_value") or {}

    def _extract_side(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for entry in items[:3]:
            detail = entry.get("detail") or {}
            peers = [
                {
                    "code": str(p.get("code") or "?"),
                    "type": str(p.get("type") or ""),
                    "amount_idr": abs(parse_safe_float(p.get("amount")) or 0.0),
                }
                for p in (entry.get("distribute_to") or [])[:3]
            ]
            out.append({
                "code": str(detail.get("code") or "?"),
                "type": str(detail.get("type") or ""),
                "amount_idr": abs(parse_safe_float(detail.get("amount")) or 0.0),
                "peers": peers,
            })
        return out

    return {
        "date_info": str(data.get("date_info") or ""),
        "top_buyers": _extract_side(by_val.get("top_broker_buy") or []),
        "top_sellers": _extract_side(by_val.get("top_broker_sell") or []),
    }


def fetch_stockbit_broker_distribution(ticker: str, token: str | None = None) -> dict[str, Any]:
    """Calls https://exodus.stockbit.com/order-trade/broker/distribution for latest 1-day crossing map."""
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = (
        "https://exodus.stockbit.com/order-trade/broker/distribution"
        f"?date=&symbol={urllib.parse.quote(clean_t)}"
        "&investor_type=INVESTOR_TYPE_ALL&market_board=MARKET_TYPE_REGULER"
        "&data_type=BROKER_DISTRIBUTION_DATA_TYPE_VALUE&period=TB_PERIOD_LAST_1_DAY"
    )
    payload = _get_json(url, tok)
    return parse_broker_distribution(payload)


def fetch_stockbit_broker_summary(ticker: str, token: str | None = None) -> dict[str, Any]:
    """Calls https://exodus.stockbit.com/marketdetectors/{TICKER} for latest regular net broker summary."""
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = (
        f"https://exodus.stockbit.com/marketdetectors/{urllib.parse.quote(clean_t)}"
        "?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER"
        "&investor_type=INVESTOR_TYPE_ALL&limit=25&period=BROKER_SUMMARY_PERIOD_LATEST"
    )
    payload = _get_json(url, tok)
    return parse_marketdetectors_summary(payload)


def fetch_stockbit_trade_book(
    ticker: str,
    token: str | None = None,
    time_interval: str = "1m",
) -> dict[str, Any]:
    """Calls https://exodus.stockbit.com/order-trade/trade-book/chart?symbol={TICKER}&time_interval=1m."""
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = (
        f"https://exodus.stockbit.com/order-trade/trade-book/chart"
        f"?symbol={urllib.parse.quote(clean_t)}&time_interval={urllib.parse.quote(time_interval)}"
    )
    return _get_json(url, tok)


def parse_orderbook_levels(payload: dict[str, Any]) -> dict[str, dict[int, dict[str, int]]]:
    """
    Normalizes Stockbit orderbook JSON into {'bid': {price: {'lot': int, 'freq': int}}, 'offer': {...}}.
    """
    data = payload.get("data") or payload
    out: dict[str, dict[int, dict[str, int]]] = {"bid": {}, "offer": {}}

    for side_out, keys in (("bid", ("bid", "bids")), ("offer", ("offer", "offers", "ask", "asks"))):
        raw_list: list[dict[str, Any]] = []
        for k in keys:
            if isinstance(data.get(k), list):
                raw_list = data[k]
                break
        for row in raw_list:
            price = parse_safe_float(row.get("price"))
            if row.get("lot") is not None:
                lot = parse_safe_float(row.get("lot")) or 0.0
            else:
                shares = parse_safe_float(row.get("volume") or row.get("vol")) or 0.0
                lot = shares / 100.0
            freq = parse_safe_float(row.get("que_num") or row.get("freq") or row.get("count")) or 0.0
            if price is not None and price > 0:
                out[side_out][int(round(price))] = {"lot": int(round(lot)), "freq": int(round(freq))}
    return out


def fetch_stockbit_orderbook(ticker: str, token: str | None = None) -> dict[str, dict[int, dict[str, int]]]:
    """Calls Stockbit v2 orderbook endpoint and returns normalized bid/offer levels."""
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = f"https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{urllib.parse.quote(clean_t)}"
    payload = _get_json(url, tok)
    return parse_orderbook_levels(payload)


def parse_marketdetectors_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extracts all net buyers and net sellers from marketdetectors JSON as signed rows."""
    data = payload.get("data") or {}
    broksum = data.get("broker_summary") or {}
    buyers_raw = broksum.get("brokers_buy") or []
    sellers_raw = broksum.get("brokers_sell") or []
    rows: list[dict[str, Any]] = []

    for b in buyers_raw:
        code = str(b.get("netbs_broker_code") or b.get("broker_code") or "").strip().upper()
        if not code or code == "?":
            continue
        val = abs(parse_safe_float(b.get("bval")) or 0.0)
        lot = int(round(abs(parse_safe_float(b.get("blot")) or 0.0)))
        avg_px = parse_safe_float(b.get("netbs_buy_avg_price"))
        rows.append({
            "broker_code": code,
            "broker_type": str(b.get("type") or ""),
            "side": "BUY",
            "net_val_idr": val,
            "net_lot": lot,
            "avg_price": avg_px,
        })

    for s in sellers_raw:
        code = str(s.get("netbs_broker_code") or s.get("broker_code") or "").strip().upper()
        if not code or code == "?":
            continue
        raw_val = s.get("sval") if s.get("sval") is not None else s.get("bval")
        raw_lot = s.get("slot") if s.get("slot") is not None else s.get("blot")
        val = abs(parse_safe_float(raw_val) or 0.0)
        lot = int(round(abs(parse_safe_float(raw_lot) or 0.0)))
        avg_px = parse_safe_float(s.get("netbs_sell_avg_price"))
        rows.append({
            "broker_code": code,
            "broker_type": str(s.get("type") or ""),
            "side": "SELL",
            "net_val_idr": -val,
            "net_lot": -lot,
            "avg_price": avg_px,
        })

    return rows


def fetch_stockbit_broker_summary_for_date(
    ticker: str,
    day_str: str,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """Fetches net broker summary rows for a specific YYYY-MM-DD trading date."""
    tok = token or load_active_token()
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = (
        f"https://exodus.stockbit.com/marketdetectors/{urllib.parse.quote(clean_t)}"
        f"?from={urllib.parse.quote(day_str)}&to={urllib.parse.quote(day_str)}"
        "&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER"
        "&investor_type=INVESTOR_TYPE_ALL&limit=25"
    )
    payload = _get_json(url, tok)
    return parse_marketdetectors_rows(payload)


def backfill_broker_history(
    store: Any,
    ticker: str,
    lookback_weekdays: int = 15,
    token: str | None = None,
) -> int:
    """Fetches missing recent weekdays of broker summary into store. Returns count of days saved."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tok = token or load_active_token()
    if not tok:
        return 0

    wib = ZoneInfo("Asia/Jakarta")
    today = datetime.now(wib).date()
    existing = set(store.list_broker_history_days(ticker, lookback_days=lookback_weekdays + 15))
    saved_days = 0
    checked = 0
    cursor = today - timedelta(days=1)  # Start from yesterday (most recent completed day)

    while checked < lookback_weekdays:
        if cursor.weekday() < 5:
            day_str = cursor.strftime("%Y-%m-%d")
            checked += 1
            if day_str not in existing:
                try:
                    rows = fetch_stockbit_broker_summary_for_date(ticker, day_str, token=tok)
                    if rows:
                        store.upsert_broker_daily(day_str, ticker, rows)
                        saved_days += 1
                except StockbitAuthError:
                    break
                except Exception:
                    pass
        cursor -= timedelta(days=1)

    return saved_days
