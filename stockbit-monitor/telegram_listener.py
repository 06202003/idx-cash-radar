"""Dengarkan perintah dari chat Telegram (long polling getUpdates), supaya token
Stockbit bisa diisi/diperbarui langsung dari HP lewat perintah:

    /settoken ACCESS_TOKEN REFRESH_TOKEN

(bisa dipisah spasi atau baris baru). Perintah lain (/status, /broksum, dst) didaftarkan
dari monitor.py lewat parameter `commands`. Hanya menerima perintah dari chat_id yang
terdaftar di TELEGRAM_CHAT_ID -- pesan dari chat lain diabaikan & dicatat di log.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import requests

from token_setup import apply_token

log = logging.getLogger("telegram_listener")


class TelegramCommandListener:
    def __init__(self, bot_token: str, authorized_chat_id: str, token_cache_path: str, reply_fn: Callable[[str], bool],
                 commands: dict[str, Callable[[list[str]], Awaitable[None]]] | None = None):
        self.commands = commands or {}  # "/nama" -> async handler(daftar_argumen)
        self._tasks: set = set()  # pegang referensi task perintah biar nggak ke-GC di tengah jalan
        self.authorized_chat_id = str(authorized_chat_id)
        self.token_cache_path = token_cache_path
        self.reply_fn = reply_fn
        self._api = f"https://api.telegram.org/bot{bot_token}"
        self._offset = 0

    def _get_updates(self):
        resp = requests.get(
            f"{self._api}/getUpdates",
            params={"timeout": 25, "offset": self._offset, "allowed_updates": '["message"]'},
            timeout=35,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

    async def poll_forever(self):
        log.info("Telegram command listener aktif (perintah: %s).", ", ".join(["/settoken", *self.commands]))
        while True:
            try:
                updates = await asyncio.to_thread(self._get_updates)
            except Exception as e:  # noqa: BLE001
                log.warning("Gagal poll getUpdates: %s", e)
                await asyncio.sleep(10)
                continue

            for upd in updates:
                self._offset = upd["update_id"] + 1
                try:
                    await self._handle_update(upd)
                except Exception as e:  # noqa: BLE001
                    log.exception("Gagal proses update: %s", e)

    async def _run_command(self, name: str, args: list[str]):
        try:
            await self.commands[name](args)
        except Exception as e:  # noqa: BLE001
            log.exception("Perintah %s gagal: %s", name, e)
            self.reply_fn(f"⚠️ Perintah {name} gagal: {e}")

    async def _handle_update(self, upd: dict):
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()

        if not text.startswith("/"):
            return
        words = text.split()
        name = words[0].split("@")[0].lower()  # "/status@NamaBot" -> "/status"
        if name in self.commands:
            if chat_id != self.authorized_chat_id:
                log.warning("Perintah %s dari chat_id tidak dikenal (%s), diabaikan.", name, chat_id)
                return
            # jalan sebagai task terpisah: ada perintah yang makan menit (/rekap), jangan
            # sampai nahan polling perintah lain (terutama /settoken).
            task = asyncio.create_task(self._run_command(name, words[1:]))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return

        if not text.startswith("/settoken"):
            return

        if chat_id != self.authorized_chat_id:
            log.warning("Perintah /settoken dari chat_id tidak dikenal (%s), diabaikan.", chat_id)
            return

        rest = text[len("/settoken"):].strip()
        parts = rest.split()
        if len(parts) < 2:
            self.reply_fn(
                "Format: <code>/settoken ACCESS_TOKEN REFRESH_TOKEN</code>\n"
                "(pisah spasi atau baris baru, tempel dalam satu pesan)"
            )
            return

        access_token, refresh_token = parts[0], parts[1]
        ok, message, _ = await asyncio.to_thread(apply_token, access_token, refresh_token, self.token_cache_path)
        prefix = "✅" if ok else "⚠️"
        self.reply_fn(f"{prefix} {message}")
        if ok:
            self.reply_fn("Sekarang hapus pesan /settoken tadi di chat ini biar token tidak nangkring di riwayat.")
