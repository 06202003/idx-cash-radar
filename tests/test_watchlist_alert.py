"""
Unit tests for Watchlist Notification Engine & Alert Dispatcher.
Phase 2 Implementation verifying PRD Section 10.2 and AGENTS.md Section 7.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.bot.main import (
    format_user_watchlist_response,
    handle_unwatch,
    handle_watch,
    handle_watchlist,
)
from src.db.repository import FinancialRepository
from src.engine.llm_explainer import check_language_compliance
from src.engine.watchlist_alert import WatchlistAlertEngine
from src.models.metrics import (
    CashCoverageMetrics,
    ComputedFilingMetrics,
    ContractExposureMetrics,
    SafeguardEvaluation,
    SloanAccrualMetrics,
)


def create_sample_metrics(
    ticker: str = "WIKA",
    flag_acute_liquidity: bool = False,
    flag_accrual_divergence: bool = False,
) -> ComputedFilingMetrics:
    return ComputedFilingMetrics(
        filing_id=f"{ticker}_2025_FY_FIRST",
        ticker=ticker,
        period_end_date="2025-12-31",
        is_audit_derived_q4=True,
        contract_exposure=ContractExposureMetrics(
            gross_exposure_idr=Decimal("1000000000000"),
            net_exposure_idr=Decimal("800000000000"),
            revenue_ttm_idr=Decimal("2000000000000"),
            gross_contract_exposure_ratio=Decimal("0.50"),
        ),
        sloan_accrual=SloanAccrualMetrics(
            net_income_ttm_idr=(
                Decimal("50000000000") if flag_accrual_divergence else Decimal("-100000000000")
            ),
            cfo_ttm_idr=Decimal("-250000000000"),
            average_assets_idr=Decimal("10000000000000"),
            sloan_ratio_ttm=Decimal("0.15") if flag_accrual_divergence else Decimal("0.02"),
        ),
        cash_coverage=CashCoverageMetrics(
            cash_idr=Decimal("300000000000"),
            st_debt_idr=Decimal("2500000000000"),
            cash_coverage_ratio=Decimal("0.12") if flag_acute_liquidity else Decimal("0.85"),
            debt_free_short_term=False,
        ),
        safeguards=SafeguardEvaluation(
            flag_accrual_divergence=flag_accrual_divergence,
            flag_acute_liquidity=flag_acute_liquidity,
            status_summary=(
                "PERHATIAN" if (flag_acute_liquidity or flag_accrual_divergence) else "NORMAL"
            ),
        ),
    )


def test_add_and_remove_watchlist(tmp_path) -> None:
    db_file = tmp_path / "test_watch.db"
    repo = FinancialRepository(db_path=db_file)

    # 1. Add WIKA to user 123
    added = repo.add_to_watchlist("123", "WIKA")
    assert added is True

    # Duplicate should be ignored
    assert repo.add_to_watchlist("123", "WIKA") is False

    # Check watchlist
    wl = repo.get_user_watchlist("123")
    assert wl == ["WIKA"]

    # 2. Add TOTL
    repo.add_to_watchlist("123", "TOTL")
    assert sorted(repo.get_user_watchlist("123")) == ["TOTL", "WIKA"]

    # 3. Remove WIKA
    removed = repo.remove_from_watchlist("123", "WIKA")
    assert removed is True
    assert repo.get_user_watchlist("123") == ["TOTL"]


def test_get_subscribers_for_ticker(tmp_path) -> None:
    db_file = tmp_path / "test_subs.db"
    repo = FinancialRepository(db_path=db_file)

    repo.add_to_watchlist("user_1", "WIKA")
    repo.add_to_watchlist("user_2", "WIKA")
    repo.add_to_watchlist("user_3", "TOTL")

    subs_wika = repo.get_subscribers_for_ticker("WIKA")
    assert len(subs_wika) == 2
    assert "user_1" in subs_wika
    assert "user_2" in subs_wika

    subs_totl = repo.get_subscribers_for_ticker("TOTL")
    assert subs_totl == ["user_3"]


def test_watchlist_alert_triggers_critical_for_acute_liquidity() -> None:
    engine = WatchlistAlertEngine()
    metrics = create_sample_metrics("WIKA", flag_acute_liquidity=True)
    alerts = engine.evaluate_filing_for_alerts(metrics, "Wijaya Karya")

    assert len(alerts) >= 1
    crit_alert = next((a for a in alerts if a.alert_level == "CRITICAL"), None)
    assert crit_alert is not None
    assert "PERINGATAN LIKUIDITAS" in crit_alert.title
    assert "WIKA" in crit_alert.title
    assert check_language_compliance(crit_alert.message) is True


def test_watchlist_alert_triggers_warning_for_accrual_divergence() -> None:
    engine = WatchlistAlertEngine()
    metrics = create_sample_metrics("PTPP", flag_accrual_divergence=True)
    alerts = engine.evaluate_filing_for_alerts(metrics, "PP (Persero)")

    assert len(alerts) >= 1
    warn_alert = next((a for a in alerts if a.alert_level == "WARNING"), None)
    assert warn_alert is not None
    assert "PERINGATAN DIVERGENSI AKRUAL" in warn_alert.title
    assert check_language_compliance(warn_alert.message) is True


def test_watchlist_alert_info_for_healthy_issuer() -> None:
    engine = WatchlistAlertEngine()
    metrics = create_sample_metrics("TOTL")
    metrics.cash_coverage.debt_free_short_term = True
    alerts = engine.evaluate_filing_for_alerts(metrics, "Total Bangun Persada")

    assert len(alerts) == 1
    assert alerts[0].alert_level == "INFO"
    assert "Bebas utang" in alerts[0].message
    assert check_language_compliance(alerts[0].message) is True


def test_format_telegram_alert() -> None:
    engine = WatchlistAlertEngine()
    metrics = create_sample_metrics("WIKA", flag_acute_liquidity=True)
    alerts = engine.evaluate_filing_for_alerts(metrics, "Wijaya Karya")
    formatted = alerts[0].format_telegram_alert()

    assert "🚨" in formatted
    assert "WIKA" in formatted
    assert "FY 2025" in formatted
    assert "/check WIKA" in formatted


def test_format_user_watchlist_response(tmp_path) -> None:
    db_file = tmp_path / "test_resp.db"
    repo = FinancialRepository(db_path=db_file)

    # Empty watchlist
    empty_resp = format_user_watchlist_response("usr_empty", repo)
    assert "KOSONG" in empty_resp

    # Populated watchlist
    repo.add_to_watchlist("usr_1", "WIKA")
    pop_resp = format_user_watchlist_response("usr_1", repo)
    assert "WATCHLIST RADAR EMITEN PRIBADI" in pop_resp
    assert "WIKA" in pop_resp


def test_bot_handlers_watch_and_unwatch(tmp_path) -> None:
    message = MagicMock()
    message.from_user.id = 999
    message.text = "/watch WIKA"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_watch(message))
    message.answer.assert_called_once()
    assert "ditambahkan ke watchlist" in message.answer.call_args[0][0]

    # Test /watchlist
    message.text = "/watchlist"
    message.answer = AsyncMock()
    asyncio.run(handle_watchlist(message))
    message.answer.assert_called_once()
    assert "WIKA" in message.answer.call_args[0][0]

    # Test /unwatch WIKA
    message.text = "/unwatch WIKA"
    message.answer = AsyncMock()
    asyncio.run(handle_unwatch(message))
    message.answer.assert_called_once()
    assert "dihapus dari watchlist" in message.answer.call_args[0][0]
