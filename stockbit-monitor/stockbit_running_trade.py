"""Ambil running trade SELURUH pasar lewat REST polling.

Endpoint WebSocket lama (wss-trading.stockbit.com) ternyata sudah tidak menerima
subscribe apa pun -- konsisten menolak dengan "you are not authorized" walau token
valid dan akun terbukti punya akses fitur Running Trade normal di app resminya.
Hasil investigasi: app web resmi Stockbit sendiri sekarang pakai REST polling ke
endpoint di bawah ini buat fitur yang sama, bukan WebSocket. Jadi kita ikutin itu --
lebih simpel dan terbukti jalan.
"""
from __future__ import annotations

import requests

from stockbit_auth import COMMON_HEADERS

URL = "https://exodus.stockbit.com/order-trade/running-trade"


def fetch_running_trade(access_token: str, limit: int = 80) -> tuple[list[dict], bool]:
    """Return (daftar_trade_terbaru, is_open_market). Melempar requests.HTTPError kalau gagal."""
    headers = dict(COMMON_HEADERS)
    headers["Authorization"] = f"Bearer {access_token}"
    params = {"sort": "DESC", "limit": limit, "order_by": "RUNNING_TRADE_ORDER_BY_TIME"}
    resp = requests.get(URL, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", {})
    return data.get("running_trade", []), bool(data.get("is_open_market", False))
