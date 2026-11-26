"""Yahoo Finance (.JK) OHLCV market data fetcher with safe numeric parsing."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pandas as pd


def parse_safe_float(val: Any) -> float | None:
    """Safely parses numeric strings (including comma-formatted thousands) into float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if pd.notna(val) else None
    s = str(val).strip().replace(",", "")
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_jk_ohlcv(ticker: str, range_str: str = "2y", timeout: float = 10.0) -> pd.DataFrame:
    """
    Fetches daily OHLCV bars for an IDX ticker (<TICKER>.JK) or index (^...) from Yahoo Finance chart API.
    Returns DataFrame with columns: date, open, high, low, close, volume.
    """
    raw_t = ticker.strip().upper()
    if raw_t.startswith("^"):
        symbol = urllib.parse.quote(raw_t)
    else:
        clean_t = raw_t.replace(".JK", "")
        symbol = urllib.parse.quote(f"{clean_t}.JK")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; IDXAlertBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        o = parse_safe_float(opens[i] if i < len(opens) else None)
        h = parse_safe_float(highs[i] if i < len(highs) else None)
        l = parse_safe_float(lows[i] if i < len(lows) else None)
        c = parse_safe_float(closes[i] if i < len(closes) else None)
        v = parse_safe_float(volumes[i] if i < len(volumes) else 0.0) or 0.0
        if None in (o, h, l, c) or c <= 0:
            continue
        dt_str = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
        rows.append({
            "date": dt_str,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


def fetch_jk_intraday(
    ticker: str,
    interval: str = "5m",
    range_str: str = "1d",
    timeout: float = 10.0,
) -> pd.DataFrame:
    """
    Fetches intraday OHLCV bars for an IDX ticker (<TICKER>.JK) from Yahoo Finance chart API.
    Timestamps are converted to WIB (UTC+7) formatted as 'YYYY-MM-DD HH:MM'.
    """
    raw_t = ticker.strip().upper()
    if raw_t.startswith("^"):
        symbol = urllib.parse.quote(raw_t)
    else:
        clean_t = raw_t.replace(".JK", "")
        symbol = urllib.parse.quote(f"{clean_t}.JK")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval={interval}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; IDXAlertBot/1.0)"},
    )
    empty_df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return empty_df

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return empty_df

    chart = result[0]
    meta = chart.get("meta") or {}
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    wib = timezone(timedelta(hours=7))
    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        c = parse_safe_float(closes[i] if i < len(closes) else None)
        if c is None or c <= 0:
            continue
        o = parse_safe_float(opens[i] if i < len(opens) else None) or c
        h = parse_safe_float(highs[i] if i < len(highs) else None) or c
        l = parse_safe_float(lows[i] if i < len(lows) else None) or c
        v = parse_safe_float(volumes[i] if i < len(volumes) else 0.0) or 0.0
        dt_str = datetime.fromtimestamp(ts, tz=wib).strftime("%Y-%m-%d %H:%M")
        rows.append({
            "date": dt_str,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return empty_df
    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    prev_close = parse_safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
    if prev_close is not None and prev_close > 0:
        df.attrs["previous_close"] = prev_close
    return df
