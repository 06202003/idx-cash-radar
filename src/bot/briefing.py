"""Factual watchlist briefing, canonical_facts DB reader, market/event fetchers, and daily_snapshot archiver."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal
from typing import Any

from lxml import etree

from src.bot.idx_calendar import now_wib
from src.bot.pg_store import BotStateStore
from src.db.repository import FinancialRepository
from src.renderer.formatter import format_idr_nominal

EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "UMA": ("unusual market activity", " uma "),
    "FCA": ("full call auction", "pemantauan khusus", " fca "),
    "SUSPENSI": ("suspensi", "penghentian sementara perdagangan"),
    "REBALANCING": ("rebalancing", "konstituen lq45", "idx80", "indeks msci", "ftse"),
}


def load_canonical_ticker_record(ticker: str, repo: FinancialRepository | None = None) -> dict[str, Any] | None:
    """
    Loads latest audited metrics and canonical_facts directly from the database.
    All numeric values in bot messages MUST originate from this function.
    """
    clean_t = ticker.strip().upper()
    db_repo = repo or FinancialRepository()
    issuer = db_repo.get_issuer(clean_t)
    if not issuer:
        return None

    with db_repo.get_connection() as conn:
        filing_row = conn.execute(
            """
            SELECT filing_id, fiscal_year, period_code, period_end_date
            FROM filings
            WHERE ticker = ?
            ORDER BY fiscal_year DESC, period_end_date DESC
            LIMIT 1
            """,
            (clean_t,),
        ).fetchone()
        if not filing_row:
            return None

        filing_id = filing_row["filing_id"]
        facts = db_repo.get_canonical_facts(filing_id)
        metrics_row = db_repo.get_computed_metrics_row(filing_id) or {}

    cash_fact = facts.get("cash_and_equivalents")
    st_bank_fact = facts.get("short_term_bank_loans")
    st_bond_fact = facts.get("bonds_payable_current")
    cfo_fact = facts.get("cfo_ytd")
    ni_fact = facts.get("net_income_ytd")

    cash_idr = Decimal(cash_fact.value_idr) if cash_fact else Decimal("0")
    st_bank_idr = Decimal(st_bank_fact.value_idr) if st_bank_fact else Decimal("0")
    st_bond_idr = Decimal(st_bond_fact.value_idr) if st_bond_fact else Decimal("0")
    st_debt_idr = st_bank_idr + st_bond_idr

    cfo_ttm = (
        Decimal(str(metrics_row["cfo_ttm_idr"]))
        if metrics_row.get("cfo_ttm_idr") is not None
        else (Decimal(cfo_fact.value_idr) if cfo_fact else Decimal("0"))
    )
    net_income_ttm = (
        Decimal(str(metrics_row["net_income_ttm_idr"]))
        if metrics_row.get("net_income_ttm_idr") is not None
        else (Decimal(ni_fact.value_idr) if ni_fact else Decimal("0"))
    )

    debt_free = bool(metrics_row.get("debt_free_short_term")) or st_debt_idr == 0
    if debt_free:
        cash_cov_str = "Bebas Utang JP"
        cash_cov_val: float | None = None
    else:
        cov_raw = (
            Decimal(str(metrics_row["cash_coverage_ratio"]))
            if metrics_row.get("cash_coverage_ratio") is not None
            else (cash_idr / st_debt_idr)
        )
        cash_cov_val = float(cov_raw)
        cash_cov_str = f"{cov_raw:.2f}x"

    sloan_raw = metrics_row.get("sloan_ratio_ttm")
    sloan_pct = round(float(sloan_raw) * 100.0, 1) if sloan_raw is not None else None

    flag_liq = bool(metrics_row.get("flag_acute_liquidity"))
    flag_acc = bool(metrics_row.get("flag_accrual_divergence"))
    if flag_liq:
        cash_status = "TEKANAN_LIKUIDITAS"
    elif flag_acc:
        cash_status = "DIVERGENSI_AKRUAL"
    elif debt_free:
        cash_status = "BEBAS_UTANG"
    elif cash_cov_val is not None and cash_cov_val >= 1.0:
        cash_status = "SOLVEN_SEHAT"
    else:
        cash_status = "TERKENDALI"

    return {
        "ticker": clean_t,
        "company_name": issuer.company_name,
        "sub_industry": issuer.idx_sub_industry,
        "filing_id": filing_id,
        "fiscal_year": int(filing_row["fiscal_year"]),
        "fiscal_period": str(filing_row["period_code"]),
        "period_end_date": str(filing_row["period_end_date"]),
        "cash_idr": int(cash_idr),
        "st_debt_idr": int(st_debt_idr),
        "cfo_ttm_idr": int(cfo_ttm),
        "net_income_ttm_idr": int(net_income_ttm),
        "cash_coverage_val": cash_cov_val,
        "cash_coverage_display": cash_cov_str,
        "sloan_ratio_pct": sloan_pct,
        "debt_free_short_term": debt_free,
        "flag_acute_liquidity": flag_liq,
        "flag_accrual_divergence": flag_acc,
        "cash_status": cash_status,
    }


def list_universe_tickers(repo: FinancialRepository | None = None) -> list[str]:
    db_repo = repo or FinancialRepository()
    with db_repo.get_connection() as conn:
        rows = conn.execute("SELECT ticker FROM issuers ORDER BY ticker").fetchall()
    return [str(r["ticker"]).upper() for r in rows]


def fetch_factual_market_quote(
    ticker: str,
    store: BotStateStore | None = None,
    timeout: float = 6.0,
) -> dict[str, Any] | None:
    """
    Fetches factual close price, 1D change %, and volume ratio vs 20-day average from Yahoo Finance .JK.
    Logs failures to source_fetch_logs and returns None instead of guessing.
    """
    clean_t = ticker.strip().upper().replace(".JK", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(clean_t + '.JK')}?range=2mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; IDXCashRadarBot/2.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        res = (data.get("chart") or {}).get("result") or []
        if not res:
            if store:
                store.log_source_fetch("yahoo_finance_jk", "EMPTY", clean_t, "No chart result")
            return None
        q = ((res[0].get("indicators") or {}).get("quote") or [{}])[0]
        closes = [float(c) for c in (q.get("close") or []) if c is not None and float(c) > 0]
        vols = [float(v) for v in (q.get("volume") or []) if v is not None]
        if len(closes) < 2:
            if store:
                store.log_source_fetch("yahoo_finance_jk", "EMPTY", clean_t, "Insufficient bars")
            return None
        last_close = closes[-1]
        prev_close = closes[-2]
        chg_1d_pct = ((last_close - prev_close) / prev_close) * 100.0
        last_vol = int(vols[-1]) if vols else 0
        avg20_vol = sum(vols[-21:-1]) / len(vols[-21:-1]) if len(vols) >= 2 else (last_vol or 1.0)
        vol_ratio = (last_vol / avg20_vol) if avg20_vol > 0 else 1.0
        return {
            "close_price": round(last_close, 2),
            "change_1d_pct": round(chg_1d_pct, 2),
            "volume": last_vol,
            "vol_ratio_20d": round(vol_ratio, 2),
        }
    except Exception as exc:
        if store:
            store.log_source_fetch("yahoo_finance_jk", "ERROR", clean_t, str(exc)[:240])
        return None


def fetch_verifiable_news(
    ticker: str,
    max_items: int = 2,
    store: BotStateStore | None = None,
    timeout: float = 6.0,
) -> list[dict[str, Any]]:
    """
    Fetches short headline + media name + URL + published_at (no sentiment labels, no copied summaries).
    Logs failures and returns [] if unreachable.
    """
    clean_t = ticker.strip().upper().replace(".JK", "")
    query = urllib.parse.quote(f"{clean_t} saham BEI when:30d")
    url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; IDXCashRadarBot/2.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = etree.fromstring(raw)
        items: list[dict[str, Any]] = []
        for el in root.xpath("//channel/item")[:max_items]:
            title = (el.findtext("title") or "").strip()
            link = (el.findtext("link") or "").strip()
            pub_date = (el.findtext("pubDate") or "").strip()
            src_el = el.find("source")
            media = src_el.text.strip() if src_el is not None and src_el.text else "Google News RSS"
            if not title or not link:
                continue
            if " - " in title and media != "Google News RSS":
                title = title.rsplit(" - ", 1)[0].strip()
            items.append({
                "title": title,
                "media": media,
                "url": link,
                "published_at": pub_date[:16] if pub_date else "-",
            })
        return items
    except Exception as exc:
        if store:
            store.log_source_fetch("google_news_rss", "ERROR", clean_t, str(exc)[:240])
        return []


def detect_verifiable_events(news_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extracts verifiable UMA/FCA/suspensi/rebalancing events with source and timestamp."""
    events: list[dict[str, str]] = []
    for n in news_items:
        hay = f" {n.get('title', '').lower()} "
        for ev_type, kws in EVENT_KEYWORDS.items():
            if any(k in hay for k in kws):
                events.append({
                    "event_type": ev_type,
                    "title": str(n.get("title", "")),
                    "source": str(n.get("media", "")),
                    "published_at": str(n.get("published_at", "-")),
                    "url": str(n.get("url", "")),
                })
                break
    return events


