"""Kirim alert ke Telegram lewat Bot API (bot terpisah dari bot trading MT5)."""
from __future__ import annotations

import logging
import re

import requests

log = logging.getLogger("notify_telegram")


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._api = f"https://api.telegram.org/bot{bot_token}"

    def send(self, text: str) -> bool:
        try:
            resp = requests.post(
                f"{self._api}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            if resp.status_code == 400 and "parse entities" in resp.text:
                # format HTML-nya ditolak: mending terkirim polos daripada pesannya hilang
                log.warning("HTML ditolak Telegram, kirim ulang sebagai teks polos: %s", resp.text[:200])
                resp = requests.post(
                    f"{self._api}/sendMessage",
                    json={"chat_id": self.chat_id, "text": re.sub(r"</?(?:b|i|pre|code)>", "", text),
                          "disable_web_page_preview": True},
                    timeout=15,
                )
            if resp.status_code != 200:
                log.error("Gagal kirim Telegram (%s): %s", resp.status_code, resp.text[:500])
                return False
            return True
        except requests.RequestException as e:
            log.error("Error kirim Telegram: %s", e)
            return False
