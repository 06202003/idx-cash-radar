"""Telegram Bot entrypoint (aiogram 3.x) with 08:45 WIB & 18:00 WIB alert scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, KeyboardButton, Message, ReplyKeyboardMarkup

from src.config import (
    ADMIN_CHAT_ID,
    DEFAULT_UNIVERSE,
    EVENING_RECAP_HOUR,
    EVENING_RECAP_MINUTE,
    MORNING_ALERT_HOUR,
    MORNING_ALERT_MINUTE,
    TELEGRAM_BOT_TOKEN,
)
from src.data.fundamental_client import fetch_cash_radar_map
from src.data.stockbit_feed import (
    StockbitAuthError,
    _get_json,
    fetch_stockbit_orderbook,
    fetch_stockbit_trade_book,
)
from src.data.stockbit_token_manager import (
    get_token_remaining_seconds,
    load_active_token,
    refresh_token_via_playwright,
    save_active_token,
)
from src.db.store import AlertStore
from src.engine.anomaly_detectors import (
    detect_broker_flow_anomaly,
    detect_tradebook_dominance,
    detect_wall_pulled,
    extract_latest_tradebook_delta,
    format_broker_flow_alert,
    format_tradebook_dominance_alert,
    format_wall_pulled_alert,
)
from src.engine.orderbook_monitor import detect_orderbook_wall_deltas, format_orderbook_wall_alert
from src.engine.scanner import analyze_ticker, format_ticker_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("idx-alert-bot")
WIB = ZoneInfo("Asia/Jakarta")

store = AlertStore()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Cek Saham"), KeyboardButton(text="⚡ Morning Scan")],
        [KeyboardButton(text="⭐ Watchlist"), KeyboardButton(text="🔑 Status Token")],
        [KeyboardButton(text="📖 Bantuan")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Ketik kode saham (misal: BBCA) atau /cek BBRI...",
)


def _extract_ticker_arg(text: str) -> str | None:
    parts = (text or "").strip().split()
    if len(parts) >= 2:
        return parts[1].strip().upper().replace(".JK", "")
    return None


async def cmd_start(message: Message) -> None:
    await message.answer(
        "📡 *IDX Alert & Direction Sentiment Bot*\n\n"
        "Bot asisten riset & alert saham BEI (Teknikal + Forecast Arah 5H + Berita + Kas XBRL + Stockbit Orderbook/Broker).\n\n"
        "*Perintah tersedia:*\n"
        "• `/cek <KODE>` — Cek sentimen arah naik/turun, backtest OOS, berita & kas\n"
        "• `/morning` — Jalankan pemindaian Morning Confluence sekarang\n"
        "• `/watch <KODE>` — Tambah saham ke watchlist alert otomatis\n"
        "• `/unwatch <KODE>` — Hapus saham dari watchlist\n"
        "• `/watchlist` — Lihat daftar pantauan Anda\n"
        "• `/pola <KODE>` — Rekap riwayat orderbook & pola market maker hari ini\n"
        "• `/tokenstatus` & `/settoken <JWT>` — Cek / perbarui token Stockbit\n\n"
        "_Catatan: Hasil forecast & skor sentimen merupakan alat bantu riset statistik, bukan saran investasi._",
        reply_markup=MAIN_KEYBOARD,
    )


async def cmd_cek(message: Message) -> None:
    ticker = _extract_ticker_arg(message.text or "")
    if not ticker:
        await message.answer("Gunakan format: `/cek BBRI` atau ketik langsung kode saham (misal `ADRO`).")
        return

    wait_msg = await message.answer(f"⏳ Menganalisis *{ticker}* (OHLCV 2Y, Walk-Forward Backtest, RSS & Kas XBRL)...")
    res = await asyncio.to_thread(analyze_ticker, ticker)
    if not res.get("technicals"):
        await wait_msg.edit_text(f"❌ Data pasar untuk `{ticker}.JK` tidak ditemukan.")
        return

    fc = res.get("forecast") or {}
    news = res.get("news") or []
    store.log_alert(
        ticker=ticker,
        alert_type="manual_cek",
        price_close=res["technicals"].get("close"),
        p_up_pct=fc.get("p_up_pct"),
        composite_score=res.get("composite_score"),
        badge=res.get("badge", ""),
        news_sentiment=news[0]["sentiment"] if news else "NETRAL",
        chat_id=message.chat.id,
    )
    await wait_msg.edit_text(format_ticker_alert(res))


async def cmd_watch(message: Message) -> None:
    ticker = _extract_ticker_arg(message.text or "")
    if not ticker or not ticker.isalnum() or len(ticker) > 6:
        await message.answer("Gunakan format: `/watch ADRO`")
        return
    store.add_watch(message.chat.id, ticker)
    await message.answer(f"✅ *{ticker}* ditambahkan ke watchlist. Anda akan menerima rekap otomatis pukul 08:45 & 18:00 WIB.")


async def cmd_unwatch(message: Message) -> None:
    ticker = _extract_ticker_arg(message.text or "")
    if not ticker:
        await message.answer("Gunakan format: `/unwatch ADRO`")
        return
    removed = store.remove_watch(message.chat.id, ticker)
    if removed:
        await message.answer(f"🗑️ *{ticker}* dihapus dari watchlist.")
    else:
        await message.answer(f"ℹ️ *{ticker}* tidak ada di watchlist Anda.")


async def cmd_watchlist(message: Message) -> None:
    items = store.list_watch(message.chat.id)
    if not items:
        await message.answer("Watchlist Anda kosong. Tambahkan dengan `/watch BBRI` atau `/watch ADRO`.")
        return
    await message.answer("📋 *Watchlist Anda:*\n" + ", ".join(f"`{t}`" for t in items))


async def cmd_morning(message: Message) -> None:
    wait_msg = await message.answer("🔎 Memindai universe saham BEI untuk Morning Confluence...")
    cash_map = await asyncio.to_thread(fetch_cash_radar_map)
    sample_tickers = store.list_watch(message.chat.id) or DEFAULT_UNIVERSE[:10]

    results = []
    for t in sample_tickers:
        res = await asyncio.to_thread(analyze_ticker, t, cash_map)
        if res.get("technicals"):
            results.append(res)

    results.sort(key=lambda r: r["composite_score"], reverse=True)
    top = results[:5]
    if not top:
        await wait_msg.edit_text("❌ Gagal mengambil data pasar saat ini.")
        return

    header = f"🔔 *MORNING CONFLUENCE & DIRECTION RADAR*\nDipindai: {len(results)} emiten\n\n"
    body = "\n\n---\n\n".join(format_ticker_alert(r) for r in top)
    await wait_msg.edit_text(header + body)


async def on_plain_ticker(message: Message) -> None:
    raw = (message.text or "").strip()
    if raw == "🔍 Cek Saham":
        await message.answer("Ketik langsung kode saham 4 huruf (misal: `BBCA`, `BBRI`, `ADRO`) atau `/cek BBRI`.")
        return
    if raw == "⚡ Morning Scan":
        await cmd_morning(message)
        return
    if raw == "⭐ Watchlist":
        await cmd_watchlist(message)
        return
    if raw == "🔑 Status Token":
        await cmd_tokenstatus(message)
        return
    if raw == "📖 Bantuan":
        await cmd_start(message)
        return

    txt = raw.upper()
    if txt.isalpha() and 4 <= len(txt) <= 5:
        wait_msg = await message.answer(f"⏳ Menganalisis *{txt}*...")
        res = await asyncio.to_thread(analyze_ticker, txt)
        if not res.get("technicals"):
            await wait_msg.edit_text(f"❌ Data pasar untuk `{txt}.JK` tidak ditemukan.")
            return
        await wait_msg.edit_text(format_ticker_alert(res))


async def scheduler_loop(bot: Bot) -> None:
    """Runs daily 08:45 WIB Morning Confluence & 18:00 WIB Evening Recap for watchlist subscribers."""
    sent_today: set[tuple[str, str]] = set()
    while True:
        try:
            now = datetime.now(WIB)
            day_key = now.strftime("%Y-%m-%d")
            is_weekday = now.weekday() < 5

            if is_weekday:
                if now.hour == MORNING_ALERT_HOUR and now.minute == MORNING_ALERT_MINUTE and (day_key, "morning") not in sent_today:
                    sent_today.add((day_key, "morning"))
                    await _broadcast_watchlist_alerts(bot, "morning")
                if now.hour == EVENING_RECAP_HOUR and now.minute == EVENING_RECAP_MINUTE and (day_key, "evening") not in sent_today:
                    sent_today.add((day_key, "evening"))
                    await _broadcast_watchlist_alerts(bot, "evening")
        except Exception as exc:
            logger.warning("Scheduler error: %s", exc)
        await asyncio.sleep(30)


async def _broadcast_watchlist_alerts(bot: Bot, alert_type: str) -> None:
    subs = store.list_all_subscribers()
    if not subs:
        return
    cash_map = await asyncio.to_thread(fetch_cash_radar_map)
    for chat_id, tickers in subs.items():
        blocks = []
        for t in tickers[:8]:
            res = await asyncio.to_thread(analyze_ticker, t, cash_map)
            if res.get("technicals"):
                blocks.append(format_ticker_alert(res))
                fc = res.get("forecast") or {}
                news = res.get("news") or []
                store.log_alert(
                    ticker=t,
                    alert_type=alert_type,
                    price_close=res["technicals"].get("close"),
                    p_up_pct=fc.get("p_up_pct"),
                    composite_score=res.get("composite_score"),
                    badge=res.get("badge", ""),
                    news_sentiment=news[0]["sentiment"] if news else "NETRAL",
                    chat_id=chat_id,
                )
        if blocks:
            title = "🔔 *MORNING ALERT (08:45 WIB)*" if alert_type == "morning" else "🌙 *REKAP SORE WATCHLIST (18:00 WIB)*"
            await bot.send_message(chat_id, title + "\n\n" + "\n\n---\n\n".join(blocks))


def create_bot() -> Bot:
    """Creates an aiogram Bot instance from TELEGRAM_BOT_TOKEN."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN belum diatur di environment / .env")
    return Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))