def format_watchlist_briefing_item(
    record: dict[str, Any],
    market: dict[str, Any] | None = None,
    news: list[dict[str, Any]] | None = None,
) -> str:
    """
    Formats a single watched ticker strictly from DB canonical_facts + factual market/news metadata.
    Contains NO evaluative words, NO RSI/MA conclusions, NO sentiment labels, and NO rankings.
    """
    cash_s = format_idr_nominal(Decimal(record["cash_idr"]))
    debt_s = format_idr_nominal(Decimal(record["st_debt_idr"]))
    cfo_s = format_idr_nominal(Decimal(record["cfo_ttm_idr"]))
    ni_s = format_idr_nominal(Decimal(record["net_income_ttm_idr"]))
    sloan_s = f"{record['sloan_ratio_pct']:+.1f}%" if record.get("sloan_ratio_pct") is not None else "N/A"

    lines = [
        f"*{record['ticker']}* — {record['company_name']}",
        f"Tanggal Laporan: `{record['period_end_date']}` ({record['fiscal_period']} {record['fiscal_year']})",
        f"• Kas: `{cash_s}` | Utang JP: `{debt_s}` | Coverage: `{record['cash_coverage_display']}`",
        f"• CFO TTM: `{cfo_s}` | Laba Bersih TTM: `{ni_s}` | Sloan: `{sloan_s}`",
        f"• Status Kas: `{record['cash_status']}`",
    ]
    if market:
        price_s = f"Rp {int(round(market['close_price'])):,}".replace(",", ".")
        lines.append(
            f"• Harga Tutup: `{price_s}` (`{market['change_1d_pct']:+.2f}%` 1H) | "
            f"Volume `{market['vol_ratio_20d']:.1f}x` rata-rata 20 hari (data tertunda ±5-15 menit)"
        )
    if news:
        top = news[0]
        lines.append(f"• Berita: {top['title']} — _{top['media']}_ ({top['published_at']})\n  {top['url']}")
    return "\n".join(lines)


