"""Telegram Bot entrypoint (aiogram 3.x) with 08:45 WIB & 18:00 WIB alert scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from src.config import (
    ADMIN_CHAT_ID,
    DEFAULT_UNIVERSE,
    EVENING_RECAP_HOUR,
    EVENING_RECAP_MINUTE,
    MORNING_ALERT_HOUR,
    MORNING_ALERT_MINUTE,
    STAGING_CHAT_IDS,
    TELEGRAM_BOT_TOKEN,
)
from src.data.fundamental_client import fetch_cash_radar_map
from src.data.market_feed import fetch_jk_ohlcv
from src.data.stockbit_feed import (
    StockbitAuthError,
    _get_json,
    backfill_broker_history,
    fetch_stockbit_broker_summary_for_date,
    fetch_stockbit_intraday,
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
    build_instant_signal_analysis,
    detect_broker_flow_anomaly,
    detect_tradebook_dominance,
    detect_wall_pulled,
    extract_latest_tradebook_delta,
    format_broker_flow_alert,
    format_tradebook_dominance_alert,
    format_wall_pulled_alert,
)
from src.engine.broker_patterns import analyze_broker_patterns
from src.engine.chart_renderer import render_ascii_bar_chart, render_morning_chart, render_sparkline_line
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
    first_name = (message.from_user.first_name if message.from_user else "") or "Trader"
    await message.answer(
        f"👁️ *IDX CASH RADAR* — _Selamat datang, {first_name}!_\n"
        "_Melihat menembus ilusi laba, menangkap jejak kas nyata & smart money BEI._\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *MULAI CEPAT (3 DETIK)*\n"
        "• Ketik langsung kode saham (contoh: `BBCA`, `BBRI`, `ADRO`) untuk analisis lengkap\n"
        "• `/watch BBCA` — Pantau real-time *Wall, HAKA/HAKI, & Broker Flip*\n"
        "• `/morning` — Scan Morning Confluence + *Grafik & Pola Broker*\n\n"
        "🧭 *MENU & PERINTAH*\n"
        "• `/cek <KODE>` — Teknikal, Forecast 5H, OOS Backtest, Berita & Kas XBRL\n"
        "• `/chart <KODE>` — Grafik mini intraday real-time (ASCII terminal)\n"
        "• `/pola <KODE>` — Rekap jejak Market Maker & orderbook hari ini\n"
        "• `/watchlist` / `/unwatch <KODE>` — Kelola daftar pantauan\n"
        "• `/modal <RUPIAH>` — Atur modal untuk hitung lot & Risk:Reward (misal `/modal 50jt`)\n"
        "• `/tokenstatus` & `/settoken <JWT>` — Cek / perbarui token Stockbit\n\n"
        "⏰ *Jadwal Auto-Alert:* `08:45 WIB` (Morning Radar) & `18:00 WIB` (Rekap Sore)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "_Disclaimer: Alat bantu riset kuantitatif & aliran dana, bukan ajakan beli/jual._",
        reply_markup=MAIN_KEYBOARD,
    )


def _skeleton_ticker_loading(ticker: str, pct: int = 35, step_note: str = "Menarik OHLCV, Broksum & Berita...") -> str:
    filled = max(1, min(10, round(pct / 10)))
    bar = ("▓" * filled) + ("░" * (10 - filled))
    t_done = "▓▓▓▓▓▓▓▓" if pct >= 50 else "▓▓▓▓░░░░"
    f_done = "▓▓▓▓▓▓▓▓" if pct >= 75 else "░░░░░░░░"
    s_done = "▓▓▓▓░░░░" if pct >= 75 else "░░░░░░░░"
    return (
        f"⏳ *ANALISIS RADAR | {ticker}*\n"
        f"`[{bar}] {pct}%` — _{step_note}_\n\n"
        f"• 📐 Teknikal & Level 20H: `{t_done}`\n"
        f"• 🎯 Forecast 5H & OOS: `{f_done}`\n"
        f"• 🤝 Broksum & Kas XBRL: `{t_done}`\n"
        f"• 📰 Berita & Sparkline: `{s_done}`"
    )


def _skeleton_scan_loading(done: int, total: int, current_ticker: str = "") -> str:
    total = max(1, total)
    pct = min(100, int(round(done / total * 100)))
    filled = max(0, min(10, round(pct / 10)))
    bar = ("▓" * filled) + ("░" * (10 - filled))
    curr_txt = f"Memindai *{current_ticker}*..." if current_ticker else "Menyiapkan radar..."
    return (
        "🔎 *MORNING CONFLUENCE SCAN*\n"
        f"`[{bar}] {done}/{total} emiten ({pct}%)`\n"
        f"_{curr_txt}_"
    )


async def cmd_cek(message: Message) -> None:
    ticker = _extract_ticker_arg(message.text or "")
    if not ticker:
        await message.answer("Gunakan format: `/cek BBRI` atau ketik langsung kode saham (misal `ADRO`).")
        return

    wait_msg = await message.answer(_skeleton_ticker_loading(ticker, pct=35))
    res = await asyncio.to_thread(analyze_ticker, ticker)
    if not res.get("technicals"):
        await wait_msg.edit_text(f"❌ Data pasar untuk `{ticker}.JK` tidak ditemukan.")
        return
    try:
        await wait_msg.edit_text(_skeleton_ticker_loading(ticker, pct=80, step_note="Menyusun Sparkline & Risk Plan..."))
    except Exception:
        pass

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
    cap = store.get_capital(message.chat.id)
    spark_txt = await asyncio.to_thread(_build_sparkline_for_ticker, ticker, res.get("ohlcv_df"))
    await wait_msg.edit_text(format_ticker_alert(res, capital_idr=cap) + "\n\n" + spark_txt)


def _fetch_chart_series(ticker: str, fallback_ohlcv: Any = None) -> tuple[list[float], list[str], str]:
    """Fetches Stockbit intraday prices/labels, falling back to 24D daily OHLCV."""
    try:
        tok = load_active_token()
        if tok:
            intra = fetch_stockbit_intraday(ticker, token=tok, lookback_days=2)
            if intra is not None and not intra.empty and len(intra) >= 4:
                prices = intra["close"].astype(float).tolist()[-48:]
                dates_raw = intra["date"].astype(str).tolist()[-48:]
                t0 = dates_raw[0][-5:] if len(dates_raw[0]) >= 5 else "Open"
                t1 = dates_raw[-1][-5:] if len(dates_raw[-1]) >= 5 else "Now"
                return prices, [t0, t1], "Intraday"
    except Exception:
        pass

    df = fallback_ohlcv if (fallback_ohlcv is not None and not getattr(fallback_ohlcv, "empty", True)) else fetch_jk_ohlcv(ticker, range_str="1mo")
    if df is not None and not df.empty and len(df) >= 2:
        tail = df.tail(24)
        prices = tail["close"].astype(float).tolist()
        d0 = str(tail["date"].iloc[0])[5:10]
        d1 = str(tail["date"].iloc[-1])[5:10]
        return prices, [d0, d1], "24H"
    return [], [], "Intraday"


def _build_sparkline_for_ticker(ticker: str, fallback_ohlcv: Any = None) -> str:
    prices, _, subtitle = _fetch_chart_series(ticker, fallback_ohlcv=fallback_ohlcv)
    return render_sparkline_line(ticker, prices, subtitle=subtitle)


async def cmd_chart(message: Message) -> None:
    ticker = _extract_ticker_arg(message.text or "")
    if not ticker:
        await message.answer("Gunakan format: `/chart BBCA`")
        return
    wait_msg = await message.answer(
        f"📊 *MEMUAT GRAFIK | {ticker}*\n"
        "`[▓▓▓▓░░░░░░]` — _Mengambil data intraday Stockbit..._\n"
        "`████ | ░░░░░░░░░░░░░░`"
    )
    prices, labels, subtitle = await asyncio.to_thread(_fetch_chart_series, ticker)
    if len(prices) < 2:
        await wait_msg.edit_text(f"❌ Data grafik *{ticker}* belum tersedia.")
        return
    chart_txt = render_ascii_bar_chart(ticker, prices, labels=labels, subtitle=subtitle)
    await wait_msg.edit_text(chart_txt)


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


async def _send_morning_chart_cards(
    bot: Bot,
    chat_id: int,
    results: list[dict],
    capital_idr: float,
    max_cards: int = 3,
) -> None:
    """Sends visual PNG Morning View + Lead-Lag Broker Pattern cards for staging chat_ids."""
    if chat_id not in STAGING_CHAT_IDS:
        return
    ranked = sorted(results, key=lambda r: float(r.get("composite_score") or 0.0), reverse=True)[:max_cards]
    for res in ranked:
        ticker = res["ticker"]
        try:
            days = await asyncio.to_thread(store.list_broker_history_days, ticker, 30)
            if len(days) < 5:
                await asyncio.to_thread(backfill_broker_history, store, ticker, 10)
            hist_rows = await asyncio.to_thread(store.get_broker_daily_history, ticker, 60)
            ohlcv_df = res.get("ohlcv_df")
            pattern_res = analyze_broker_patterns(
                hist_rows,
                ohlcv_df=ohlcv_df,
                latest_broksum=res.get("stockbit_broksum"),
            )
            if ohlcv_df is None or ohlcv_df.empty:
                continue
            png_bytes = await asyncio.to_thread(
                render_morning_chart,
                ticker,
                ohlcv_df,
                res,
                pattern_res,
                capital_idr,
            )
            caption = (
                f"📊 *MORNING VIEW | {ticker}* ({res.get('badge', '')})\n"
                f"🔎 {pattern_res.get('headline', '-')}"
            )
            await bot.send_photo(
                chat_id,
                BufferedInputFile(png_bytes, filename=f"{ticker}_morning.png"),
                caption=caption[:1024],
            )
        except Exception as exc:
            logger.warning("Morning chart card failed for %s: %s", ticker, exc)


async def cmd_morning(message: Message) -> None:
    sample_tickers = store.list_watch(message.chat.id) or DEFAULT_UNIVERSE[:10]
    total = len(sample_tickers)
    wait_msg = await message.answer(_skeleton_scan_loading(0, total))
    cash_map = await asyncio.to_thread(fetch_cash_radar_map)

    results = []
    for idx, t in enumerate(sample_tickers, start=1):
        if idx == 1 or idx % 2 == 0 or idx == total:
            try:
                await wait_msg.edit_text(_skeleton_scan_loading(idx - 1, total, t))
            except Exception:
                pass
        res = await asyncio.to_thread(analyze_ticker, t, cash_map)
        if res.get("technicals"):
            results.append(res)

    results.sort(key=lambda r: r["composite_score"], reverse=True)
    top = results[:5]
    if not top:
        await wait_msg.edit_text("❌ Gagal mengambil data pasar saat ini.")
        return

    cap = store.get_capital(message.chat.id)
    header = f"🔔 *MORNING CONFLUENCE & DIRECTION RADAR*\nDipindai: {len(results)} emiten\n\n"
    body = "\n\n---\n\n".join(format_ticker_alert(r, capital_idr=cap) for r in top)
    await wait_msg.edit_text(header + body)
    if message.bot is not None:
        await _send_morning_chart_cards(message.bot, message.chat.id, results, cap, max_cards=3)


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
        wait_msg = await message.answer(_skeleton_ticker_loading(txt, pct=35))
        res = await asyncio.to_thread(analyze_ticker, txt)
        if not res.get("technicals"):
            await wait_msg.edit_text(f"❌ Data pasar untuk `{txt}.JK` tidak ditemukan.")
            return
        try:
            await wait_msg.edit_text(_skeleton_ticker_loading(txt, pct=80, step_note="Menyusun Sparkline & Risk Plan..."))
        except Exception:
            pass
        cap = store.get_capital(message.chat.id)
        spark_txt = await asyncio.to_thread(_build_sparkline_for_ticker, txt, res.get("ohlcv_df"))
        await wait_msg.edit_text(format_ticker_alert(res, capital_idr=cap) + "\n\n" + spark_txt)


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
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    for chat_id, tickers in subs.items():
        blocks = []
        analyzed_results = []
        cap = store.get_capital(chat_id)
        for t in tickers[:8]:
            res = await asyncio.to_thread(analyze_ticker, t, cash_map)
            if res.get("technicals"):
                analyzed_results.append(res)
                blocks.append(format_ticker_alert(res, capital_idr=cap))
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
                if alert_type == "evening":
                    try:
                        rows = await asyncio.to_thread(fetch_stockbit_broker_summary_for_date, t, today_str)
                        if rows:
                            await asyncio.to_thread(store.upsert_broker_daily, today_str, t, rows)
                    except Exception:
                        pass
        if blocks:
            title = "🔔 *MORNING ALERT (08:45 WIB)*" if alert_type == "morning" else "🌙 *REKAP SORE WATCHLIST (18:00 WIB)*"
            await bot.send_message(chat_id, title + "\n\n" + "\n\n---\n\n".join(blocks))
            if alert_type == "morning":
                await _send_morning_chart_cards(bot, chat_id, analyzed_results, cap, max_cards=3)


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


def _parse_capital_arg(raw: str) -> float | None:
    s = (raw or "").strip().lower().replace(",", "").replace(".", "").replace("rp", "").strip()
    if not s:
        return None
    mult = 1.0
    if s.endswith("jt"):
        mult = 1_000_000.0
        s = s[:-2].strip()
    elif s.endswith("m"):
        mult = 1_000_000_000.0
        s = s[:-1].strip()
    try:
        val = float(s) * mult
        return val if val >= 100_000 else None
    except ValueError:
        return None


async def cmd_modal(message: Message) -> None:
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        curr = store.get_capital(message.chat.id)
        curr_s = f"Rp {int(round(curr)):,}".replace(",", ".")
        await message.answer(
            f"💰 Modal aktif saat ini: `{curr_s}` (Risk `1%`/trade).\n"
            "Ubah dengan `/modal 50jt` atau `/modal 100000000`."
        )
        return
    parsed = _parse_capital_arg(parts[1])
    if parsed is None:
        await message.answer("❌ Format salah. Contoh: `/modal 50jt` atau `/modal 100000000` (min Rp 100.000).")
        return
    store.set_capital(message.chat.id, parsed)
    cap_s = f"Rp {int(round(parsed)):,}".replace(",", ".")
    await message.answer(f"✅ Modal Money Management diset ke `{cap_s}` (maks risk `1%`/trade, maks alokasi `25%`/saham).")


def build_dispatcher() -> Dispatcher:
    """Builds and wires all command & text message handlers."""
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start", "help"))
    dp.message.register(cmd_cek, Command("cek", "check"))
    dp.message.register(cmd_chart, Command("chart", "grafik"))
    dp.message.register(cmd_watch, Command("watch"))
    dp.message.register(cmd_unwatch, Command("unwatch"))
    dp.message.register(cmd_watchlist, Command("watchlist"))
    dp.message.register(cmd_morning, Command("morning"))
    dp.message.register(cmd_pola, Command("pola", "riwayat"))
    dp.message.register(cmd_modal, Command("modal"))
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

                    alerts_to_send: list[tuple[str, str]] = []
                    tb_raw: dict = {}
                    md_raw: dict = {}
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
                                alerts_to_send.append((format_orderbook_wall_alert(t, w), f"{w['side']}_WALL"))
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
                                alerts_to_send.append((format_wall_pulled_alert(t, pw), f"{pw['side']}_PULLED"))
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
                            alerts_to_send.append((format_tradebook_dominance_alert(dom), dom["side"]))
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
                            alerts_to_send.append((format_broker_flow_alert(bf), bf["signal"]))
                            store.log_mm_event(
                                t,
                                "BROKER_FLIP",
                                side=bf["signal"],
                                value_idr=abs(bf["non_retail_net_idr"]),
                                detail=f"Non-Ritel: {','.join(bf['non_retail_brokers'])}",
                            )
                    except Exception:
                        pass

                    for alert_txt, signal_kind in alerts_to_send:
                        for cid, user_tickers in subs.items():
                            if t in user_tickers:
                                analysis_txt = build_instant_signal_analysis(
                                    t,
                                    signal_kind,
                                    curr_ob=curr_ob,
                                    md_raw=md_raw,
                                    capital_idr=store.get_capital(cid),
                                )
                                sent_msg = await bot.send_message(cid, alert_txt)
                                await bot.send_message(
                                    cid,
                                    analysis_txt,
                                    reply_to_message_id=sent_msg.message_id,
                                )
        except Exception as exc:
            logger.warning("Orderbook monitor error: %s", exc)
        await asyncio.sleep(poll_seconds)


async def main() -> None:
    bot = create_bot()
    dp = build_dispatcher()

    try:
        await bot.set_my_commands([
            BotCommand(command="cek", description="Analisis saham & sentimen arah (misal /cek BBCA)"),
            BotCommand(command="chart", description="Grafik mini intraday real-time (ASCII)"),
            BotCommand(command="morning", description="Scan Morning Confluence watchlist"),
            BotCommand(command="watch", description="Tambah saham ke watchlist alert"),
            BotCommand(command="unwatch", description="Hapus saham dari watchlist"),
            BotCommand(command="watchlist", description="Lihat daftar watchlist aktif"),
            BotCommand(command="pola", description="Rekam pola market maker & orderbook hari ini"),
            BotCommand(command="modal", description="Atur modal untuk Risk:Reward & sizing lot"),
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
