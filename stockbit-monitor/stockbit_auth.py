"""Auth ke Stockbit (API tidak resmi, hasil reverse-engineering).

Login lewat password (login/v6/username) sekarang wajib reCAPTCHA v3 -- token itu
tidak bisa dibuat lewat HTTP client biasa. Jadi flow di sini TIDAK login sendiri:
access_token + refresh_token diisi manual sekali (hasil login lewat browser asli),
lalu proses ini hanya mengandalkan endpoint refresh (login/refresh) yang tidak
butuh recaptcha untuk memperpanjang sesi selama mungkin.

Kalau refresh_token akhirnya invalid/revoked, satu-satunya jalan adalah login
manual lagi lewat browser dan isi ulang token cache-nya (lihat set_token.py).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import requests

BASE_URL = "https://exodus.stockbit.com"

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "X-DeviceType": "Google Chrome",
    "X-Platform": "PC",
    "X-AppVersion": "3.17.2",
    "Accept-Language": "ID",
    "Content-Type": "application/json",
}


class StockbitAuthError(RuntimeError):
    pass


class NewDeviceVerificationRequired(StockbitAuthError):
    """Login berhasil tapi Stockbit minta verifikasi device baru (OTP dsb)."""

    def __init__(self, payload):
        super().__init__("Stockbit meminta verifikasi device baru (OTP). Cek payload.")
        self.payload = payload


class ManualReloginRequired(StockbitAuthError):
    """Token cache kosong/invalid dan refresh_token juga sudah tidak berlaku.
    Butuh login manual lewat browser lalu isi ulang token cache (set_token.py)."""


@dataclass
class TokenData:
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0  # epoch seconds
    user_id: int = 0


@dataclass
class StockbitAuthClient:
    username: str = ""
    password: str = ""
    player_id: str = ""
    session: requests.Session = field(default_factory=requests.Session)
    token: TokenData = field(default_factory=TokenData)
    token_cache_path: str = ""  # kalau diisi, auto-save tiap kali token berubah (mis. habis refresh)

    # ---------- low level ----------

    def _headers(self, auth: bool = False) -> dict:
        h = dict(COMMON_HEADERS)
        if auth:
            h["Authorization"] = f"Bearer {self.token.access_token}"
        return h

    # ---------- auth flow ----------

    def login(self) -> None:
        body = {"user": self.username, "password": self.password, "player_id": self.player_id}
        resp = self.session.post(f"{BASE_URL}/login/v6/username", headers=self._headers(), data=json.dumps(body), timeout=30)
        payload = _safe_json(resp)

        if resp.status_code != 200:
            raise StockbitAuthError(f"Login gagal ({resp.status_code}): {payload}")

        data = payload.get("data", {})
        access_token, refresh_token, expired_at = _try_extract_tokens(payload)
        if access_token and refresh_token:
            self.token.access_token = access_token
            self.token.refresh_token = refresh_token
            self.token.expires_at = _parse_expiry(expired_at)
            return

        # Beberapa flow mengembalikan indikasi perlu verifikasi device baru / OTP
        if "multi_factor" in data or "trusted_device" in data or "login_token" in data:
            raise NewDeviceVerificationRequired(payload)

        raise StockbitAuthError(f"Struktur respons login tidak dikenali: {payload}")

    def refresh(self) -> None:
        headers = self._headers()
        headers["Authorization"] = f"Bearer {self.token.refresh_token}"
        resp = self.session.post(f"{BASE_URL}/login/refresh", headers=headers, timeout=30)
        payload = _safe_json(resp)
        if resp.status_code != 200:
            raise StockbitAuthError(f"Refresh token gagal ({resp.status_code}): {payload}")

        access_token, refresh_token, expired_at = _try_extract_tokens(payload)
        if not access_token or not refresh_token:
            # PENTING: jangan overwrite/simpan apa pun kalau parsing gagal -- token lama
            # (termasuk refresh_token yang masih valid) harus tetap utuh buat percobaan berikutnya.
            raise StockbitAuthError(
                f"Refresh sukses (200) tapi token tidak ketemu di respons -- struktur API kemungkinan "
                f"sudah berubah. Payload mentah: {payload}"
            )

        self.token.access_token = access_token
        self.token.refresh_token = refresh_token
        self.token.expires_at = _parse_expiry(expired_at)
        if self.token_cache_path:
            self.save_token_cache(self.token_cache_path)

    def ensure_valid_token(self) -> str:
        if not self.token.access_token or time.time() > self.token.expires_at - 300:
            if not self.token.refresh_token:
                raise ManualReloginRequired(
                    "Tidak ada refresh_token tersimpan. Login manual lewat browser lalu jalankan set_token.py."
                )
            try:
                self.refresh()
            except StockbitAuthError as e:
                raise ManualReloginRequired(
                    f"Refresh token gagal/invalid ({e}). Login manual lewat browser lalu jalankan set_token.py."
                ) from e
        return self.token.access_token

    # ---------- token cache (diisi manual dari hasil login browser) ----------

    def load_token_cache(self, path: str) -> None:
        if not os.path.exists(path):
            raise ManualReloginRequired(
                f"Token cache {path} belum ada. Login manual lewat browser lalu jalankan set_token.py."
            )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.token.access_token = data.get("access_token", "")
        self.token.refresh_token = data.get("refresh_token", "")
        self.token.expires_at = float(data.get("expires_at", 0))
        self.token.user_id = int(data.get("user_id", 0))

    def save_token_cache(self, path: str) -> None:
        data = {
            "access_token": self.token.access_token,
            "refresh_token": self.token.refresh_token,
            "expires_at": self.token.expires_at,
            "user_id": self.token.user_id,
        }
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def _get(self, path: str, token: str) -> requests.Response:
        headers = self._headers()
        headers["Authorization"] = f"Bearer {token}"
        return self.session.get(f"{BASE_URL}{path}", headers=headers, timeout=30)

    def _authed_get(self, path: str) -> requests.Response:
        """GET dengan Bearer token, auto-refresh + retry sekali kalau dapat 401 --
        expires_at yang tersimpan lokal kadang nggak sinkron sama kondisi asli di
        server (mis. token dicabut dari sisi lain), jadi jangan cuma percaya expiry
        lokal begitu saja."""
        token = self.ensure_valid_token()
        resp = self._get(path, token)
        if resp.status_code == 401:
            try:
                self.refresh()
            except StockbitAuthError as e:
                raise ManualReloginRequired(
                    f"Token ditolak server (401) dan refresh juga gagal: {e}. "
                    "Login manual lewat browser lalu kirim /settoken atau jalankan set_token.py."
                ) from e
            resp = self._get(path, self.token.access_token)
        return resp

    def fetch_user_id(self) -> int:
        resp = self._authed_get("/usergraph/socialinfo/user/me")
        payload = _safe_json(resp)
        if resp.status_code != 200:
            raise StockbitAuthError(f"Ambil user id gagal ({resp.status_code}): {payload}")
        user_id = payload.get("data", {}).get("user_id", 0)
        self.token.user_id = int(user_id)
        return self.token.user_id

    def fetch_websocket_key(self) -> str:
        resp = self._authed_get("/auth/websocket/key")
        payload = _safe_json(resp)
        if resp.status_code != 200:
            raise StockbitAuthError(f"Ambil websocket key gagal ({resp.status_code}): {payload}")
        return payload.get("data", {}).get("key", "")


def _safe_json(resp: requests.Response):
    try:
        return resp.json()
    except ValueError:
        return {"raw_text": resp.text[:2000]}


def _dig(d, path: list[str]):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _try_extract_tokens(payload: dict) -> tuple[str, str, str | None]:
    """Coba beberapa kemungkinan struktur respons Stockbit (bisa berubah tanpa
    pemberitahuan karena ini API tidak resmi). Return ("", "", None) kalau semua gagal --
    caller WAJIB treat ini sebagai kegagalan, jangan pernah overwrite token lama pakai hasil kosong."""
    candidates = [
        ["data", "refresh"],
        ["data", "login", "token_data"],
        ["data"],
        [],
    ]
    for path in candidates:
        node = _dig(payload, path)
        if not isinstance(node, dict):
            continue
        access = node.get("access")
        refresh = node.get("refresh")
        if not isinstance(access, dict) or not isinstance(refresh, dict):
            continue
        access_token = access.get("token", "")
        refresh_token = refresh.get("token", "")
        if access_token and refresh_token:
            return access_token, refresh_token, access.get("expired_at")
    return "", "", None


def _parse_expiry(expired_at: str | None) -> float:
    if not expired_at:
        return time.time() + 900  # fallback konservatif kalau expired_at tidak ada/tidak kebaca
    try:
        # ISO 8601, contoh: 2026-09-10T12:34:56Z
        import datetime

        dt = datetime.datetime.strptime(expired_at.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
        return dt.timestamp()
    except Exception:
        return time.time() + 3600
