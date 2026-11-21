"""Isi token cache Stockbit secara manual lewat terminal (alternatif dari /settoken di Telegram).

Jalankan ini LANGSUNG DI SERVER (bukan lewat chat AI manapun):
    source .venv/bin/activate
    python3 set_token.py

Cara ambil access_token & refresh_token: lihat instruksi yang sama di telegram_listener.py
atau README singkat yang sudah dijelaskan sebelumnya (DevTools -> Network -> login/v6/username
-> tab Response -> data.login.token_data.access.token / .refresh.token).

Input di bawah TIDAK ditampilkan ke layar dan TIDAK pernah dikirim ke mana pun
selain disimpan ke token_cache.json di folder ini.
"""
from __future__ import annotations

import getpass

from token_setup import apply_token

TOKEN_CACHE_PATH = "token_cache.json"


def main():
    print("=== Isi token Stockbit (input disembunyikan) ===")
    access_token = getpass.getpass("access_token: ")
    refresh_token = getpass.getpass("refresh_token: ")
    expires_in_min_raw = input("access token berlaku berapa menit lagi dari sekarang? [default 30]: ").strip()
    expires_in_min = int(expires_in_min_raw) if expires_in_min_raw else 30

    ok, message, _ = apply_token(access_token, refresh_token, TOKEN_CACHE_PATH, expires_in_min)
    print(("OK. " if ok else "GAGAL. ") + message)


if __name__ == "__main__":
    main()
