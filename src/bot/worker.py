"""
Fase 8 Production Telegram Bot Worker & Scheduler (Docker + PostgreSQL/Supabase).
Implements /bantuan, /tentang, /cek (PNG card + news URL), /watch, /unwatch, /watchlist,
/stop (UU PDP full data deletion), /jadwal, IDX holiday guard, and idempotent delivery.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from src.bot.briefing import (
    capture_universe_daily_snapshot,
    detect_filing_change_for_ticker,
    detect_verifiable_events,
    fetch_factual_market_quote,
    fetch_verifiable_news,
    format_event_alert,
    format_filing_change_alert,
    format_volume_alert,
    format_watchlist_briefing_item,
    list_universe_tickers,
    load_canonical_ticker_record,
)
from src.bot.idx_calendar import is_idx_trading_day, now_wib
from src.bot.pg_store import MAX_WATCHLIST_TICKERS, BotStateStore
from src.db.repository import FinancialRepository
from src.engine.realtime_news_analyzer import detect_ticker_in_article, fetch_article_from_url
from src.renderer.share_card import build_share_card_payload, render_share_card_png

logger = logging.getLogger("idx-cash-radar.bot-worker")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://idx-cash-radar.vercel.app").rstrip("/")
VOLUME_ALERT_THRESHOLD = float(os.getenv("VOLUME_ALERT_THRESHOLD", "3.0"))
GROUP_COOLDOWN_SECONDS = float(os.getenv("GROUP_COOLDOWN_SECONDS", "60.0"))
_URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+")
_TICKER_TOKEN_RE = re.compile(r"\b([A-Z]{4,5})\b")


def extract_url_or_ticker(text: str, universe: set[str] | None = None) -> tuple[str | None, str | None]:
    """
    Extracts (url, ticker) from free text or forwarded messages.
    Uses detect_ticker_in_article first, then falls back to known universe tokens.
    """
    raw = (text or "").strip()
    if not raw:
        return None, None
    url_m = _URL_RE.search(raw)
    if url_m:
        return url_m.group(0), None

    if universe:
        issuers_arg = [{"ticker": t} for t in universe]
        detected = detect_ticker_in_article(raw, issuers_arg)
        if detected:
            return None, detected
        for tok in _TICKER_TOKEN_RE.findall(raw.upper()):
            if tok in universe:
                return None, tok
    return None, None


def build_about_text() -> str:
    return (
        "ℹ️ *Tentang IDX Cash & Accrual Radar*\n\n"
        "Platform audit fakta laporan keuangan XBRL resmi BEI berbasis perhitungan deterministik Python (`Decimal`).\n"
        f"• Metodologi & Ambang Aturan: {PUBLIC_BASE_URL}/metodologi\n"
        f"• Kebijakan Privasi (UU PDP): `docs/privacy.md` (ketik `/stop` untuk menghapus seluruh data Anda).\n\n"
        "_Catatan: Seluruh data bersifat historis per tanggal pelaporan BEI dan bukan ajakan transaksi maupun saran investasi._"
    )


def format_unknown_ticker_message(ticker: str) -> str:
    return (
        f"ℹ️ Emiten `{ticker}` belum ada di data kami.\n"
        "Gunakan `/cek <KODE>` untuk emiten yang tercakup di universe kami."
    )


def build_briefing_message_for_user(
    tickers: list[str],
    title: str,
    repo: FinancialRepository,
    store: BotStateStore | None = None,
    fetch_external: bool = True,
) -> str | None:
    """Builds a personalized watchlist briefing using only the user's watched tickers."""
    if not tickers:
        return None
    blocks: list[str] = []
    for t in tickers[:MAX_WATCHLIST_TICKERS]:
        rec = load_canonical_ticker_record(t, repo)
        if not rec:
            continue
        market = fetch_factual_market_quote(t, store=store) if fetch_external else None
        news = fetch_verifiable_news(t, max_items=1, store=store) if fetch_external else []
        blocks.append(format_watchlist_briefing_item(rec, market=market, news=news))
    if not blocks:
        return None
    return f"*{title}*\n\n" + "\n\n---\n\n".join(blocks)


