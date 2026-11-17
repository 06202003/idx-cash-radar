"""
Lightweight Real-Time IDX Stock Quote Fetcher (.JK via Yahoo Finance v8 Chart API).
Uses only Python standard library with parallel ThreadPoolExecutor and 5-minute TTL cache
to stay fast and serverless-friendly (Vercel) with zero extra dependencies.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

_CACHE_LOCK = threading.Lock()
_QUOTE_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
DEFAULT_TTL_SECONDS = 300  # 5 minutes


def fetch_single_quote(
    ticker: str,
    timeout: float = 5.0,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any] | None:
    """Fetches a single IDX stock quote (<TICKER>.JK) with in-memory TTL cache."""
    clean = ticker.strip().upper()
    if not clean or len(clean) > 6:
        return None

    now = time.time()
    with _CACHE_LOCK:
        cached = _QUOTE_CACHE.get(clean)
        if cached and (now - cached[0]) < ttl_seconds:
            return cached[1]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}.JK?interval=1d&range=2d"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )

    quote: dict[str, Any] | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        results = (payload.get("chart") or {}).get("result") or []
        if results:
            meta = results[0].get("meta") or {}
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is not None:
                price_f = float(price)
                prev_f = float(prev_close) if prev_close is not None else price_f
                chg = price_f - prev_f
                chg_pct = (chg / prev_f * 100.0) if prev_f > 0 else 0.0
                quote = {
                    "ticker": clean,
                    "symbol": f"{clean}.JK",
                    "price_idr": round(price_f, 2),
                    "prev_close_idr": round(prev_f, 2),
                    "change_idr": round(chg, 2),
                    "change_pct": round(chg_pct, 2),
                    "day_high_idr": meta.get("regularMarketDayHigh"),
                    "day_low_idr": meta.get("regularMarketDayLow"),
                    "volume": meta.get("regularMarketVolume"),
                    "currency": meta.get("currency", "IDR"),
                    "source": "Yahoo Finance (.JK)",
                    "fetched_at": int(now),
                }
    except Exception:
        quote = None

    with _CACHE_LOCK:
        _QUOTE_CACHE[clean] = (now, quote)

    return quote


def fetch_batch_quotes(
    tickers: list[str],
    timeout: float = 5.0,
    max_workers: int = 12,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, dict[str, Any]]:
    """Fetches quotes for multiple IDX tickers concurrently, skipping unavailable symbols."""
    unique = sorted({t.strip().upper() for t in tickers if t and t.strip()})
    if not unique:
        return {}

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(unique))) as pool:
        future_map = {
            pool.submit(fetch_single_quote, t, timeout, ttl_seconds): t
            for t in unique
        }
        for fut in as_completed(future_map):
            t = future_map[fut]
            try:
                q = fut.result()
                if q is not None:
                    results[t] = q
            except Exception:
                continue
    return results


_HISTORY_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any] | None]] = {}
_VALID_RANGES = {
    "1d": "15m",
    "5d": "1h",
    "1mo": "1d",
    "3mo": "1d",
    "6mo": "1d",
    "1y": "1d",
}


def fetch_price_history(
    ticker: str,
    range_str: str = "3mo",
    timeout: float = 6.0,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any] | None:
    """Fetches full OHLCV price history from Yahoo Finance for exchange-style candlestick chart."""
    clean = ticker.strip().upper()
    rng = range_str if range_str in _VALID_RANGES else "3mo"
    interval = _VALID_RANGES[rng]
    if not clean or len(clean) > 6:
        return None

    now = time.time()
    cache_key = (clean, rng)
    with _CACHE_LOCK:
        cached = _HISTORY_CACHE.get(cache_key)
        if cached and (now - cached[0]) < ttl_seconds:
            return cached[1]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    payload = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = (
            f"https://{host}/v8/finance/chart/{clean}.JK"
            f"?interval={interval}&range={rng}"
        )
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if (payload.get("chart") or {}).get("result"):
                break
        except Exception:
            continue

    history: dict[str, Any] | None = None
    try:
        results = ((payload or {}).get("chart") or {}).get("result") or []
        if results:
            res0 = results[0]
            meta = res0.get("meta") or {}
            timestamps = res0.get("timestamp") or []
            quotes_arr = ((res0.get("indicators") or {}).get("quote") or [{}])[0]
            opens = quotes_arr.get("open") or []
            highs = quotes_arr.get("high") or []
            lows = quotes_arr.get("low") or []
            closes = quotes_arr.get("close") or []
            volumes = quotes_arr.get("volume") or []

            is_intraday = rng in ("1d", "5d")
            points = []
            seen_times: set[Any] = set()
            for idx, ts in enumerate(timestamps):
                c = closes[idx] if idx < len(closes) else None
                if c is None:
                    continue
                o = opens[idx] if idx < len(opens) and opens[idx] is not None else c
                h = highs[idx] if idx < len(highs) and highs[idx] is not None else c
                lo = lows[idx] if idx < len(lows) and lows[idx] is not None else c
                v = volumes[idx] if idx < len(volumes) else 0
                # Lightweight Charts uses unix timestamp for intraday, YYYY-MM-DD for daily
                time_key: Any = (
                    int(ts) if is_intraday else time.strftime("%Y-%m-%d", time.gmtime(ts))
                )
                if time_key in seen_times:
                    continue
                seen_times.add(time_key)
                points.append({
                    "time": time_key,
                    "date": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
                    if is_intraday
                    else str(time_key),
                    "open": round(float(o), 2),
                    "high": round(float(h), 2),
                    "low": round(float(lo), 2),
                    "close": round(float(c), 2),
                    "volume": int(v or 0),
                })

            if points:
                first_c = points[0]["close"]
                last_c = float(meta.get("regularMarketPrice") or points[-1]["close"])
                prev_c = float(meta.get("chartPreviousClose") or first_c)
                ref_c = prev_c if rng == "1d" else first_c
                period_chg_pct = ((last_c - ref_c) / ref_c * 100.0) if ref_c > 0 else 0.0
                high_val = max(p["high"] for p in points)
                low_val = min(p["low"] for p in points)
                total_vol = sum(p["volume"] for p in points)
                is_flat = (high_val == low_val and total_vol == 0)
                history = {
                    "ticker": clean,
                    "range": rng,
                    "interval": interval,
                    "is_intraday": is_intraday,
                    "is_flat_suspended": is_flat,
                    "last_price": round(last_c, 2),
                    "prev_close": round(prev_c, 2),
                    "period_change_pct": round(period_chg_pct, 2),
                    "period_high": round(high_val, 2),
                    "period_low": round(low_val, 2),
                    "total_volume": total_vol,
                    "points": points,
                    "source": "Yahoo Finance (.JK)",
                }
    except Exception:
        history = None

    with _CACHE_LOCK:
        _HISTORY_CACHE[cache_key] = (now, history)

    return history
