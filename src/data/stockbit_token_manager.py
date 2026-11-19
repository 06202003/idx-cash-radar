"""Stockbit Bearer JWT token manager (runtime storage, JWT exp check, and Playwright auto-refresh)."""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

from src.config import STOCKBIT_BEARER_TOKEN, STOCKBIT_PROFILE_DIR, STOCKBIT_TOKEN_FILE


def _strip_bearer(raw: str) -> str:
    s = (raw or "").strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    return s


def decode_jwt_expiry(token: str) -> int | None:
    """Decodes the 'exp' Unix timestamp from a JWT without verifying signature."""
    clean = _strip_bearer(token)
    parts = clean.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    try:
        raw_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        data = json.loads(raw_bytes.decode("utf-8"))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def get_token_remaining_seconds(token: str) -> int | None:
    exp = decode_jwt_expiry(token)
    if exp is None:
        return None
    return int(exp - time.time())


def load_active_token(token_file: Path = STOCKBIT_TOKEN_FILE) -> str:
    """Loads active Stockbit Bearer token from .stockbit_token file or env."""
    if token_file.exists():
        saved = _strip_bearer(token_file.read_text(encoding="utf-8"))
        if saved:
            return saved
    return _strip_bearer(STOCKBIT_BEARER_TOKEN)


def save_active_token(token: str, token_file: Path = STOCKBIT_TOKEN_FILE) -> str:
    clean = _strip_bearer(token)
    token_file.write_text(clean, encoding="utf-8")
    return clean


def refresh_token_via_playwright(
    profile_dir: Path = STOCKBIT_PROFILE_DIR,
    token_file: Path = STOCKBIT_TOKEN_FILE,
    headless: bool = True,
    timeout_ms: int = 25_000,
) -> str | None:
    """
    Opens stockbit.com using a persistent Chromium/Edge profile directory.
    Captures the fresh Authorization: Bearer token from exodus.stockbit.com network traffic.
    """
    from playwright.sync_api import sync_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)
    captured: list[str] = []

    with sync_playwright() as p:
        context = None
        for channel in ("msedge", "chrome", None):
            try:
                kwargs: dict[str, Any] = {
                    "user_data_dir": str(profile_dir),
                    "headless": headless,
                }
                if channel:
                    kwargs["channel"] = channel
                context = p.chromium.launch_persistent_context(**kwargs)
                break
            except Exception:
                continue
        if context is None:
            return None

        try:
            page = context.pages[0] if context.pages else context.new_page()

            def _on_request(req: Any) -> None:
                if "exodus.stockbit.com" in req.url:
                    auth = req.headers.get("authorization") or req.headers.get("Authorization")
                    if auth and auth.lower().startswith("bearer "):
                        tok = _strip_bearer(auth)
                        if tok and tok not in captured:
                            captured.append(tok)

            page.on("request", _on_request)
            page.goto("https://stockbit.com/symbol/BBCA", wait_until="domcontentloaded", timeout=timeout_ms)
            deadline = time.time() + (timeout_ms / 1000.0)
            while time.time() < deadline and not captured:
                page.wait_for_timeout(500)
        finally:
            context.close()

    if captured:
        return save_active_token(captured[-1], token_file=token_file)
    return None


if __name__ == "__main__":
    if "--login" in sys.argv:
        print("Membuka browser untuk login Stockbit (tutup setelah masuk halaman utama & token tertangkap)...")
        tok = refresh_token_via_playwright(headless=False, timeout_ms=120_000)
        if tok:
            rem = get_token_remaining_seconds(tok)
            print(f"Token tersimpan! Sisa masa berlaku: {rem} detik.")
        else:
            print("Gagal menangkap token. Pastikan Anda sudah login di halaman Stockbit.")
    else:
        tok = refresh_token_via_playwright(headless=True)
        print("Refresh OK" if tok else "Refresh gagal (perlu --login ulang)")
