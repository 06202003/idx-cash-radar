"""Frozen 10y data snapshot manager with SHA256 manifest and strict segment splitting."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.market_feed import fetch_jk_ohlcv
from src.eval.data_loader import ORIGINAL_6, UNIVERSE_28

ROOT_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = ROOT_DIR / "data_snapshot"
MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"

LIQUIDITY_THRESHOLD_IDR = 5_000_000_000.0  # Rp 5 Miliar 60d median daily traded value
DISCOVERY_5Y_BARS = 1200
LOCK_RECENT_BARS = 126
PURGE_BARS = 5


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_snapshot(range_str: str = "10y", force: bool = False) -> dict[str, Any]:
    """Downloads 10y OHLCV once and freezes it to data_snapshot/ with SHA256 hashes."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if MANIFEST_PATH.exists() and not force:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    manifest: dict[str, Any] = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "range_str": range_str,
        "format": "csv.gz (pyarrow/fastparquet unavailable)",
        "files": {},
    }
    for ticker in UNIVERSE_28 + ["^JKSE"]:
        df = fetch_jk_ohlcv(ticker, range_str=range_str, timeout=15.0)
        safe = ticker.replace("^", "IDX_")
        fname = f"{safe}_{range_str}.csv.gz"
        fpath = SNAPSHOT_DIR / fname
        df.to_csv(fpath, index=False, compression="gzip")
        manifest["files"][ticker] = {
            "filename": fname,
            "rows": len(df),
            "start_date": str(df["date"].iloc[0]) if not df.empty else None,
            "end_date": str(df["date"].iloc[-1]) if not df.empty else None,
            "sha256": _sha256_file(fpath),
        }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_snapshot() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    """Loads frozen OHLCV data strictly from data_snapshot/ (verifying SHA256)."""
    if not MANIFEST_PATH.exists():
        manifest = create_snapshot(range_str="10y", force=False)
    else:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    data: dict[str, pd.DataFrame] = {}
    jkse = pd.DataFrame()
    for ticker, meta in manifest["files"].items():
        fpath = SNAPSHOT_DIR / meta["filename"]
        if _sha256_file(fpath) != meta["sha256"]:
            raise RuntimeError(f"Snapshot integrity check failed for {ticker}: {fpath}")
        df = pd.read_csv(fpath, compression="gzip")
        if ticker == "^JKSE":
            jkse = df
        elif not df.empty:
            data[ticker] = df
    return data, jkse, manifest


def apply_liquidity_and_segments(
    data: dict[str, pd.DataFrame],
    min_value_idr: float = LIQUIDITY_THRESHOLD_IDR,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """
    Applies causal 60-day median traded value filter and assigns segment labels:
    - LOCK-RECENT: last 126 bars
    - DISCOVERY: 5y window (~1200 bars) minus last 126 bars (with 5-bar purge)
    - FRESH-PAST: older than 5y window (with 5-bar purge)
    """
    filtered: dict[str, pd.DataFrame] = {}
    stats: dict[str, Any] = {
        "total_tickers": len(data),
        "eliminated_tickers": [],
        "total_bars_raw": 0,
        "total_bars_after_liq": 0,
        "fresh_past_bars": 0,
        "discovery_bars": 0,
        "lock_recent_bars": 0,
    }

    for t, raw_df in data.items():
        df = raw_df.sort_values("date").reset_index(drop=True).copy()
        n = len(df)
        stats["total_bars_raw"] += n
        if n < 250:
            stats["eliminated_tickers"].append((t, f"rows={n}<250"))
            continue

        val_idr = df["close"].astype(float) * df["volume"].astype(float)
        med60 = val_idr.rolling(60, min_periods=60).median()
        df["liq_ok"] = (med60 >= min_value_idr).fillna(False)

        # Assign time segments by bar index from end (non-overlapping with 5-bar purge)
        seg = np.full(n, "PURGE", dtype=object)
        lock_start = max(0, n - LOCK_RECENT_BARS)
        disc_start = max(0, n - DISCOVERY_5Y_BARS)
        disc_end = max(0, lock_start - PURGE_BARS)
        fresh_end = max(0, disc_start - PURGE_BARS)

        seg[lock_start:] = "LOCK-RECENT"
        if disc_end > disc_start:
            seg[disc_start:disc_end] = "DISCOVERY"
        if fresh_end > 0:
            seg[:fresh_end] = "FRESH-PAST"
        df["segment"] = seg

        n_liq = int(df["liq_ok"].sum())
        stats["total_bars_after_liq"] += n_liq
        if int(((df["segment"] == "DISCOVERY") & df["liq_ok"]).sum()) < 120:
            stats["eliminated_tickers"].append((t, "insufficient_liquid_discovery"))
            continue

        stats["fresh_past_bars"] += int(((df["segment"] == "FRESH-PAST") & df["liq_ok"]).sum())
        stats["discovery_bars"] += int(((df["segment"] == "DISCOVERY") & df["liq_ok"]).sum())
        stats["lock_recent_bars"] += int(((df["segment"] == "LOCK-RECENT") & df["liq_ok"]).sum())
        filtered[t] = df

    stats["kept_tickers"] = len(filtered)
    stats["kept_original_6"] = [t for t in ORIGINAL_6 if t in filtered]
    return filtered, stats