async def cmd_settoken(message: Message) -> None:
    if ADMIN_CHAT_ID and str(message.chat.id) != ADMIN_CHAT_ID:
        await message.answer("⛔ Perintah ini hanya untuk admin.")
        return
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Gunakan: `/settoken <BEARER_JWT>`")
        return
    saved = save_active_token(parts[1])
    rem = get_token_remaining_seconds(saved)
    hours = round(rem / 3600.0, 1) if rem is not None else "?"
    await message.answer(f"✅ Stockbit Bearer token diperbarui! Sisa masa berlaku: `{hours} jam`.")


async def cmd_tokenstatus(message: Message) -> None:
    if ADMIN_CHAT_ID and str(message.chat.id) != ADMIN_CHAT_ID:
        await message.answer("⛔ Perintah ini hanya untuk admin.")
        return
    tok = load_active_token()
    if not tok:
        await message.answer("❌ Stockbit token belum diatur. Gunakan `/settoken <JWT>` atau `--login`.")
        return
    rem = get_token_remaining_seconds(tok)
    if rem is None:
        await message.answer("ℹ️ Token aktif, namun tidak memiliki klaim `exp`.")
    elif rem <= 0:
        await message.answer("⚠️ Stockbit token sudah **expired**. Mencoba refresh atau kirim `/settoken <JWT>`.")
    else:
        await message.answer(f"🔑 Stockbit token aktif — sisa `{round(rem / 3600.0, 1)} jam`.")


