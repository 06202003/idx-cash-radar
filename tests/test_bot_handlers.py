"""
Unit tests for Telegram Bot handlers and response formatting.
Strictly verifies Section 8 and Section 10 of AGENTS.md.
Enhanced for professional executive commands: /check, /ticker, /top, /compare, /trend.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.bot.main import (
    format_bot_response_for_ticker,
    format_comparison_response,
    format_leaderboard_response,
    format_news_response,
    format_ticker_list_response,
    format_trend_response,
    get_action_inline_keyboard,
    get_main_reply_keyboard,
    handle_callback_router,
    handle_check,
    handle_compare,
    handle_help,
    handle_start,
    handle_text_router,
    handle_ticker,
    handle_top,
    handle_trend,
)
from src.db.repository import FinancialRepository


def test_format_bot_response_out_of_scope_ticker(tmp_path):
    db_file = tmp_path / "test_bot.db"
    repo = FinancialRepository(db_path=db_file)

    # Ask for BBCA which is out of scope / not in DB
    response = format_bot_response_for_ticker("BBCA", repo)

    assert "INFORMASI CAKUPAN EMITEN" in response
    assert "BBCA" in response
    assert "Konstruksi Bangunan" in response

    # Check that demand was logged
    with repo.get_connection() as conn:
        rows = conn.execute("SELECT ticker FROM demand_log;").fetchall()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "BBCA"


def test_format_bot_response_real_construction_ticker():
    # Use live database if populated
    repo = FinancialRepository()
    issuer = repo.get_issuer("WIKA")
    if not issuer:
        return

    response = format_bot_response_for_ticker("WIKA", repo)

    assert "DIAGNOSTIK KAS & AKRUAL EMITEN" in response
    assert "WIKA" in response
    assert "Wijaya Karya" in response
    assert "AUDIT TRAIL DATA BEI" in response


def test_format_ticker_list_response():
    repo = FinancialRepository()
    response = format_ticker_list_response(repo)

    assert "DIREKTORI EMITEN TERCAKUP" in response
    assert "WIKA" in response
    assert "TOTL" in response
    assert "/check" in response


def test_format_leaderboard_response():
    repo = FinancialRepository()
    response = format_leaderboard_response(repo)

    assert "KLASEMEN SOLVABILITAS KAS SEKTOR KONSTRUKSI" in response
    assert "Emiten" in response
    assert "TOTL" in response or "PBSA" in response


def test_format_comparison_response():
    repo = FinancialRepository()
    response = format_comparison_response("WIKA", "TOTL", repo)

    assert "KOMPARASI HEAD-TO-HEAD KETAHANAN KAS" in response
    assert "WIKA" in response
    assert "TOTL" in response
    assert "Kas & Setara Kas" in response


def test_format_trend_response():
    repo = FinancialRepository()
    response = format_trend_response("WIKA", repo)

    assert "EVOLUSI TREN KEUANGAN: WIKA" in response
    assert "2022" in response
    assert "2025" in response


def test_format_news_response():
    response = format_news_response("WIKA")
    assert "SENTIMEN BERITA & KETERBUKAAN BEI: WIKA" in response


def test_keyboards_structure():
    reply_kb = get_main_reply_keyboard()
    assert reply_kb.resize_keyboard is True
    assert len(reply_kb.keyboard) >= 3
    # Check that no raw /cek ticker is hardcoded in buttons
    for row in reply_kb.keyboard:
        for btn in row:
            assert "/cek" not in btn.text

    inline_kb = get_action_inline_keyboard("WIKA")
    assert len(inline_kb.inline_keyboard) >= 2
    callbacks = [btn.callback_data for row in inline_kb.inline_keyboard for btn in row]
    assert "trend:WIKA" in callbacks
    assert "top" in callbacks
    assert "calk:WIKA" in callbacks


def test_handle_start():
    message = MagicMock()
    message.answer = AsyncMock()

    asyncio.run(handle_start(message))

    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "SELAMAT DATANG DI IDX CASH & ACCRUAL RADAR" in args[0]
    assert "/check" in args[0]
    assert "/ticker" in args[0]
    assert kwargs.get("reply_markup") is not None


def test_handle_help():
    message = MagicMock()
    message.answer = AsyncMock()

    asyncio.run(handle_help(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "PANDUAN LENGKAP IDX CASH & ACCRUAL RADAR" in args[0]
    assert "Intensitas Eksposur Kontrak PSAK 72" in args[0]


def test_handle_ticker():
    message = MagicMock()
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_ticker(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "DIREKTORI EMITEN TERCAKUP" in args[0]


def test_handle_check_invalid_args():
    message = MagicMock()
    message.text = "/check"
    message.answer = AsyncMock()

    asyncio.run(handle_check(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Format salah" in args[0]


def test_handle_check_valid_ticker():
    message = MagicMock()
    message.text = "/check BBCA"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_check(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "INFORMASI CAKUPAN EMITEN" in args[0]
    assert "BBCA" in args[0]


def test_handle_top():
    message = MagicMock()
    message.text = "/top"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_top(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "KLASEMEN SOLVABILITAS KAS SEKTOR KONSTRUKSI" in args[0]


def test_handle_compare():
    message = MagicMock()
    message.text = "/compare WIKA TOTL"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_compare(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "KOMPARASI HEAD-TO-HEAD" in args[0]


def test_handle_trend():
    message = MagicMock()
    message.text = "/trend WIKA"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_trend(message))

    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "EVOLUSI TREN KEUANGAN: WIKA" in args[0]


def test_handle_callback_router():
    cb_top = MagicMock()
    cb_top.data = "top"
    cb_top.answer = AsyncMock()
    cb_top.message = MagicMock()
    cb_top.message.answer = AsyncMock()

    asyncio.run(handle_callback_router(cb_top))
    cb_top.answer.assert_called_once()
    cb_top.message.answer.assert_called_once()
    args, _ = cb_top.message.answer.call_args
    assert "KLASEMEN SOLVABILITAS" in args[0]


def test_handle_text_router():
    message = MagicMock()
    message.text = "TOTL"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_text_router(message))
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "TOTL" in args[0]
