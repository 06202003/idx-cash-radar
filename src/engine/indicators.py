"""Technical indicators and regime detection for IDX daily OHLCV bars."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds MA20, MA50, RSI(14), momentum returns, volume spike ratio, and volatility."""
    out = df.copy()
    close = out["close"].astype(float)
    vol = out["volume"].astype(float)

    out["ma20"] = close.rolling(20, min_periods=20).mean()
    out["ma50"] = close.rolling(50, min_periods=50).mean()

    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0.0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0.0, np.nan)
    out["rsi14"] = 100.0 - (100.0 / (1.0 + rs))
    out.loc[(loss == 0.0) & (gain > 0.0), "rsi14"] = 100.0
    out.loc[(gain == 0.0) & (loss == 0.0), "rsi14"] = 50.0

    out["ret_1d"] = close.pct_change(1)
    out["ret_5d"] = close.pct_change(5)
    out["ret_20d"] = close.pct_change(20)

    vol_avg20 = vol.rolling(20, min_periods=20).mean().replace(0.0, np.nan)
    out["vol_ratio_20d"] = (vol / vol_avg20).fillna(1.0)
    out["volatility_20d"] = out["ret_1d"].rolling(20, min_periods=20).std().fillna(0.0)

    out["dist_ma20"] = (close / out["ma20"]) - 1.0
    out["dist_ma50"] = (close / out["ma50"]) - 1.0
    out["high_20d"] = out["high"].astype(float).rolling(20, min_periods=20).max()
    out["low_20d"] = out["low"].astype(float).rolling(20, min_periods=20).min()
    return out


def summarize_latest_technicals(ind_df: pd.DataFrame) -> dict[str, object]:
    """Extracts human-readable technical regime and spike warnings from latest bar."""
    if ind_df.empty:
        return {}
    last = ind_df.iloc[-1]
    close = float(last["close"])
    ma20 = float(last["ma20"]) if pd.notna(last["ma20"]) else None
    ma50 = float(last["ma50"]) if pd.notna(last["ma50"]) else None
    rsi = float(last["rsi14"]) if pd.notna(last["rsi14"]) else None
    vol_ratio = float(last["vol_ratio_20d"]) if pd.notna(last["vol_ratio_20d"]) else 1.0
    ret_1d = float(last["ret_1d"]) if pd.notna(last["ret_1d"]) else 0.0

    if ma20 is not None and ma50 is not None:
        if close > ma20 > ma50:
            trend = "UPTREND (Harga > MA20 > MA50)"
        elif close < ma20 < ma50:
            trend = "DOWNTREND (Harga < MA20 < MA50)"
        else:
            trend = "SIDEWAYS / TRANSISI"
    else:
        trend = "DATA TERBATAS"

    spike_chase_warning = bool(vol_ratio >= 3.0 and ret_1d >= 0.03)
    dist_ma20 = float(last["dist_ma20"]) if "dist_ma20" in last and pd.notna(last["dist_ma20"]) else None
    dist_ma50 = float(last["dist_ma50"]) if "dist_ma50" in last and pd.notna(last["dist_ma50"]) else None
    vol20 = float(last["volatility_20d"]) if "volatility_20d" in last and pd.notna(last["volatility_20d"]) else None
    h20 = float(last["high_20d"]) if pd.notna(last["high_20d"]) else None
    l20 = float(last["low_20d"]) if pd.notna(last["low_20d"]) else None
    pos20 = ((close - l20) / (h20 - l20) * 100.0) if (h20 is not None and l20 is not None and h20 > l20) else None
    return {
        "date": str(last["date"]),
        "close": close,
        "ret_1d_pct": round(ret_1d * 100.0, 2),
        "ret_5d_pct": round(float(last["ret_5d"] or 0.0) * 100.0, 2),
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "vol_ratio_20d": round(vol_ratio, 2),
        "dist_ma20_pct": round(dist_ma20 * 100.0, 2) if dist_ma20 is not None else None,
        "dist_ma50_pct": round(dist_ma50 * 100.0, 2) if dist_ma50 is not None else None,
        "pos_20d_pct": round(pos20, 1) if pos20 is not None else None,
        "volatility_20d_pct": round(vol20 * 100.0, 2) if vol20 is not None else None,
        "trend": trend,
        "spike_chase_warning": spike_chase_warning,
        "high_20d": h20,
        "low_20d": l20,
    }
