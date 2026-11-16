"""
Telegram Bot Interface using aiogram 3.x.
Strictly implements Section 8 and Section 10 of AGENTS.md.
Enhanced with executive commands: /check, /ticker, /top, /compare, /trend.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import socket
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import Command
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Force IPv4 and fast direct DNS resolution for api.telegram.org to prevent
# Windows DNS semaphore timeouts ([WinError 121]) and ISP IPv6 drops
_orig_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
    if host == "api.telegram.org":
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("149.154.166.110", port))]
    res = _orig_getaddrinfo(host, port, *args, **kwargs)
    ipv4 = [r for r in res if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else res


socket.getaddrinfo = _patched_getaddrinfo

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_case_evaluation import evaluate_filing  # noqa: E402
from src.db.repository import FinancialRepository  # noqa: E402
from src.engine.calk_extractor import CALKFootnoteExtractor  # noqa: E402
from src.engine.cohort import evaluate_cohort_rank  # noqa: E402
from src.engine.llm_explainer import AIExecutiveExplainer  # noqa: E402
from src.engine.news_radar import NewsRadar  # noqa: E402
from src.engine.rag_chat import RAGFinancialChatbot  # noqa: E402
from src.engine.watchlist_alert import WatchlistAlertEngine  # noqa: E402
from src.parser.dynamic_ingestor import DynamicXBRLIngestor  # noqa: E402
from src.renderer.card_renderer import DiagnosticCardRenderer  # noqa: E402
from src.renderer.formatter import format_decimal_id, format_idr_nominal  # noqa: E402

dp = Dispatcher()
renderer = DiagnosticCardRenderer()
repo = FinancialRepository()
explainer = AIExecutiveExplainer()
news_radar = NewsRadar()
calk_extractor = CALKFootnoteExtractor()
rag_chatbot = RAGFinancialChatbot(repository=repo, news_radar=news_radar)
alert_engine = WatchlistAlertEngine(repository=repo)
dynamic_ingestor = DynamicXBRLIngestor(repo=repo)


def get_main_reply_keyboard() -> types.ReplyKeyboardMarkup:
    """Creates a sleek, executive navigation keyboard without hardcoded ticker spam."""
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="🔍 Check Emiten"),
                types.KeyboardButton(text="🏆 Top Leaderboard"),
            ],
            [
                types.KeyboardButton(text="⚖️ Compare Peers"),
                types.KeyboardButton(text="📈 Trend 4 Tahun"),
            ],
            [
                types.KeyboardButton(text="⭐ Watchlist Pantauan"),
                types.KeyboardButton(text="🏛️ Daftar Ticker"),
            ],
            [
                types.KeyboardButton(text="📖 Panduan & Metodologi"),
            ],
        ],
        resize_keyboard=True,
        persistent=True,
        input_field_placeholder="Ketik /check <KODE> (contoh: /check WIKA)...",
    )


def get_action_inline_keyboard(ticker: str) -> types.InlineKeyboardMarkup:
    """Creates interactive inline action buttons attached to diagnostic cards."""
    peer_compare = "WIKA" if ticker.upper() == "TOTL" else "TOTL"
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📈 Trend 4Y", callback_data=f"trend:{ticker}"
                ),
                types.InlineKeyboardButton(
                    text="🏆 Top 12", callback_data="top"
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text=f"⚖️ Compare vs {peer_compare}",
                    callback_data=f"compare:{ticker}:{peer_compare}",
                ),
                types.InlineKeyboardButton(
                    text="📰 Live News", callback_data=f"news:{ticker}"
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text="📋 CALK Footnote", callback_data=f"calk:{ticker}"
                ),
                types.InlineKeyboardButton(
                    text="⭐ Watch Radar", callback_data=f"watch:{ticker}"
                ),
            ],
        ]
    )


def format_bot_response_for_ticker(ticker_str: str, repository: FinancialRepository) -> str:
    """Core deterministic handler for generating diagnostic responses."""
    ticker = ticker_str.strip().upper()
    issuer = repository.get_issuer(ticker)

    # Check if issuer exists
    if not issuer:
        repository.log_demand(ticker)
        return renderer.render_empty_state_card(ticker)

    sub_ind = issuer.idx_sub_industry.lower()
    is_fmcg = any(
        k in sub_ind for k in ["fmcg", "makanan", "perawatan", "ritel", "farmasi"]
    )
    is_banking = any(k in sub_ind for k in ["bank", "keuangan"])

    # Find latest filing for this issuer
    query = """
    SELECT filing_id FROM filings
    WHERE ticker = ? ORDER BY fiscal_year DESC, period_code DESC LIMIT 1;
    """
    with repository.get_connection() as conn:
        row = conn.execute(query, (ticker,)).fetchone()

    if not row:
        repository.log_demand(ticker)
        return renderer.render_empty_state_card(ticker)

    filing_id = row["filing_id"]
    fiscal_yr = filing_id.split("_")[1]

    # Sector Routing: FMCG
    if is_fmcg:
        facts = repository.get_canonical_facts(filing_id)

        def get_fmcg_val(k: str, default: str = "0") -> Decimal:
            return Decimal(facts[k].value_idr) if k in facts else Decimal(default)

        return renderer.render_fmcg_card(
            ticker=ticker,
            company_name=issuer.company_name,
            sub_industry=issuer.idx_sub_industry,
            fiscal_year=fiscal_yr,
            cfo_val=get_fmcg_val("cfo"),
            ni_val=get_fmcg_val("net_income"),
            cash_val=get_fmcg_val("cash_and_equivalents"),
            debt_val=get_fmcg_val("st_debt_bank_loans"),
            rec_val=get_fmcg_val("trade_receivables_third_parties"),
            inv_val=get_fmcg_val("inventories"),
            rev_val=get_fmcg_val("revenue"),
        )

    # Sector Routing: Banking
    if is_banking:
        facts = repository.get_canonical_facts(filing_id)

        def get_bank_val(k: str, default: str = "0") -> Decimal:
            return Decimal(facts[k].value_idr) if k in facts else Decimal(default)

        return renderer.render_banking_card(
            ticker=ticker,
            company_name=issuer.company_name,
            sub_industry=issuer.idx_sub_industry,
            fiscal_year=fiscal_yr,
            cash_val=get_bank_val("cash_and_equivalents"),
            dpk_val=get_bank_val("customer_deposits"),
            loans_val=get_bank_val("loans_gross"),
            npl_val=get_bank_val("non_performing_loans"),
            rev_val=get_bank_val("revenue"),
            ni_val=get_bank_val("net_income"),
            cfo_val=get_bank_val("cfo"),
        )

    # Sector Routing: Construction (PSAK 72)
    metrics = evaluate_filing(filing_id, repository)
    if not metrics:
        return f"⚠️ Data metrik belum siap untuk emiten {ticker}."

    # Compute cohort ranks against all peers for this filing period
    query_peers = """
    SELECT cm.ticker, cm.gross_contract_exposure_ratio, cm.sloan_ratio_ttm, cm.cash_coverage_ratio
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    WHERE f.period_end_date = ?;
    """
    with repository.get_connection() as conn:
        peer_rows = conn.execute(query_peers, (metrics.period_end_date,)).fetchall()

    if peer_rows:
        def to_dec(val: Any) -> Decimal | None:
            if val is None:
                return None
            try:
                return Decimal(str(val))
            except Exception:
                return None

        gross_dict = {
            r["ticker"]: to_dec(r["gross_contract_exposure_ratio"]) for r in peer_rows
        }
        sloan_dict = {r["ticker"]: to_dec(r["sloan_ratio_ttm"]) for r in peer_rows}
        cov_dict = {r["ticker"]: to_dec(r["cash_coverage_ratio"]) for r in peer_rows}

        metrics.cohort_ranks["contract_exposure"] = evaluate_cohort_rank(
            "gross_contract_exposure_ratio", ticker, gross_dict, higher_is="higher"
        )
        metrics.cohort_ranks["sloan_accrual"] = evaluate_cohort_rank(
            "sloan_ratio_ttm", ticker, sloan_dict, higher_is="higher"
        )
        metrics.cohort_ranks["cash_coverage"] = evaluate_cohort_rank(
            "cash_coverage_ratio", ticker, cov_dict, higher_is="lower"
        )

    # Contextual news & disclosure sentiment radar (Gate 7)
    news_items = news_radar.get_news_for_ticker(ticker)

    # Generate human-friendly executive narrative via Gemini (or deterministic fallback)
    ai_narrative = explainer.explain(metrics, issuer.company_name, news_items=news_items)

    return renderer.render_construction_card(
        metrics=metrics,
        company_name=issuer.company_name,
        repo=repository,
        ai_narrative=ai_narrative,
        news_items=news_items,
    )


def format_ticker_list_response(repository: FinancialRepository) -> str:
    """Builds directory of all covered issuers across sectors in IDX."""
    query = """
    SELECT ticker, company_name, idx_sub_industry
    FROM issuers
    ORDER BY ticker ASC;
    """
    with repository.get_connection() as conn:
        rows = conn.execute(query).fetchall()

    if not rows:
        return "⚠️ Belum ada daftar emiten yang tercatat di database."

    constr = [r for r in rows if "konstruksi" in r["idx_sub_industry"].lower()]
    fmcg_keywords = ["fmcg", "makanan", "perawatan", "ritel", "farmasi"]
    fmcg = [
        r for r in rows
        if any(k in r["idx_sub_industry"].lower() for k in fmcg_keywords)
    ]
    bank = [
        r for r in rows
        if any(k in r["idx_sub_industry"].lower() for k in ["bank", "keuangan"])
    ]
    energy_keywords = ["energi", "tambang", "minyak", "gas", "mineral", "bahan bakar"]
    energy = [
        r for r in rows
        if any(k in r["idx_sub_industry"].lower() for k in energy_keywords)
    ]
    telco_keywords = ["telekomunikasi", "menara"]
    telco = [
        r for r in rows
        if any(k in r["idx_sub_industry"].lower() for k in telco_keywords)
    ]

    lines = [
        "🏛️ DIREKTORI EMITEN TERCAKUP (MULTI-SEKTOR BEI)",
        "━" * 42,
        f"Total Semesta: {len(rows)} Emiten Terverifikasi Data XBRL\n",
        f"🏗️ Sub-Industri Konstruksi Bangunan & Rekayasa Sipil ({len(constr)}):",
    ]
    for idx, r in enumerate(constr, start=1):
        lines.append(f" {idx:2d}. {r['ticker']} — {r['company_name']}")

    if fmcg:
        lines.append(f"\n🛒 Sektor Barang Konsumen, Farmasi & Ritel ({len(fmcg)}):")
        for idx, r in enumerate(fmcg, start=1):
            lines.append(f" {idx:2d}. {r['ticker']} — {r['company_name']}")

    if bank:
        lines.append(f"\n🏦 Sektor Perbankan & Jasa Keuangan ({len(bank)}):")
        for idx, r in enumerate(bank, start=1):
            lines.append(f" {idx:2d}. {r['ticker']} — {r['company_name']}")

    if energy:
        lines.append(f"\n⚡ Sektor Energi, Tambang & Komoditas ({len(energy)}):")
        for idx, r in enumerate(energy, start=1):
            lines.append(f" {idx:2d}. {r['ticker']} — {r['company_name']}")

    if telco:
        lines.append(f"\n📱 Sektor Telekomunikasi & Menara Digital ({len(telco)}):")
        for idx, r in enumerate(telco, start=1):
            lines.append(f" {idx:2d}. {r['ticker']} — {r['company_name']}")

    lines.append("\n" + "━" * 42)
    lines.append("💡 Format Perintah Analisis:")
    lines.append("• /check <KODE>       — Diagnostik kas (contoh: /check TOTL, /check ICBP)")
    lines.append("• /compare <K1> <K2>  — Head-to-head (contoh: /compare WIKA TOTL)")
    lines.append("• /trend <KODE>       — Riwayat 4 tahun (contoh: /trend WIKA)")
    return "\n".join(lines)


def format_leaderboard_response(repository: FinancialRepository) -> str:
    """Builds solvency leaderboard for all 12 construction issuers (FY 2025)."""
    query = """
    SELECT cm.ticker, i.company_name, cm.cash_coverage_ratio, cm.debt_free_short_term,
           cm.sloan_ratio_ttm, cm.cfo_ttm_idr, cm.flag_acute_liquidity, cm.flag_accrual_divergence
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    WHERE f.fiscal_year = 2025 AND LOWER(i.idx_sub_industry) LIKE '%konstruksi%';
    """
    with repository.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query).fetchall()]

    if not rows:
        return "⚠️ Data klasemen untuk FY 2025 belum tersedia di database."

    def sort_key(item: dict[str, Any]) -> tuple[int, float]:
        is_safe = 0 if item.get("flag_acute_liquidity") else 1
        is_free = 1 if item.get("debt_free_short_term") else 0
        cov = item.get("cash_coverage_ratio")
        cov_num = float(cov) if cov is not None else 0.0
        effective_cov = 9999.0 if is_free else cov_num
        return (is_safe, effective_cov)

    sorted_rows = sorted(rows, key=sort_key, reverse=True)

    items: list[dict[str, Any]] = []
    for idx, r in enumerate(sorted_rows, start=1):
        rank_icon = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else "🔹"))
        cov_val = r["cash_coverage_ratio"]
        free = bool(r["debt_free_short_term"])
        sloan_val = r["sloan_ratio_ttm"]

        if free:
            cov_disp = "Bebas Utang Jk. Pendek 🟢"
        elif cov_val is not None:
            c_dec = Decimal(str(cov_val))
            cov_disp = f"{format_decimal_id(c_dec, 2)}x"
        else:
            cov_disp = "N/A"

        if sloan_val is not None:
            s_dec = Decimal(str(sloan_val))
            tag = "(Arus Kas Solid 🟢)" if s_dec < Decimal("0") else "(Akrual 🟡)"
            sloan_disp = f"{format_decimal_id(s_dec * 100, 1)}% {tag}"
        else:
            sloan_disp = "N/A"

        if r["flag_acute_liquidity"]:
            status_badge = "🔴 TEKANAN LIKUIDITAS"
        elif r["flag_accrual_divergence"]:
            status_badge = "🟡 DIVERGENSI AKRUAL"
        else:
            status_badge = "🟢 AMAN & SOLID"

        items.append({
            "rank": idx,
            "rank_icon": rank_icon,
            "ticker": r["ticker"],
            "company_name": r["company_name"],
            "coverage_display": cov_disp,
            "sloan_display": sloan_disp,
            "status_badge": status_badge,
        })

    return renderer.render_leaderboard_card(items, fiscal_year=2025)


def format_comparison_response(
    ticker1_str: str, ticker2_str: str, repository: FinancialRepository
) -> str:
    """Builds side-by-side comparative analysis between two construction issuers."""
    t1 = ticker1_str.strip().upper()
    t2 = ticker2_str.strip().upper()

    iss1 = repository.get_issuer(t1)
    iss2 = repository.get_issuer(t2)

    if not iss1 or "konstruksi" not in iss1.idx_sub_industry.lower():
        return f"⚠️ Emiten {t1} belum tercakup dalam semesta data Konstruksi Bangunan."
    if not iss2 or "konstruksi" not in iss2.idx_sub_industry.lower():
        return f"⚠️ Emiten {t2} belum tercakup dalam semesta data Konstruksi Bangunan."

    query = (
        "SELECT filing_id FROM filings "
        "WHERE ticker = ? ORDER BY fiscal_year DESC, period_code DESC LIMIT 1;"
    )
    with repository.get_connection() as conn:
        r1 = conn.execute(query, (t1,)).fetchone()
        r2 = conn.execute(query, (t2,)).fetchone()

    if not r1 or not r2:
        return f"⚠️ Data laporan keuangan belum lengkap untuk membandingkan {t1} vs {t2}."

    m1 = evaluate_filing(r1["filing_id"], repository)
    m2 = evaluate_filing(r2["filing_id"], repository)

    if not m1 or not m2:
        return f"⚠️ Gagal menghitung metrik untuk perbandingan {t1} vs {t2}."

    ai_narrative = explainer.explain_comparison(m1, iss1.company_name, m2, iss2.company_name)

    return renderer.render_comparison_card(
        m1=m1,
        name1=iss1.company_name,
        m2=m2,
        name2=iss2.company_name,
        ai_narrative=ai_narrative,
        fiscal_year=2025,
    )


def format_trend_response(ticker_str: str, repository: FinancialRepository) -> str:
    """Builds 4-year evolution trend card (2022-2025) for a given issuer."""
    ticker = ticker_str.strip().upper()
    issuer = repository.get_issuer(ticker)
    if not issuer or "konstruksi" not in issuer.idx_sub_industry.lower():
        return f"⚠️ Emiten {ticker} belum tercakup dalam semesta data Konstruksi Bangunan."

    query = """
    SELECT f.fiscal_year, f.filing_id, cm.cash_coverage_ratio, cm.debt_free_short_term,
           cm.sloan_ratio_ttm, cm.cfo_ttm_idr, cm.flag_acute_liquidity, cm.flag_accrual_divergence
    FROM filings f
    LEFT JOIN computed_metrics cm ON f.filing_id = cm.filing_id
    WHERE f.ticker = ?
    ORDER BY f.fiscal_year ASC;
    """
    with repository.get_connection() as conn:
        rows = conn.execute(query, (ticker,)).fetchall()

    if not rows:
        return f"⚠️ Data historis untuk {ticker} belum ditemukan di basis data."

    history: list[dict[str, Any]] = []
    for r in rows:
        yr = r["fiscal_year"]
        cfo_raw = r["cfo_ttm_idr"]
        cov_raw = r["cash_coverage_ratio"]
        sloan_raw = r["sloan_ratio_ttm"]

        cfo_val = Decimal(str(cfo_raw)) if cfo_raw is not None else Decimal("0")
        cov_val = Decimal(str(cov_raw)) if cov_raw is not None else None
        sloan_val = Decimal(str(sloan_raw)) if sloan_raw is not None else None
        debt_free = bool(r["debt_free_short_term"])
        flag_acute = bool(r["flag_acute_liquidity"])
        flag_accrual = bool(r["flag_accrual_divergence"])

        cfo_str = format_idr_nominal(cfo_val)
        if debt_free:
            cov_str = "Bebas Utang Jk. Pendek 🟢"
        elif cov_val is not None:
            cov_str = f"{format_decimal_id(cov_val, 2)}x"
        else:
            cov_str = "N/A"

        sloan_str = f"{format_decimal_id(sloan_val * 100, 1)}%" if sloan_val is not None else "N/A"

        if flag_acute:
            badge = "🔴 TEKANAN LIKUIDITAS"
        elif flag_accrual:
            badge = "🟡 DIVERGENSI AKRUAL"
        else:
            badge = "🟢 NORMAL / AMAN"

        history.append({
            "fiscal_year": yr,
            "cfo_ttm_idr": cfo_val,
            "cash_coverage_ratio": cov_val,
            "debt_free_short_term": debt_free,
            "cfo_str": cfo_str,
            "cov_str": cov_str,
            "sloan_str": sloan_str,
            "status_badge": badge,
        })

    ai_narrative = explainer.explain_trend(ticker, issuer.company_name, history)
    return renderer.render_trend_card(ticker, issuer.company_name, history, ai_narrative)


def format_news_response(ticker_str: str) -> str:
    """Formats standalone news digest for quick refresh button."""
    ticker = ticker_str.strip().upper()
    news_items = news_radar.get_news_for_ticker(ticker)
    if not news_items:
        return f"📰 Belum ada pengumuman keterbukaan informasi baru untuk {ticker}."

    lines = [
        f"📰 SENTIMEN BERITA & KETERBUKAAN BEI: {ticker}",
        "━" * 42,
    ]
    for it in news_items:
        s = getattr(it, "sentiment", "NETRAL")
        h = getattr(it, "headline", str(it))
        d = getattr(it, "date", "")
        icon = "🟢" if s == "POSITIF" else ("🔴" if s == "PERHATIAN" else "🟡")
        lines.append(f"{icon} [{s}] {d}\n   {h}\n")
    lines.append("━" * 42)
    lines.append(
        "💡 Sentimen bursa berfungsi sebagai konteks sekunder dan tidak mengubah "
        "evaluasi kas deterministik."
    )
    return "\n".join(lines)


def format_calk_response(ticker_str: str, repository: FinancialRepository) -> str:
    """Formats CALK footnote breakdown with deterministic verbatim grounding verification."""
    ticker = ticker_str.strip().upper()
    issuer = repository.get_issuer(ticker)
    if not issuer or "konstruksi" not in issuer.idx_sub_industry.lower():
        return f"⚠️ Emiten {ticker} belum terdaftar dalam semesta sektor konstruksi."

    samples_dir = ROOT_DIR / "data" / "calk_samples"
    candidate_files = list(samples_dir.glob(f"{ticker}_*.txt"))

    if candidate_files:
        source_text = candidate_files[0].read_text(encoding="utf-8")
        if "Catatan 8" in source_text:
            footnote_num = "Catatan 8"
        elif "Catatan 7" in source_text:
            footnote_num = "Catatan 7"
        else:
            footnote_num = "Catatan Kaki"
        extraction = calk_extractor.extract_from_text(
            ticker=ticker,
            fiscal_year=2023,
            source_text=source_text,
            footnote_number=footnote_num,
            footnote_title="Piutang Usaha & Aset Kontrak",
            page_number=45,
            target_context="receivables",
        )
        return renderer.render_calk_card(extraction)

    return (
        f"📋 Catatan kaki CALK untuk {ticker} belum diunggah ke arsip lokal.\n"
        f"💡 Contoh terverifikasi yang saat ini aktif: /calk WIKA atau /calk TOTL."
    )


def format_user_watchlist_response(user_id: str, repository: FinancialRepository) -> str:
    """Formats personalized alert watchlist summary for user."""
    tickers = repository.get_user_watchlist(user_id)
    if not tickers:
        return (
            "⭐ WATCHLIST RADAR PRIBADI KOSONG\n"
            "━" * 40 + "\n"
            "Anda belum memantau emiten apa pun.\n"
            "👉 Gunakan `/watch <KODE>` untuk memantau emiten (contoh: `/watch WIKA`).\n"
            "Sistem akan memantau rilis laporan keuangan & risiko kas secara otomatis."
        )

    lines = [
        "⭐ WATCHLIST RADAR EMITEN PRIBADI",
        "━" * 40,
        f"Total emiten dipantau: {len(tickers)} emiten\n",
    ]
    for t in tickers:
        query = """
        SELECT cm.cash_coverage_ratio, cm.debt_free_short_term,
               cm.flag_acute_liquidity, cm.flag_accrual_divergence
        FROM computed_metrics cm
        JOIN filings f ON cm.filing_id = f.filing_id
        WHERE cm.ticker = ? ORDER BY f.fiscal_year DESC LIMIT 1;
        """
        with repository.get_connection() as conn:
            row = conn.execute(query, (t,)).fetchone()
        if row:
            if row["flag_acute_liquidity"]:
                badge = "🔴 TEKANAN KAS"
            elif row["flag_accrual_divergence"]:
                badge = "🟡 DIVERGENSI AKRUAL"
            else:
                badge = "🟢 AMAN & SOLID"
            cov = "Bebas Utang" if row["debt_free_short_term"] else f"{row['cash_coverage_ratio']}x"
            lines.append(f"• **{t}**: {badge} (Solvabilitas: {cov})")
        else:
            lines.append(f"• **{t}**: Terdaftar dalam pantauan")

    lines.append("\n" + "━" * 40)
    lines.append("💡 Perintah Pantauan:")
    lines.append("• `/check <KODE>`   — Buka diagnostik lengkap")
    lines.append("• `/unwatch <KODE>` — Hapus emiten dari daftar")
    return "\n".join(lines)


@dp.message(Command("start", ignore_case=True))
async def handle_start(message: types.Message) -> None:
    """Handles /start command with executive greeting and instructions."""
    text = (
        "🚀 SELAMAT DATANG DI IDX CASH & ACCRUAL RADAR (v2.0)\n"
        "Asisten pintar pemeriksa kesehatan keuangan & kas riil emiten Konstruksi BEI.\n\n"
        "💡 Kenapa Radar Ini Penting untuk Anda?\n"
        "Banyak emiten mencatat laba miliaran, tetapi uang kas belum tentu ada di rekening "
        "karena masih tertahan di tagihan proyek. Radar ini membantu investor awam membedakan\n"
        "mana emiten yang benar-benar pegang kas nyata dan mana yang kasnya sedang mepet!\n\n"
        "📌 Menu Perintah Cepat:\n"
        "• /check <KODE>       — Cek kesehatan kas saham (contoh: /check WIKA atau /check TOTL)\n"
        "• /ticker             — Daftar 12 emiten konstruksi yang tercakup\n"
        "• /top                — Klasemen kas terbaik dan paling aman (FY 2025)\n"
        "• /compare <K1> <K2>  — Bandingkan kas 2 emiten (contoh: /compare WIKA TOTL)\n"
        "• /trend <KODE>       — Riwayat tren kas & utang 4 tahun (2022–2025)\n"
        "• /calk <KODE>        — Rincian proyek berelasi & cadangan piutang di catatan kaki\n"
        "• /watch <KODE>       — Pasang alarm pantauan otomatis jika kas emiten bermasalah\n"
        "• /ask <PERTANYAAN>   — Konsultasi santai dengan AI berbasis data resmi BEI\n"
        "• /help               — Panduan cara baca istilah untuk pemula\n\n"
        "💬 Fitur Tanya Jawab Bebas (RAG):\n"
        "Ketik pertanyaan santai apa saja di chat ini (misal: 'Kenapa kas TOTL aman?',\n"
        "'Apa bedanya laba akrual dengan arus kas?'), AI akan menjawab berbasis data BEI.\n\n"
        "Gunakan menu tombol di bawah atau ketik kode saham langsung:"
    )
    await message.answer(text, reply_markup=get_main_reply_keyboard())


@dp.message(Command("help", ignore_case=True))
async def handle_help(message: types.Message) -> None:
    """Handles /help command with methodology details."""
    text = (
        "📖 PANDUAN LENGKAP IDX CASH & ACCRUAL RADAR (Edisi Pemula)\n\n"
        "Panduan ini dirancang agar siapa pun — bahkan tanpa latar belakang akuntansi — "
        "bisa mengecek kesehatan kas saham secara mandiri.\n\n"
        "🏪 Analogi Warung / Toko Sederhana:\n"
        "Bayangkan sebuah toko mencatat nota penjualan Rp 100 juta bulan ini (Laba di buku).\n"
        "Namun pembeli baru berjanji bayar bulan depan (Piutang).\n"
        "Jika kas di laci cuma Rp 2 juta sementara sewa toko Rp 20 juta jatuh tempo besok,\n"
        "toko tersebut berada dalam tekanan kas! Hal serupa dianalisis radar ini.\n\n"
        "📊 3 Pilar Pemeriksaan Deterministik:\n"
        "1. Intensitas Eksposur Kontrak PSAK 72: Seberapa banyak uang modal kerja yang masih "
        "tertahan di tagihan proyek klien (belum cair ke rekening kas).\n"
        "2. Sloan Accrual Ratio TTM: Menguji apakah laba benar-benar menghasilkan arus kas "
        "operasional riil atau hanya untung di atas kertas pembukuan.\n"
        "3. Solvabilitas Kas terhadap Utang Berbunga Jangka Pendek (Cash Coverage): "
        "Mengukur apakah kas di rekening cukup untuk melunasi utang bank jatuh tempo 1 tahun.\n\n"
        "🚦 Arti Lampu Indikator:\n"
        "• 🟢 AMAN & SOLID: Kas tebal, bebas utang segera, operasional hasilkan kas nyata.\n"
        "• 🟡 DIVERGENSI AKRUAL: Catat untung tapi kas tertahan di tagihan proyek.\n"
        "• 🔴 TEKANAN LIKUIDITAS: Kas bebas < 20% utang bank jatuh tempo 1 tahun.\n\n"
        "Format Perintah Utama:\n"
        "• /check <KODE>       — Diagnostik komprehensif emiten (contoh: /check TOTL)\n"
        "• /ticker             — Lihat daftar 12 emiten yang tercakup\n"
        "• /top                — Klasemen peringkat kas industri\n"
        "• /compare <K1> <K2>  — Adu ketahanan kas head-to-head (contoh: /compare WIKA TOTL)\n"
        "• /trend <KODE>       — Riwayat tren 4 tahun (contoh: /trend WIKA)\n"
        "• /ask <PERTANYAAN>   — Konsultasi finansial bebas bahasa manusia"
    )
    await message.answer(text, reply_markup=get_main_reply_keyboard())


@dp.message(Command("ticker", "tickers", ignore_case=True))
async def handle_ticker(message: types.Message) -> None:
    """Handles /ticker command displaying all 12 covered issuers."""
    print("📥 Permintaan diterima: /ticker", flush=True)
    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    resp_text = await asyncio.to_thread(format_ticker_list_response, repo)
    await message.answer(resp_text, reply_markup=get_main_reply_keyboard())
    print("📤 Respon terkirim untuk /ticker", flush=True)


@dp.message(Command("top", "leaderboard", ignore_case=True))
async def handle_top(message: types.Message) -> None:
    """Handles /top command showing the full FY 2025 podium leaderboard."""
    print("📥 Permintaan diterima: /top", flush=True)
    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    resp_text = await asyncio.to_thread(format_leaderboard_response, repo)
    await message.answer(resp_text, reply_markup=get_main_reply_keyboard())
    print("📤 Respon terkirim untuk /top", flush=True)


@dp.message(Command("compare", "banding", ignore_case=True))
async def handle_compare(message: types.Message) -> None:
    """Handles /compare <KODE1> <KODE2> command for head-to-head comparison."""
    args = message.text.split() if message.text else []
    if len(args) < 3:
        await message.answer(
            "⚠️ Format salah. Gunakan: /compare <KODE1> <KODE2>\nContoh: /compare WIKA TOTL",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    t1, t2 = args[1].strip().upper(), args[2].strip().upper()
    print(f"📥 Permintaan diterima: /compare {t1} vs {t2}", flush=True)

    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    resp_text = await asyncio.to_thread(format_comparison_response, t1, t2, repo)
    await message.answer(resp_text, reply_markup=get_main_reply_keyboard())
    print(f"📤 Respon terkirim untuk /compare {t1} vs {t2}", flush=True)


@dp.message(Command("trend", "tren", ignore_case=True))
async def handle_trend(message: types.Message) -> None:
    """Handles /trend <KODE> command for 4-year evolution analysis."""
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "⚠️ Format salah. Gunakan: /trend <KODE_EMITEN>\nContoh: /trend WIKA",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    ticker = args[1].strip().upper()
    print(f"📥 Permintaan diterima: /trend {ticker}", flush=True)

    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    resp_text = await asyncio.to_thread(format_trend_response, ticker, repo)
    inline_kb = get_action_inline_keyboard(ticker) if "EVOLUSI TREN" in resp_text else None
    await message.answer(resp_text, reply_markup=inline_kb)
    print(f"📤 Respon terkirim untuk /trend {ticker}", flush=True)


@dp.message(Command("check", "cek", ignore_case=True))
async def handle_check(message: types.Message) -> None:
    """Handles /check <TICKER> command with non-blocking execution and typing indicator."""
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "⚠️ Format salah. Gunakan: /check <KODE_EMITEN> (contoh: /check WIKA)",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    ticker = args[1].strip().upper()
    print(f"📥 Permintaan diterima: /check {ticker}", flush=True)

    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    resp_text = await asyncio.to_thread(format_bot_response_for_ticker, ticker, repo)
    inline_kb = get_action_inline_keyboard(ticker) if "DIAGNOSTIK KAS" in resp_text else None

    try:
        await message.answer(resp_text, reply_markup=inline_kb)
    except TelegramRetryAfter as exc:
        print(f"⏳ Rate limit dari Telegram ({exc.retry_after}s). Menunggu...", flush=True)
        await asyncio.sleep(exc.retry_after)
        await message.answer(resp_text, reply_markup=inline_kb)

    print(f"📤 Respon terkirim untuk {ticker}", flush=True)


@dp.message(Command("calk", ignore_case=True))
async def handle_calk(message: types.Message) -> None:
    """Handles /calk <TICKER> command for audited footnote breakdown."""
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "⚠️ Format salah. Gunakan: /calk <KODE_EMITEN> (contoh: /calk WIKA atau /calk TOTL)",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    ticker = args[1].strip().upper()
    print(f"📥 Permintaan diterima: /calk {ticker}", flush=True)

    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    resp_text = await asyncio.to_thread(format_calk_response, ticker, repo)
    inline_kb = get_action_inline_keyboard(ticker)
    await message.answer(resp_text, reply_markup=inline_kb)
    print(f"📤 Respon CALK terkirim untuk {ticker}", flush=True)


@dp.message(Command("watch", ignore_case=True))
async def handle_watch(message: types.Message) -> None:
    """Handles /watch <TICKER> to subscribe to automatic distress & filing alerts."""
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "⚠️ Format salah. Gunakan: /watch <KODE_EMITEN> (contoh: /watch WIKA)",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    ticker = args[1].strip().upper()
    issuer = repo.get_issuer(ticker)
    if not issuer:
        await message.answer(
            f"⚠️ Emiten {ticker} belum terdaftar dalam semesta sektor konstruksi.",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    user_id = str(message.from_user.id if message.from_user else "default_user")
    repo.add_to_watchlist(user_id, ticker)
    await message.answer(
        f"✅ Berhasil! **{ticker}** ({issuer.company_name}) ditambahkan ke watchlist Anda.\n"
        f"Anda akan menerima alert otomatis jika terdeteksi anomali kas atau rilis baru.\n\n"
        f"Ketik `/watchlist` untuk melihat daftar pantauan Anda.",
        reply_markup=get_action_inline_keyboard(ticker),
    )


@dp.message(Command("unwatch", ignore_case=True))
async def handle_unwatch(message: types.Message) -> None:
    """Handles /unwatch <TICKER> to unsubscribe from alerts."""
    args = message.text.split() if message.text else []
    if len(args) < 2:
        await message.answer(
            "⚠️ Format salah. Gunakan: /unwatch <KODE_EMITEN> (contoh: /unwatch WIKA)",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    ticker = args[1].strip().upper()
    user_id = str(message.from_user.id if message.from_user else "default_user")
    removed = repo.remove_from_watchlist(user_id, ticker)
    if removed:
        await message.answer(
            f"🗑️ Emiten **{ticker}** telah dihapus dari watchlist radar Anda.",
            reply_markup=get_main_reply_keyboard(),
        )
    else:
        await message.answer(
            f"ℹ️ Emiten **{ticker}** tidak ditemukan di dalam watchlist Anda.",
            reply_markup=get_main_reply_keyboard(),
        )


@dp.message(Command("watchlist", "pantau", ignore_case=True))
async def handle_watchlist(message: types.Message) -> None:
    """Handles /watchlist command showing user's personal radar watch list."""
    user_id = str(message.from_user.id if message.from_user else "default_user")
    resp = await asyncio.to_thread(format_user_watchlist_response, user_id, repo)
    await message.answer(resp, reply_markup=get_main_reply_keyboard())