async def send_with_resilience(
    bot: Bot,
    chat_id: int,
    text: str,
    store: BotStateStore,
    delivery_key: str,
    alert_date: date,
    alert_type: str,
    ticker: str,
    max_retries: int = 3,
) -> bool:
    """
    Idempotently sends a Telegram message handling TelegramRetryAfter, transient errors,
    and TelegramForbiddenError (user blocked bot).
    """
    if store.has_delivered(delivery_key):
        return False

    for attempt in range(1, max_retries + 1):
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            store.record_alert_delivery(
                delivery_key=delivery_key,
                chat_id=chat_id,
                alert_date=alert_date,
                alert_type=alert_type,
                ticker=ticker,
                message_text=text,
                status="SENT",
            )
            return True
        except TelegramRetryAfter as exc:
            wait_s = max(float(exc.retry_after), 1.0)
            logger.warning("Telegram rate limit (%ss) on chat %s", wait_s, chat_id)
            await asyncio.sleep(wait_s)
        except TelegramForbiddenError as exc:
            logger.info("User %s blocked the bot; removing watchlist data.", chat_id)
            store.record_alert_delivery(
                delivery_key=delivery_key,
                chat_id=chat_id,
                alert_date=alert_date,
                alert_type=alert_type,
                ticker=ticker,
                message_text=text,
                status="BLOCKED",
                error_detail=str(exc)[:200],
            )
            store.delete_user_data(chat_id)
            return False
        except Exception as exc:
            if attempt >= max_retries:
                store.record_alert_delivery(
                    delivery_key=delivery_key,
                    chat_id=chat_id,
                    alert_date=alert_date,
                    alert_type=alert_type,
                    ticker=ticker,
                    message_text=text,
                    status="FAILED",
                    error_detail=str(exc)[:200],
                )
                return False
            await asyncio.sleep(1.5 * attempt)
    return False


async def run_scheduler_tick(
    bot: Bot,
    store: BotStateStore,
    repo: FinancialRepository,
    now_dt: datetime | None = None,
    fetch_external: bool = True,
) -> dict[str, int]:
    """
    Executes one scheduler tick in Asia/Jakarta time:
    - Skips if IDX is closed (weekend or IDX holiday).
    - Sends per-user morning briefing at their configured HH:MM (default 08:30 WIB).
    - Sends evening recap at 18:00 WIB & archives daily_snapshot for the entire universe.
    - Sends factual volume/event alerts for watched tickers.
    """
    current = now_dt or now_wib()
    today = current.date()
    if not is_idx_trading_day(today):
        return {"skipped_holiday": 1, "morning_sent": 0, "evening_sent": 0, "snapshots": 0}

    hhmm = current.strftime("%H:%M")
    morning_sent = 0
    evening_sent = 0
    snapshots = 0

    # 1. Per-user morning watchlist briefing
    morning_subs = store.list_subscribers_for_time(hhmm)
    for cid, tickers in morning_subs.items():
        dkey = store.build_delivery_key(cid, today, "morning_briefing", hhmm)
        if store.has_delivered(dkey):
            continue
        msg = await asyncio.to_thread(
            build_briefing_message_for_user,
            tickers,
            f"📋 BRIEFING WATCHLIST PAGI ({hhmm} WIB)",
            repo,
            store,
            fetch_external,
        )
        if msg and await send_with_resilience(bot, cid, msg, store, dkey, today, "morning_briefing", "WATCHLIST"):
            morning_sent += 1

    # 2. Evening recap (18:00 WIB) + universe daily_snapshot
    if hhmm == "18:00":
        all_subs = store.list_all_subscribers()
        for cid, tickers in all_subs.items():
            dkey = store.build_delivery_key(cid, today, "evening_recap", "18:00")
            if store.has_delivered(dkey):
                continue
            msg = await asyncio.to_thread(
                build_briefing_message_for_user,
                tickers,
                "🌆 REKAP WATCHLIST SORE (18:00 WIB)",
                repo,
                store,
                fetch_external,
            )
            if msg and await send_with_resilience(bot, cid, msg, store, dkey, today, "evening_recap", "WATCHLIST"):
                evening_sent += 1

        if store.count_snapshots(today) == 0:
            snapshots = await asyncio.to_thread(
                capture_universe_daily_snapshot, store, repo, today, fetch_external
            )

    # 3. Watched ticker filing-change, event & volume alerts (idempotent per ticker per day)
    if fetch_external and current.hour in (9, 10, 11, 13, 14, 15):
        all_subs = store.list_all_subscribers()
        watched_unique = sorted({t for ts in all_subs.values() for t in ts})
        for t in watched_unique:
            filing_change = await asyncio.to_thread(detect_filing_change_for_ticker, t, store, repo)
            if filing_change:
                fmsg = format_filing_change_alert(filing_change)
                for cid, user_tickers in all_subs.items():
                    if t in user_tickers:
                        fkey = store.build_delivery_key(cid, today, "filing_change", filing_change["new_filing_id"])
                        await send_with_resilience(bot, cid, fmsg, store, fkey, today, "filing_change", t)
                store.set_last_seen_filing(t, filing_change["new_filing_id"])

            market = await asyncio.to_thread(fetch_factual_market_quote, t, store)
            news = await asyncio.to_thread(fetch_verifiable_news, t, 2, store)
            events = detect_verifiable_events(news) if news else []

            for cid, user_tickers in all_subs.items():
                if t not in user_tickers:
                    continue
                if market and market["vol_ratio_20d"] >= VOLUME_ALERT_THRESHOLD:
                    vkey = store.build_delivery_key(cid, today, "volume_alert", t)
                    if not store.has_delivered(vkey):
                        vmsg = format_volume_alert(t, market["vol_ratio_20d"])
                        await send_with_resilience(bot, cid, vmsg, store, vkey, today, "volume_alert", t)
                for ev in events:
                    ekey = store.build_delivery_key(cid, today, f"event_{ev['event_type']}", t)
                    if not store.has_delivered(ekey):
                        emsg = format_event_alert(t, ev)
                        await send_with_resilience(bot, cid, emsg, store, ekey, today, f"event_{ev['event_type']}", t)

    return {
        "skipped_holiday": 0,
        "morning_sent": morning_sent,
        "evening_sent": evening_sent,
        "snapshots": snapshots,
    }