def format_volume_alert(ticker: str, vol_ratio_20d: float) -> str:
    """Factual volume alert message without evaluative labels."""
    ratio_id = f"{vol_ratio_20d:.1f}".replace(".", ",")
    return f"📊 *{ticker}*: Volume {ratio_id}x rata-rata 20 hari, data tertunda ±5-15 menit."


def format_event_alert(ticker: str, ev: dict[str, str]) -> str:
    """Factual event alert message (UMA/FCA/suspensi/rebalancing) with source and timestamp."""
    return (
        f"📌 *{ticker} — Peristiwa {ev['event_type']}*\n"
        f"{ev['title']}\n"
        f"Sumber: {ev['source']} | Waktu: {ev['published_at']}\n"
        f"{ev['url']}"
    )


def capture_universe_daily_snapshot(
    store: BotStateStore,
    repo: FinancialRepository | None = None,
    snapshot_date: date | None = None,
    fetch_external: bool = True,
) -> int:
    """
    Captures daily_snapshot for the ENTIRE covered universe on a trading day.
    Returns count of tickers archived.
    """
    db_repo = repo or FinancialRepository()
    snap_date = snapshot_date or now_wib().date()
    tickers = list_universe_tickers(db_repo)
    archived = 0
    for t in tickers:
        rec = load_canonical_ticker_record(t, db_repo)
        if not rec:
            continue
        market = fetch_factual_market_quote(t, store=store) if fetch_external else None
        news = fetch_verifiable_news(t, max_items=3, store=store) if fetch_external else []
        events = detect_verifiable_events(news) if news else []
        flags = {
            "debt_free_short_term": rec["debt_free_short_term"],
            "flag_acute_liquidity": rec["flag_acute_liquidity"],
            "flag_accrual_divergence": rec["flag_accrual_divergence"],
            "period_end_date": rec["period_end_date"],
        }
        store.upsert_daily_snapshot(
            snapshot_date=snap_date,
            ticker=t,
            cash_status=rec["cash_status"],
            flags=flags,
            close_price=market["close_price"] if market else None,
            volume=market["volume"] if market else None,
            news_items=news,
            idx_announcements=events,
        )
        archived += 1
    return archived


