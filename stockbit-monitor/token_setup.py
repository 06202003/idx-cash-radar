"""Helper bersama: validasi access_token/refresh_token Stockbit lalu simpan ke token cache.
Dipakai oleh set_token.py (CLI) dan telegram_listener.py (perintah /settoken)."""
from __future__ import annotations

import time

from stockbit_auth import StockbitAuthClient, TokenData


def apply_token(access_token: str, refresh_token: str, token_cache_path: str, expires_in_min: int = 30):
    """Return (ok: bool, message: str, user_id: int)."""
    access_token = (access_token or "").strip()
    refresh_token = (refresh_token or "").strip()
    if not access_token or not refresh_token:
        return False, "access_token / refresh_token kosong.", 0

    client = StockbitAuthClient(token_cache_path=token_cache_path)
    client.token = TokenData(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=time.time() + expires_in_min * 60,
    )

    try:
        uid = client.fetch_user_id()
    except Exception as e:  # noqa: BLE001
        return False, f"Gagal verifikasi token ke Stockbit: {e}. Cek lagi token-nya, mungkin salah tempel / sudah expired.", 0

    client.token.user_id = uid
    client.save_token_cache(token_cache_path)
    return True, f"Token tersimpan, user_id={uid}. Monitor akan lanjut otomatis.", uid