def create_fase8_router(store: BotStateStore, repo: FinancialRepository) -> Router:
    """Creates an aiogram Router implementing all Fase 8 production commands."""
    router = Router(name="fase8")

    @router.message(Command("start", ignore_case=True))
    async def handle_start_pg(message: Message) -> None:
        cid = int(message.chat.id)
        store.touch_user(cid)
        store.record_analytics_event("bot_start")
        from src.bot.main import handle_start
        await handle_start(message)

    @router.message(Command("tentang", ignore_case=True))
    async def handle_tentang(message: Message) -> None:
        await message.answer(build_about_text())

    @router.message(Command("stop", ignore_case=True))
    async def handle_stop(message: Message) -> None:
        cid = int(message.chat.id)
        deleted = store.delete_user_data(cid)
        await message.answer(
            "🗑️ Seluruh data Anda (watchlist, jadwal briefing, dan log pengiriman) telah dihapus dari sistem.\n"
            f"Ringkasan penghapusan: {deleted['watchlists_deleted']} watchlist, "
            f"{deleted['schedules_deleted']} jadwal, {deleted['alert_logs_deleted']} log."
        )

    @router.message(Command("jadwal", ignore_case=True))
    async def handle_jadwal(message: Message) -> None:
        parts = (message.text or "").strip().split()
        cid = int(message.chat.id)
        if len(parts) < 2:
            cur = store.get_morning_time(cid)
            await message.answer(
                f"⏰ Jadwal briefing pagi Anda saat ini: `{cur} WIB`.\n"
                "Untuk mengubah, kirim: `/jadwal 08:30` (format 24 jam HH:MM WIB)."
            )
            return
        if store.set_morning_time(cid, parts[1]):
            await message.answer(f"✅ Jadwal briefing watchlist pagi diubah menjadi `{parts[1]} WIB` (hari bursa BEI).")
        else:
            await message.answer("⚠️ Format jam tidak valid. Gunakan format 24 jam HH:MM, contoh: `/jadwal 08:15`.")

    @router.message(Command("watch", ignore_case=True))
    async def handle_watch_pg(message: Message) -> None:
        parts = (message.text or "").strip().split()
        if len(parts) < 2:
            await message.answer("⚠️ Format: `/watch <KODE>` (contoh: `/watch ADRO`).")
            return
        clean_t = store.validate_ticker(parts[1])
        if not clean_t:
            await message.answer("⚠️ Kode saham harus 4–5 karakter huruf/angka (contoh: `ADRO`, `BBRI`).")
            return
        rec = load_canonical_ticker_record(clean_t, repo)
        if not rec:
            store.record_analytics_event("ticker_tidak_ditemukan", clean_t)
            await message.answer(format_unknown_ticker_message(clean_t))
            return
        ok, msg = store.add_watch(int(message.chat.id), clean_t)
        store.touch_user(int(message.chat.id))
        prefix = "✅" if ok else "⚠️"
        await message.answer(f"{prefix} {msg}")

    @router.message(Command("unwatch", ignore_case=True))
    async def handle_unwatch_pg(message: Message) -> None:
        parts = (message.text or "").strip().split()
        if len(parts) < 2:
            await message.answer("⚠️ Format: `/unwatch <KODE>`.")
            return
        clean_t = store.validate_ticker(parts[1])
        if not clean_t:
            await message.answer("⚠️ Kode saham tidak valid.")
            return
        removed = store.remove_watch(int(message.chat.id), clean_t)
        if removed:
            await message.answer(f"🗑️ `{clean_t}` dihapus dari watchlist Anda.")
        else:
            await message.answer(f"ℹ️ `{clean_t}` tidak ada di watchlist Anda.")

    @router.message(Command("watchlist", ignore_case=True))
    async def handle_watchlist_pg(message: Message) -> None:
        cid = int(message.chat.id)
        tickers = store.list_watch(cid)
        if not tickers:
            await message.answer("Watchlist Anda kosong. Tambahkan dengan `/watch ADRO` (maks 20 emiten).")
            return
        msg = await asyncio.to_thread(
            build_briefing_message_for_user,
            tickers,
            f"📋 WATCHLIST ANDA ({len(tickers)}/{MAX_WATCHLIST_TICKERS})",
            repo,
            store,
            False,
        )
        await message.answer(msg or "Watchlist kosong.")

    async def _reply_checked_url(message: Message, url: str) -> None:
        is_group = message.chat.type in ("group", "supergroup")
        if is_group and not store.check_and_set_group_cooldown(int(message.chat.id), "URL", GROUP_COOLDOWN_SECONDS):
            return
        res = await asyncio.to_thread(fetch_article_from_url, url)
        headline = res.get("headline") or "-"
        src = res.get("source") or "Web"
        body_text = res.get("body_text") or ""
        issuers_arg = [{"ticker": tk} for tk in list_universe_tickers(repo)]
        t = detect_ticker_in_article(f"{headline}\n{body_text}", issuers_arg, url=url)
        lines = [f"📰 *{headline}*", f"Media: _{src}_", url]
        if t:
            rec = load_canonical_ticker_record(t, repo)
            if rec:
                lines.append("\n" + format_watchlist_briefing_item(rec))
                if is_group:
                    store.record_analytics_event("kartu_dibagikan", t)
            else:
                store.record_analytics_event("ticker_tidak_ditemukan", t)
                lines.append("\n" + format_unknown_ticker_message(t))
        await message.answer("\n".join(lines))

    async def _reply_checked_ticker(message: Message, raw_ticker: str) -> None:
        clean_t = store.validate_ticker(raw_ticker)
        if not clean_t:
            await message.answer("⚠️ Format kode saham tidak valid (4–5 karakter).")
            return
        is_group = message.chat.type in ("group", "supergroup")
        if is_group and not store.check_and_set_group_cooldown(int(message.chat.id), clean_t, GROUP_COOLDOWN_SECONDS):
            return

        rec = load_canonical_ticker_record(clean_t, repo)
        if not rec:
            store.record_analytics_event("ticker_tidak_ditemukan", clean_t)
            await message.answer(format_unknown_ticker_message(clean_t))
            return

        caption = format_watchlist_briefing_item(rec)
        payload = build_share_card_payload(rec)
        png_bytes = await asyncio.to_thread(render_share_card_png, payload, "1:1")
        photo = BufferedInputFile(png_bytes, filename=f"{clean_t}_card.png")
        await message.answer_photo(photo=photo, caption=caption)
        if is_group:
            store.record_analytics_event("kartu_dibagikan", clean_t)

    @router.message(Command("cek", ignore_case=True))
    async def handle_cek_pg(message: Message) -> None:
        store.touch_user(int(message.chat.id))
        parts = (message.text or "").strip().split(maxsplit=1)
        arg = parts[1].strip() if len(parts) >= 2 else ""

        # Group/reply support: /cek replying to a message mentioning a stock or URL
        if not arg and message.reply_to_message:
            replied_txt = message.reply_to_message.text or message.reply_to_message.caption or ""
            universe = set(list_universe_tickers(repo))
            found_url, found_ticker = extract_url_or_ticker(replied_txt, universe=universe)
            if found_url:
                await _reply_checked_url(message, found_url)
                return
            if found_ticker:
                await _reply_checked_ticker(message, found_ticker)
                return
            await message.answer("ℹ️ Tidak ditemukan kode saham atau tautan berita pada pesan yang dibalas.")
            return

        if not arg:
            await message.answer("Gunakan `/cek <KODE>` (contoh: `/cek WIKA`) atau `/cek <URL_BERITA>`.")
            return
        if arg.startswith("http://") or arg.startswith("https://"):
            await _reply_checked_url(message, arg)
            return
        await _reply_checked_ticker(message, arg)

    @router.message(F.forward_origin | (F.chat.type == "private") & F.text.regexp(r"https?://"))
    async def handle_forward_to_check(message: Message) -> None:
        """Forward-to-check: extracts URL or ticker from forwarded messages or private URLs."""
        store.touch_user(int(message.chat.id))
        raw = message.text or message.caption or ""
        universe = set(list_universe_tickers(repo))
        found_url, found_ticker = extract_url_or_ticker(raw, universe=universe)
        if found_url:
            await _reply_checked_url(message, found_url)
            return
        if found_ticker:
            await _reply_checked_ticker(message, found_ticker)
            return
        await message.answer("ℹ️ Tidak ditemukan kode saham BEI atau tautan berita di pesan yang diteruskan.")

    @router.inline_query()
    async def handle_inline_query(inline_query: InlineQuery) -> None:
        """Inline mode: @botname TLKM sends factual cash card directly to any group/chat."""
        q = (inline_query.query or "").strip().upper().replace(".JK", "")
        universe = list_universe_tickers(repo)
        matches = [t for t in universe if t.startswith(q)] if q else universe[:5]
        results: list[InlineQueryResultArticle] = []
        for t in matches[:5]:
            rec = load_canonical_ticker_record(t, repo)
            if not rec:
                continue
            card_text = format_watchlist_briefing_item(rec)
            results.append(
                InlineQueryResultArticle(
                    id=f"card_{t}",
                    title=f"{t} — {rec['company_name']}",
                    description=f"Kas: {rec['cash_coverage_display']} | Laporan: {rec['period_end_date']}",
                    input_message_content=InputTextMessageContent(message_text=card_text),
                )
            )
        if results:
            store.record_analytics_event("kartu_dibagikan", matches[0])
        await inline_query.answer(results=results, cache_time=60, is_personal=False)

    return router


async def run_worker() -> None:
    """Entrypoint for dedicated Docker Telegram Bot + Scheduler worker."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN wajib diisi.")

    store = BotStateStore()  # Enforces PostgreSQL DATABASE_URL in production
    repo = FinancialRepository()
    bot = Bot(token=token)

    from aiogram import Dispatcher

    dp = Dispatcher()
    dp.include_router(create_fase8_router(store, repo))

    # Also keep legacy /help & /bantuan handler
    from src.bot.main import handle_help

    dp.message.register(handle_help, Command("help", "bantuan", ignore_case=True))

    async def _loop() -> None:
        while True:
            try:
                await run_scheduler_tick(bot, store, repo)
            except Exception as exc:
                logger.warning("Scheduler tick error: %s", exc)
            await asyncio.sleep(60)

    sched = asyncio.create_task(_loop())
    try:
        logger.info("Fase 8 Telegram Worker started (PostgreSQL + Asia/Jakarta scheduler).")
        await dp.start_polling(bot)
    finally:
        sched.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
