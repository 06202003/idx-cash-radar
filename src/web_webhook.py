"""FastAPI serverless Webhook & Cron entrypoint for deploying idx-alert-bot on Vercel."""

from __future__ import annotations

import asyncio
from typing import Any

from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Query, Request

from src.bot.main import build_dispatcher, create_bot, store
from src.config import CRON_SECRET, DEFAULT_CHAT_ID, DEFAULT_UNIVERSE, DEFAULT_WATCHLIST_ENV
from src.data.fundamental_client import fetch_cash_radar_map
from src.engine.scanner import analyze_ticker, format_ticker_alert

app = FastAPI(title="IDX Alert & Direction Sentiment Bot", version="0.1.0")
_DP = build_dispatcher()


def _resolve_cron_tickers() -> list[str]:
    if DEFAULT_WATCHLIST_ENV:
        return [t.strip().upper() for t in DEFAULT_WATCHLIST_ENV.split(",") if t.strip()][:8]
    return DEFAULT_UNIVERSE[:6]


def _check_cron_auth(authorization: str | None, secret: str | None) -> None:
    if not CRON_SECRET:
        return
    token = (secret or "").strip()
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid CRON_SECRET")


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "idx-alert-bot", "mode": "serverless-webhook"}


@app.post("/api/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    """Receives Telegram Bot API updates via Webhook."""
    payload = await request.json()
    bot = create_bot()
    try:
        update = Update.model_validate(payload, context={"bot": bot})
        await _DP.feed_update(bot, update)
    finally:
        await bot.session.close()
    return {"ok": True}


@app.get("/api/set-webhook")
async def register_webhook(request: Request, url: str | None = Query(default=None)) -> dict[str, Any]:
    """Registers the Vercel deployment URL as Telegram Webhook."""
    target_url = (url or str(request.base_url).rstrip("/") + "/api/webhook").strip()
    if not target_url.endswith("/api/webhook"):
        target_url = target_url.rstrip("/") + "/api/webhook"
    bot = create_bot()
    try:
        ok = await bot.set_webhook(url=target_url)
    finally:
        await bot.session.close()
    return {"ok": ok, "webhook_url": target_url}


async def _run_cron_broadcast(alert_type: str) -> dict[str, Any]:
    subs = store.list_all_subscribers()
    if not subs and DEFAULT_CHAT_ID:
        try:
            subs = {int(DEFAULT_CHAT_ID): _resolve_cron_tickers()}
        except ValueError:
            subs = {}

    if not subs:
        return {"status": "skipped", "reason": "No subscribers or DEFAULT_CHAT_ID configured"}

    cash_map = await asyncio.to_thread(fetch_cash_radar_map)
    bot = create_bot()
    sent_count = 0
    try:
        for chat_id, tickers in subs.items():
            blocks = []
            for t in tickers[:8]:
                res = await asyncio.to_thread(analyze_ticker, t, cash_map)
                if res.get("technicals"):
                    blocks.append(format_ticker_alert(res))
            if blocks:
                title = (
                    "🔔 *MORNING ALERT (08:45 WIB)*"
                    if alert_type == "morning"
                    else "🌙 *REKAP SORE WATCHLIST (18:00 WIB)*"
                )
                await bot.send_message(chat_id, title + "\n\n" + "\n\n---\n\n".join(blocks))
                sent_count += 1
    finally:
        await bot.session.close()

    return {"status": "ok", "alert_type": alert_type, "chats_notified": sent_count}


@app.get("/api/cron/morning")
async def cron_morning(
    authorization: str | None = Header(default=None),
    secret: str | None = Query(default=None),
) -> dict[str, Any]:
    _check_cron_auth(authorization, secret)
    return await _run_cron_broadcast("morning")


@app.get("/api/cron/evening")
async def cron_evening(
    authorization: str | None = Header(default=None),
    secret: str | None = Query(default=None),
) -> dict[str, Any]:
    _check_cron_auth(authorization, secret)
    return await _run_cron_broadcast("evening")
