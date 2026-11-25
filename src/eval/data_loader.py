"""Dataset loader, universe definition, caching, and dev/hold-out splitting."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.market_feed import fetch_jk_ohlcv

ORIGINAL_6: list[str] = ["VKTR", "BBCA", "BBRI", "ADRO", "ANTM", "BRIS"]

EXTRA_LIQUID_22: list[str] = [
    "BMRI", "BBNI", "TLKM", "ISAT", "EXCL",
    "ASII", "UNTR", "PTBA", "ITMG", "INCO",
    "MEDC", "PGAS", "AKRA", "ICBP", "INDF",
    "MYOR", "KLBF", "AMRT", "MAPI", "UNVR",
    "CPIN", "SMGR",
]

UNIVERSE_28: list[str] = ORIGINAL_6 + EXTRA_LIQUID_22

CACHE_DIR = Path(__file__).resolve().parents[2] / "experiments" / "cache"


def load_ticker_ohlcv(ticker: str, range_str: str = "5y", use_cache: bool = True) -> pd.DataFrame:
    """Fetches and caches OHLCV data for reproducible offline re-runs."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = ticker.replace("^", "IDX_")
    cache_file = CACHE_DIR / f"{safe_name}_{range_str}.csv"
    if use_cache and cache_file.exists():
        df = pd.read_csv(cache_file)
        if not df.empty:
            return df
    df = fetch_jk_ohlcv(ticker, range_str=range_str)
    if not df.empty and use_cache:
        df.to_csv(cache_file, index=False)
    return df


def load_universe(range_str: str = "5y", use_cache: bool = True) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Loads OHLCV for all 28 tickers + ^JKSE benchmark."""
    jkse = load_ticker_ohlcv("^JKSE", range_str=range_str, use_cache=use_cache)
    data: dict[str, pd.DataFrame] = {}
    for t in UNIVERSE_28:
        df = load_ticker_ohlcv(t, range_str=range_str, use_cache=use_cache)
        if len(df) >= 250:
            data[t] = df
    return data, jkse