def detect_filing_change_for_ticker(
    ticker: str,
    store: BotStateStore,
    repo: FinancialRepository | None = None,
) -> dict[str, Any] | None:
    """
    Compares the latest filing in DB against the previous filing and last_seen_filings.
    Returns a factual change payload only when a newer filing_id is detected.
    """
    clean_t = ticker.strip().upper()
    db_repo = repo or FinancialRepository()
    with db_repo.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT filing_id, fiscal_year, period_code, period_end_date
            FROM filings
            WHERE ticker = ?
            ORDER BY fiscal_year DESC, period_end_date DESC
            LIMIT 2
            """,
            (clean_t,),
        ).fetchall()
    if len(rows) < 2:
        if len(rows) == 1 and store.get_last_seen_filing(clean_t) is None:
            store.set_last_seen_filing(clean_t, str(rows[0]["filing_id"]))
        return None

    newest, prev = rows[0], rows[1]
    newest_id = str(newest["filing_id"])
    seen_id = store.get_last_seen_filing(clean_t)
    if seen_id == newest_id:
        return None
    if seen_id is None:
        # Baseline initialization on first run; do not spam historical filings.
        store.set_last_seen_filing(clean_t, newest_id)
        return None

    m_new = db_repo.get_computed_metrics_row(newest_id) or {}
    m_prev = db_repo.get_computed_metrics_row(str(prev["filing_id"])) or {}

    def _cov_disp(m: dict[str, Any]) -> str:
        if m.get("debt_free_short_term"):
            return "Bebas Utang JP"
        val = m.get("cash_coverage_ratio")
        return f"{Decimal(str(val)):.2f}x" if val is not None else "N/A"

    return {
        "ticker": clean_t,
        "new_filing_id": newest_id,
        "new_period_end_date": str(newest["period_end_date"]),
        "prev_period_end_date": str(prev["period_end_date"]),
        "prev_cfo_idr": int(Decimal(str(m_prev.get("cfo_ttm_idr") or 0))),
        "new_cfo_idr": int(Decimal(str(m_new.get("cfo_ttm_idr") or 0))),
        "prev_cov_display": _cov_disp(m_prev),
        "new_cov_display": _cov_disp(m_new),
    }


def format_filing_change_alert(change: dict[str, Any]) -> str:
    """Formats a factual new-filing change alert without evaluative claims."""
    prev_cfo = format_idr_nominal(Decimal(change["prev_cfo_idr"]))
    new_cfo = format_idr_nominal(Decimal(change["new_cfo_idr"]))
    return (
        f"📄 *{change['ticker']}* merilis laporan baru (`{change['new_period_end_date']}`, "
        f"sebelumnya `{change['prev_period_end_date']}`).\n"
        f"• Arus kas operasi 12 bulan: `Rp {prev_cfo}` → `Rp {new_cfo}`\n"
        f"• Cash coverage: `{change['prev_cov_display']}` → `{change['new_cov_display']}`"
    )