@dp.message(Command("ask", "tanya", ignore_case=True))
async def handle_ask(message: types.Message) -> None:
    """Handles /ask <PERTANYAAN> command using grounded RAG."""
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "💬 Silakan tulis pertanyaan finansial Anda setelah perintah /ask.\n"
            "Contoh:\n"
            "• `/ask Kenapa rasio kas TOTL sangat tinggi?`\n"
            "• `/ask Apa bedanya Sloan Accrual dengan Arus Kas Operasi?`\n"
            "• `/ask Emiten mana yang memiliki kas paling aman?`",
            reply_markup=get_main_reply_keyboard(),
            parse_mode="Markdown",
        )
        return

    query = args[1].strip()
    print(f"📥 Permintaan RAG Chat: {query}", flush=True)

    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    rag_answer = await asyncio.to_thread(rag_chatbot.answer_query, query)
    await message.answer(rag_answer, reply_markup=get_main_reply_keyboard())
    print("📤 Respon RAG Chat terkirim", flush=True)


@dp.message(F.document)
async def handle_document_upload(message: types.Message) -> None:
    """
    Handles user upload of instance.zip or .xbrl/.xml files.
    Dynamically parses the financial facts, saves to SQLite, and returns an instant card.
    """
    doc = message.document
    if not doc:
        return

    fname = doc.file_name or "instance.zip"
    fname_low = fname.lower()
    valid_exts = (".zip", ".xbrl", ".xml")
    if not any(fname_low.endswith(ext) for ext in valid_exts):
        await message.answer(
            "⚠️ Berkas yang dikirim tidak dikenali sebagai laporan keuangan XBRL BEI.\n"
            "Format yang didukung: berkas `.zip` (misal `instance.zip`), `.xbrl`, atau `.xml`.",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    await message.answer(
        f"⏳ Menerima berkas **{fname}** ({round((doc.file_size or 0) / 1024, 1)} KB)...\n"
        "Mengekstrak taksonomi XBRL dan memvalidasi rekonsiliasi angka kas...",
        reply_markup=get_main_reply_keyboard(),
    )

    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    bio = io.BytesIO()
    if message.bot:
        try:
            await message.bot.download(file=doc, destination=bio)
            file_bytes = bio.getvalue()
        except Exception as e:
            await message.answer(
                f"❌ Gagal mengunduh berkas dari Telegram: {e}",
                reply_markup=get_main_reply_keyboard(),
            )
            return
    else:
        file_bytes = b""

    res = await asyncio.to_thread(
        dynamic_ingestor.process_file,
        file_bytes,
        fname,
    )

    if res.get("status") != "success":
        await message.answer(
            f"❌ {res.get('message', 'Gagal memproses berkas.')}",
            reply_markup=get_main_reply_keyboard(),
        )
        return

    success_header = (
        "🎉 **BERKAS RESMI BEI BERHASIL DIEKSTRAK & DIINJEKSI!**\n"
        f"🏢 Emiten    : **{res['ticker']}** — {res['company_name']}\n"
        f"📅 Periode   : **FY {res['fiscal_year']}**\n"
        f"🏷️ Sektor    : {res['sub_industry']}\n"
        f"📊 Pos Valid : {res['facts_count']} Pos Keuangan Terverifikasi\n"
        f"{'━' * 42}\n\n"
    )

    full_resp = success_header + res["card_text"]
    inline_kb = get_action_inline_keyboard(res["ticker"])
    await message.answer(full_resp, reply_markup=inline_kb)
    print(f"📤 Injeksi dinamis sukses untuk {res['ticker']}", flush=True)


@dp.callback_query()
async def handle_callback_router(callback: types.CallbackQuery) -> None:
    """Handles interactive inline button clicks seamlessly."""
    await callback.answer()
    data = callback.data or ""

    if callback.message and callback.message.bot:
        try:
            await callback.message.bot.send_chat_action(
                chat_id=callback.message.chat.id, action=ChatAction.TYPING
            )
        except Exception:
            pass

    if data == "top":
        resp = await asyncio.to_thread(format_leaderboard_response, repo)
        if callback.message:
            await callback.message.answer(resp, reply_markup=get_main_reply_keyboard())

    elif data.startswith("trend:") or data.startswith("tren:"):
        ticker = data.split(":")[1]
        resp = await asyncio.to_thread(format_trend_response, ticker, repo)
        if callback.message:
            await callback.message.answer(resp, reply_markup=get_action_inline_keyboard(ticker))

    elif data.startswith("compare:") or data.startswith("banding:"):
        parts = data.split(":")
        t1, t2 = parts[1], parts[2]
        resp = await asyncio.to_thread(format_comparison_response, t1, t2, repo)
        if callback.message:
            await callback.message.answer(resp, reply_markup=get_main_reply_keyboard())

    elif data.startswith("news:"):
        ticker = data.split(":")[1]
        resp = await asyncio.to_thread(format_news_response, ticker)
        if callback.message:
            await callback.message.answer(resp, reply_markup=get_action_inline_keyboard(ticker))

    elif data.startswith("calk:"):
        ticker = data.split(":")[1]
        resp = await asyncio.to_thread(format_calk_response, ticker, repo)
        if callback.message:
            await callback.message.answer(resp, reply_markup=get_action_inline_keyboard(ticker))

    elif data.startswith("watch:"):
        ticker = data.split(":")[1]
        user_id = str(callback.from_user.id if callback.from_user else "default_user")
        repo.add_to_watchlist(user_id, ticker)
        if callback.message:
            await callback.message.answer(
                f"⭐ **{ticker}** ditambahkan ke watchlist Anda. "
                f"Ketik `/watchlist` untuk melihat seluruh pantauan.",
                reply_markup=get_main_reply_keyboard(),
            )


@dp.message()
async def handle_text_router(message: types.Message) -> None:
    """Smart router for executive navigation buttons, direct ticker queries, and RAG chat."""
    raw = message.text.strip() if message.text else ""
    if not raw:
        return

    # Category Button: Check Emiten
    if "check emiten" in raw.lower():
        guide_text = (
            "🔍 PENCARIAN & DIAGNOSTIK EMITEN\n"
            "━" * 42 + "\n"
            "Ketik perintah dengan format:\n"
            "👉 /check <KODE_EMITEN>\n"
            "Contoh: /check TOTL atau /check WIKA\n\n"
            "💡 Tip: Anda juga dapat mengetik langsung 4 huruf kode saham (contoh: TOTL)."
        )
        await message.answer(guide_text, reply_markup=get_main_reply_keyboard())
        return

    # Category Button: Top Leaderboard
    if "top leaderboard" in raw.lower() or raw.lower() == "top":
        await handle_top(message)
        return

    # Category Button: Compare Peers
    if "compare peers" in raw.lower():
        compare_guide = (
            "⚖️ HEAD-TO-HEAD COMPARISON\n"
            "━" * 42 + "\n"
            "Bandingkan ketahanan kas dan beban utang dua emiten:\n"
            "👉 /compare <KODE1> <KODE2>\n"
            "Contoh: /compare WIKA TOTL atau /compare ADHI PTPP"
        )
        await message.answer(compare_guide, reply_markup=get_main_reply_keyboard())
        return

    # Category Button: Trend 4 Tahun
    if "trend 4 tahun" in raw.lower():
        trend_guide = (
            "📈 EVOLUSI TREN KEUANGAN 4 TAHUN\n"
            "━" * 42 + "\n"
            "Lihat lintasan arus kas dan solvabilitas historis (2022–2025):\n"
            "👉 /trend <KODE_EMITEN>\n"
            "Contoh: /trend WIKA atau /trend TOTL"
        )
        await message.answer(trend_guide, reply_markup=get_main_reply_keyboard())
        return

    # Category Button: Daftar Ticker
    if "daftar ticker" in raw.lower() or raw.lower() == "ticker":
        await handle_ticker(message)
        return

    # Category Button: Watchlist Pantauan
    if "watchlist" in raw.lower() or "pantauan" in raw.lower():
        await handle_watchlist(message)
        return

    # Category Button: Panduan & Metodologi
    if "panduan" in raw.lower() or "metodologi" in raw.lower():
        await handle_help(message)
        return

    # Direct 4-letter stock ticker like 'TOTL', 'WIKA', 'PBSA'
    if len(raw) == 4 and raw.isalpha():
        message.text = f"/check {raw.upper()}"
        await handle_check(message)
        return

    # Conversational RAG Query: Answer free-form financial questions using grounded RAG knowledge
    print(f"📥 Permintaan Tanya Jawab Percakapan (RAG): {raw}", flush=True)
    if message.bot:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    rag_response = await asyncio.to_thread(rag_chatbot.answer_query, raw)
    await message.answer(rag_response, reply_markup=get_main_reply_keyboard())
    print("📤 Respon Tanya Jawab RAG terkirim", flush=True)


async def setup_bot_commands(bot: Bot) -> None:
    """Registers standard bot commands so Telegram displays the native '/' command menu."""
    commands = [
        types.BotCommand(command="check", description="Diagnostik kas & akrual emiten"),
        types.BotCommand(command="ticker", description="Daftar 12 emiten konstruksi BEI"),
        types.BotCommand(command="top", description="Klasemen solvabilitas kas industri"),
        types.BotCommand(command="compare", description="Komparasi kas head-to-head dua emiten"),
        types.BotCommand(command="trend", description="Evolusi tren arus kas & utang 4 tahun"),
        types.BotCommand(command="calk", description="Rincian pihak berelasi & CKPN catatan kaki"),
        types.BotCommand(command="watchlist", description="Pantau emiten & notifikasi alert"),
        types.BotCommand(command="ask", description="Tanya jawab finansial & metodologi RAG"),
        types.BotCommand(command="help", description="Panduan metodologi & indikator"),
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as exc:
        print(f"⚠️ Warning: Could not register Telegram bot commands: {exc}", flush=True)


class IPv4AiohttpSession(AiohttpSession):
    """AiohttpSession forced to IPv4 to prevent Windows/ISP IPv6 semaphore timeout drops."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET


async def main() -> None:
    parser = argparse.ArgumentParser(description="IDX Cash Radar Telegram Bot")
    parser.add_argument(
        "--token", default=os.getenv("TELEGRAM_BOT_TOKEN"), help="Telegram Bot Token"
    )
    args = parser.parse_args()

    if not args.token:
        print("⚠️ TELEGRAM_BOT_TOKEN belum diatur.")
        print("👉 Silakan isi TELEGRAM_BOT_TOKEN di file .env atau gunakan argumen --token.")
        return

    while True:
        try:
            session = IPv4AiohttpSession(timeout=30.0)
            bot = Bot(token=args.token, session=session)
            await bot.delete_webhook(drop_pending_updates=False)
            await setup_bot_commands(bot)
            print("🤖 Bot Telegram IDX Cash Radar aktif (IPv4). Memulai polling...", flush=True)
            await dp.start_polling(bot, polling_timeout=10)
            break
        except (TelegramNetworkError, OSError) as exc:
            print(f"⚠️ Gangguan jaringan ({exc}). Mencoba rekoneksi dalam 5 detik...", flush=True)
            await asyncio.sleep(5)
        except (KeyboardInterrupt, SystemExit):
            break


if __name__ == "__main__":
    asyncio.run(main())
