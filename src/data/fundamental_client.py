"""Optional fundamental cash-safety lookup from IDX Cash & Accrual Radar API."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from src.config import CASH_RADAR_API_URL

_CACHE: dict[str, dict[str, Any]] = {}


def fetch_cash_radar_map(timeout: float = 5.0) -> dict[str, dict[str, Any]]:
    """Fetches screener cash metrics from idx-cash-radar API, falling back to cache on error."""
    global _CACHE
    url = f"{CASH_RADAR_API_URL}/api/screener?fiscal_year=2025"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; IDXAlertBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        if isinstance(rows, list) and rows:
            _CACHE = {str(r["ticker"]).upper(): r for r in rows if r.get("ticker")}
    except Exception:
        pass
    return dict(_CACHE)