async def cmd_pola(message: Message) -> None:
    ticker = _extract_ticker_arg(message.text or "")
    if not ticker:
        await message.answer("Gunakan format: `/pola BBRI` untuk melihat rekaman pola market maker hari ini.")
        return
    report = store.format_mm_pattern_report(ticker)
    await message.answer(report)


def build_dispatcher() -> Dispatcher:
    """Builds and wires all command & text message handlers."""
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start", "help"))
    dp.message.register(cmd_cek, Command("cek", "check"))
    dp.message.register(cmd_watch, Command("watch"))
    dp.message.register(cmd_unwatch, Command("unwatch"))
    dp.message.register(cmd_watchlist, Command("watchlist"))
    dp.message.register(cmd_morning, Command("morning"))
    dp.message.register(cmd_pola, Command("pola", "riwayat"))
    dp.message.register(cmd_settoken, Command("settoken"))
    dp.message.register(cmd_tokenstatus, Command("tokenstatus"))
    dp.message.register(on_plain_ticker, F.text)
    return dp


async def orderbook_monitor_loop(bot: Bot, poll_seconds: float = 25.0) -> None:
    """
    Polls Stockbit orderbook, 1m trade-book, and broker summary during IDX market hours
    for Bid/Offer walls, pulled walls, 1m HAKA/HAKI dominance, and Retail vs Institutional flips.
    """
    import time
    import urllib.parse

    prev_snapshots: dict[str, dict] = {}
    last_sent_ts: dict[tuple[str, str], float] = {}

    def _cooldown_ok(ticker: str, kind: str, sec: float = 300.0) -> bool:
        now_t = time.time()
        prev_t = last_sent_ts.get((ticker, kind), 0.0)
        if now_t - prev_t >= sec:
            last_sent_ts[(ticker, kind)] = now_t
            return True
        return False

    while True:
        try:
            now = datetime.now(WIB)
            in_session = (now.weekday() < 5) and (9 <= now.hour < 16)
            tok = load_active_token()
            if in_session and tok:
                subs = store.list_all_subscribers()
                unique_tickers = sorted({t for ts in subs.values() for t in ts})
                for t in unique_tickers[:10]:
                    try:
                        curr_ob = await asyncio.to_thread(fetch_stockbit_orderbook, t, tok)
                    except StockbitAuthError:
                        refreshed = await asyncio.to_thread(refresh_token_via_playwright, headless=True)
                        if refreshed:
                            tok = refreshed
                            curr_ob = await asyncio.to_thread(fetch_stockbit_orderbook, t, tok)
                        else:
                            break
                    except Exception:
                        curr_ob = {"bid": {}, "offer": {}}

                    alerts_to_send: list[str] = []
                    tb_raw: dict = {}
                    trade_lots: dict | None = None
                    try:
                        tb_raw = await asyncio.to_thread(fetch_stockbit_trade_book, t, tok, "1m")
                        trade_lots = extract_latest_tradebook_delta(tb_raw)
                    except Exception:
                        tb_raw = {}

                    prev_ob = prev_snapshots.get(t)
                    if prev_ob and (curr_ob.get("bid") or curr_ob.get("offer")):
                        for w in detect_orderbook_wall_deltas(prev_ob, curr_ob, min_delta_lot=5000, max_delta_freq=2)[:2]:
                            if _cooldown_ok(t, f"wall_{w['side']}_{w['price']}", 180.0):
                                alerts_to_send.append(format_orderbook_wall_alert(t, w))
                                store.log_mm_event(
                                    t,
                                    "WALL_ADDED",
                                    side=w["side"],
                                    price=w["price"],
                                    lot_delta=w["delta_lot"],
                                    freq_delta=w["delta_freq"],
                                )
                        for pw in detect_wall_pulled(prev_ob, curr_ob, min_pulled_lot=5000, trade_lots=trade_lots)[:2]:
                            if pw.get("eaten_by_trade"):
                                if _cooldown_ok(t, f"eaten_{pw['side']}_{pw['price']}", 180.0):
                                    store.log_mm_event(
                                        t,
                                        "WALL_EATEN",
                                        side=pw["side"],
                                        price=pw["price"],
                                        lot_delta=-pw["pulled_lot"],
                                        freq_delta=pw["delta_freq"],
                                        detail="Dimakan HAKI/HAKA",
                                    )
                            elif _cooldown_ok(t, f"pulled_{pw['side']}_{pw['price']}", 180.0):
                                alerts_to_send.append(format_wall_pulled_alert(t, pw))
                                store.log_mm_event(
                                    t,
                                    "WALL_PULLED",
                                    side=pw["side"],
                                    price=pw["price"],
                                    lot_delta=-pw["pulled_lot"],
                                    freq_delta=pw["delta_freq"],
                                )
                    if curr_ob.get("bid") or curr_ob.get("offer"):
                        prev_snapshots[t] = curr_ob

                    if tb_raw:
                        dom = detect_tradebook_dominance(t, tb_raw)
                        if dom and _cooldown_ok(t, f"dom_{dom['side']}", 300.0):
                            alerts_to_send.append(format_tradebook_dominance_alert(dom))
                            store.log_mm_event(
                                t,
                                f"{dom['side']}_1M",
                                side=dom["side"],
                                lot_delta=dom.get("buy_lot") if dom["side"] == "HAKA" else -int(dom.get("sell_lot") or 0),
                                value_idr=dom["total_value_idr"],
                                detail=f"{dom['dominance_pct']}% ({dom.get('time') or ''})",
                            )

                    try:
                        md_url = (
                            f"https://exodus.stockbit.com/marketdetectors/{urllib.parse.quote(t)}"
                            "?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER"
                            "&investor_type=INVESTOR_TYPE_ALL&limit=25&period=BROKER_SUMMARY_PERIOD_LATEST"
                        )
                        md_raw = await asyncio.to_thread(_get_json, md_url, tok)
                        bf = detect_broker_flow_anomaly(t, md_raw)
                        if bf and _cooldown_ok(t, f"bf_{bf['signal']}", 900.0):
                            alerts_to_send.append(format_broker_flow_alert(bf))
                            store.log_mm_event(
                                t,
                                "BROKER_FLIP",
                                side=bf["signal"],
                                value_idr=abs(bf["non_retail_net_idr"]),
                                detail=f"Non-Ritel: {','.join(bf['non_retail_brokers'])}",
                            )
                    except Exception:
                        pass

                    for alert_txt in alerts_to_send:
                        for cid, user_tickers in subs.items():
                            if t in user_tickers:
                                await bot.send_message(cid, alert_txt)
        except Exception as exc:
            logger.warning("Orderbook monitor error: %s", exc)
        await asyncio.sleep(poll_seconds)


async def main() -> None:
    bot = create_bot()
    dp = build_dispatcher()

    try:
        await bot.set_my_commands([
            BotCommand(command="cek", description="Analisis saham & sentimen arah (misal /cek BBCA)"),
            BotCommand(command="morning", description="Scan Morning Confluence watchlist"),
            BotCommand(command="watch", description="Tambah saham ke watchlist alert"),
            BotCommand(command="unwatch", description="Hapus saham dari watchlist"),
            BotCommand(command="watchlist", description="Lihat daftar watchlist aktif"),
            BotCommand(command="pola", description="Rekam pola market maker & orderbook hari ini"),
            BotCommand(command="tokenstatus", description="Cek sisa masa aktif token Stockbit"),
            BotCommand(command="settoken", description="Perbarui Bearer JWT Stockbit"),
            BotCommand(command="start", description="Bantuan & tampilkan menu tombol"),
        ])
    except Exception as exc:
        logger.warning("Failed to set bot commands: %s", exc)

    sched_task = asyncio.create_task(scheduler_loop(bot))
    ob_task = asyncio.create_task(orderbook_monitor_loop(bot))
    try:
        logger.info("Starting idx-alert-bot polling...")
        await dp.start_polling(bot)
    finally:
        sched_task.cancel()
        ob_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
