"""
FastAPI Application & Interactive Financial Radar REST API.
Phase 2 Implementation according to docs/PRD.md Section 10.2.
Provides programmatic endpoints and visual financial diagnostic dashboard.
"""

from __future__ import annotations

import base64
import math
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Ensure root directory on sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.db.repository import FinancialRepository  # noqa: E402
from src.engine.calk_extractor import CALKFootnoteExtractor  # noqa: E402
from src.engine.daily_news_cron import (  # noqa: E402
    load_daily_news,
    refresh_daily_news,
)
from src.engine.knowledge_ingestor import (  # noqa: E402
    ingest_structured_issuer,
    ingest_xbrl_file_bytes,
)
from src.engine.market_quotes import (  # noqa: E402
    fetch_batch_quotes,
    fetch_price_history,
    fetch_single_quote,
)
from src.engine.ml_models import FinancialMLSuite  # noqa: E402
from src.engine.news_radar import NewsRadar  # noqa: E402
from src.engine.rag_chat import RAGFinancialChatbot  # noqa: E402
from src.engine.realtime_news_analyzer import (  # noqa: E402
    analyze_sentiment_deterministic,
    detect_all_tickers_in_article,
    detect_ticker_in_article,
    extract_key_highlights,
    fetch_article_from_url,
    synthesize_news_vs_accrual,
)

app = FastAPI(
    title="IDX Cash & Accrual Radar API",
    description="Deterministic Financial Intelligence API for IDX Construction Sector (PSAK 72)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = FinancialRepository()
calk_extractor = CALKFootnoteExtractor(api_key="")
ml_suite = FinancialMLSuite(repo=repo)
news_radar = NewsRadar()
rag_chatbot = RAGFinancialChatbot(repository=repo, news_radar=news_radar)


class ChatRequest(BaseModel):
    message: str


class NewsAnalyzeRequest(BaseModel):
    url: str | None = None
    raw_text: str | None = None
    ticker: str | None = None


class IssuerIngestRequest(BaseModel):
    ticker: str
    company_name: str
    idx_sub_industry: str
    fiscal_year: int = 2025
    unit_multiplier: int = 1_000_000_000  # Default Miliar IDR; or 1 for full IDR
    cash: float
    st_debt_bank: float = 0.0
    st_debt_bonds: float = 0.0
    cfo_ttm: float
    net_income_ttm: float
    revenue_ttm: float
    total_assets: float
    total_liabilities: float = 0.0
    receivables: float = 0.0
    source_note: str | None = None


class IssuerXBRLUploadRequest(BaseModel):
    ticker: str
    company_name: str
    idx_sub_industry: str
    fiscal_year: int = 2025
    filename: str
    content_base64: str


def _build_sector_condition(sector: str | None, col: str = "idx_sub_industry") -> str:
    """Builds SQL condition for filtering by sector category."""
    if not sector:
        return ""
    s = sector.upper()
    if s == "CONSTRUCTION":
        return f"LOWER({col}) LIKE '%konstruksi%'"
    elif s == "FMCG":
        return (
            f"(LOWER({col}) LIKE '%fmcg%' "
            f"OR LOWER({col}) LIKE '%makanan%' "
            f"OR LOWER({col}) LIKE '%perawatan%' "
            f"OR LOWER({col}) LIKE '%ritel%' "
            f"OR LOWER({col}) LIKE '%farmasi%')"
        )
    elif s == "BANKING":
        return f"(LOWER({col}) LIKE '%bank%' OR LOWER({col}) LIKE '%keuangan%')"
    elif s == "ENERGY":
        return (
            f"(LOWER({col}) LIKE '%energi%' "
            f"OR LOWER({col}) LIKE '%tambang%' "
            f"OR LOWER({col}) LIKE '%minyak%' "
            f"OR LOWER({col}) LIKE '%gas%' "
            f"OR LOWER({col}) LIKE '%mineral%' "
            f"OR LOWER({col}) LIKE '%bahan bakar%')"
        )
    elif s == "TELECOM":
        return f"(LOWER({col}) LIKE '%telekomunikasi%' OR LOWER({col}) LIKE '%menara%')"
    return ""


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "system": "IDX Cash & Accrual Radar v2.0"}


@app.get("/api/issuers")
def get_issuers(sector: str | None = None) -> list[dict[str, Any]]:
    """Returns directory of covered issuers across sectors."""
    cond = _build_sector_condition(sector, "idx_sub_industry")
    where_clause = f"WHERE {cond}" if cond else ""

    query = f"""
    SELECT ticker, company_name, idx_sub_industry, listing_status
    FROM issuers
    {where_clause}
    ORDER BY ticker ASC;
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query).fetchall()]
    return rows


@app.post("/api/issuers/ingest")
def ingest_new_issuer_data(req: IssuerIngestRequest) -> dict[str, Any]:
    """
    Self-Growing Knowledge Base endpoint: allows users to add a new ticker
    or update financial metrics, computing all ratios deterministically and
    persisting immediately into SQLite for Screener, Radar, and RAG Chatbot.
    """
    try:
        mult = Decimal(str(req.unit_multiplier or 1))
        res = ingest_structured_issuer(
            repo=repo,
            ticker=req.ticker,
            company_name=req.company_name,
            idx_sub_industry=req.idx_sub_industry,
            fiscal_year=req.fiscal_year,
            cash_idr=Decimal(str(req.cash)) * mult,
            st_debt_bank_idr=Decimal(str(req.st_debt_bank)) * mult,
            st_debt_bonds_idr=Decimal(str(req.st_debt_bonds)) * mult,
            cfo_ttm_idr=Decimal(str(req.cfo_ttm)) * mult,
            net_income_ttm_idr=Decimal(str(req.net_income_ttm)) * mult,
            revenue_ttm_idr=Decimal(str(req.revenue_ttm)) * mult,
            total_assets_idr=Decimal(str(req.total_assets)) * mult,
            total_liabilities_idr=Decimal(str(req.total_liabilities)) * mult,
            receivables_idr=Decimal(str(req.receivables)) * mult,
            source_note=req.source_note,
        )
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save issuer data: {exc}") from exc


@app.post("/api/issuers/ingest-xbrl")
def ingest_new_issuer_xbrl(req: IssuerXBRLUploadRequest) -> dict[str, Any]:
    """
    Parses an uploaded BEI XBRL (.xml or .zip) filing and ingests it into
    the self-growing SQLite knowledge database.
    """
    try:
        raw_b64 = req.content_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        file_bytes = base64.b64decode(raw_b64)
        return ingest_xbrl_file_bytes(
            repo=repo,
            ticker=req.ticker,
            company_name=req.company_name,
            idx_sub_industry=req.idx_sub_industry,
            fiscal_year=req.fiscal_year,
            filename=req.filename,
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to parse XBRL file: {exc}"
        ) from exc


@app.get("/api/screener")
def get_screener_data(
    fiscal_year: int = 2025, sector: str | None = None
) -> list[dict[str, Any]]:
    """
    Returns full screening dataset across all issuers for Stockbit/TradingView-style screener.
    Includes Cash, ST Debt, CFO TTM, Net Income TTM, Coverage Ratio, Sloan Accrual, and Risk Status.
    """
    where_clause = (
        "WHERE f.filing_id = ("
        "SELECT f2.filing_id FROM filings f2 "
        "JOIN computed_metrics cm2 ON f2.filing_id = cm2.filing_id "
        "WHERE f2.ticker = f.ticker "
        "ORDER BY CASE WHEN f2.fiscal_year = ? THEN 0 ELSE 1 END, "
        "f2.fiscal_year DESC LIMIT 1)"
    )
    params: list[Any] = [fiscal_year]

    cond = _build_sector_condition(sector, "i.idx_sub_industry")
    if cond:
        where_clause += f" AND {cond}"

    query = f"""
    SELECT cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
           cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.cfo_ttm_idr, cm.net_income_ttm_idr,
           cm.revenue_ttm_idr, cm.flag_acute_liquidity, cm.flag_accrual_divergence,
           MAX(CASE WHEN cf.canonical_key = 'cash_and_equivalents'
               THEN cf.value_idr END) as cash_idr,
           SUM(CASE WHEN cf.canonical_key IN (
               'st_debt_bank_loans',
               'st_debt_current_maturities_bank_loans',
               'st_debt_current_maturities_bonds_sukuk_mtn'
           ) THEN CAST(cf.value_idr AS NUMERIC) ELSE 0 END) as st_debt_idr,
           MAX(CASE WHEN cf.canonical_key = 'total_assets'
               THEN cf.value_idr END) as total_assets_idr,
           MAX(CASE WHEN cf.canonical_key = 'total_liabilities'
               THEN cf.value_idr END) as total_liabilities_idr,
           SUM(CASE WHEN cf.canonical_key IN (
               'trade_receivables_third_parties',
               'trade_receivables_related_parties',
               'contract_assets_current',
               'contract_assets_non_current'
           ) THEN CAST(cf.value_idr AS NUMERIC) ELSE 0 END) as receivables_idr,
           MAX(CASE WHEN cf.canonical_key = 'st_debt_bank_loans'
               THEN cf.value_idr END) as bank_loans_idr,
           MAX(CASE WHEN cf.canonical_key = 'st_debt_current_maturities_bonds_sukuk_mtn'
               THEN cf.value_idr END) as bonds_sukuk_idr
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    LEFT JOIN canonical_facts cf ON f.filing_id = cf.filing_id
    {where_clause}
    GROUP BY cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
             cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.cfo_ttm_idr, cm.net_income_ttm_idr,
             cm.revenue_ttm_idr, cm.flag_acute_liquidity, cm.flag_accrual_divergence
    ORDER BY cm.ticker ASC;
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    for r in rows:
        is_free = bool(r["debt_free_short_term"])
        raw_cov = r["cash_coverage_ratio"]
        cov = 9999.0 if is_free else (float(raw_cov) if raw_cov is not None else 0.0)
        flag_liq = bool(r["flag_acute_liquidity"])
        flag_div = bool(r["flag_accrual_divergence"])

        if flag_liq:
            status = "TEKANAN_LIKUIDITAS"
            badge = "Red (Critical)"
        elif flag_div:
            status = "DIVERGENSI_AKRUAL"
            badge = "Amber (Caution)"
        elif is_free:
            status = "BEBAS_UTANG"
            badge = "Green (Fortress)"
        elif cov >= 1.0:
            status = "SOLVEN_SEHAT"
            badge = "Green (Healthy)"
        else:
            status = "TERKENDALI"
            badge = "Amber (Moderate)"

        def _safe_int(val: Any) -> int:
            return int(Decimal(str(val))) if val not in (None, "") else 0

        r["status_code"] = status
        r["status_label"] = badge
        r["cash_idr"] = _safe_int(r.get("cash_idr"))
        r["st_debt_idr"] = _safe_int(r.get("st_debt_idr"))
        r["cfo_ttm_idr"] = _safe_int(r.get("cfo_ttm_idr"))
        r["net_income_ttm_idr"] = _safe_int(r.get("net_income_ttm_idr"))
        r["total_assets_idr"] = _safe_int(r.get("total_assets_idr"))
        r["total_liabilities_idr"] = _safe_int(r.get("total_liabilities_idr"))
        r["receivables_idr"] = _safe_int(r.get("receivables_idr"))
        r["bank_loans_idr"] = _safe_int(r.get("bank_loans_idr"))
        r["bonds_sukuk_idr"] = _safe_int(r.get("bonds_sukuk_idr"))
        r["revenue_ttm_idr"] = _safe_int(r.get("revenue_ttm_idr"))
        r["sloan_ratio_pct"] = round(float(r["sloan_ratio_ttm"] or 0.0) * 100, 2)
        r["cash_coverage_display"] = (
            "Debt-Free" if is_free else (f"{float(raw_cov):.2f}x" if raw_cov else "0.00x")
        )

    return rows


@app.get("/api/leaderboard")
def get_leaderboard(
    fiscal_year: int = 2025, sector: str | None = None
) -> list[dict[str, Any]]:
    """Returns solvency leaderboard ranking for the specified fiscal year and sector."""
    where_clause = (
        "WHERE f.filing_id = ("
        "SELECT f2.filing_id FROM filings f2 "
        "JOIN computed_metrics cm2 ON f2.filing_id = cm2.filing_id "
        "WHERE f2.ticker = f.ticker "
        "ORDER BY CASE WHEN f2.fiscal_year = ? THEN 0 ELSE 1 END, "
        "f2.fiscal_year DESC LIMIT 1)"
    )
    params: list[Any] = [fiscal_year]

    cond = _build_sector_condition(sector, "i.idx_sub_industry")
    if cond:
        where_clause += f" AND {cond}"

    query = f"""
    SELECT cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
           cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.cfo_ttm_idr,
           cm.flag_acute_liquidity, cm.flag_accrual_divergence
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    {where_clause};
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    def sort_key(item: dict[str, Any]) -> tuple[int, float]:
        is_safe = 0 if item.get("flag_acute_liquidity") else 1
        is_free = 1 if item.get("debt_free_short_term") else 0
        cov = item.get("cash_coverage_ratio")
        effective_cov = 9999.0 if is_free else (float(cov) if cov is not None else 0.0)
        return (is_safe, effective_cov)

    sorted_rows = sorted(rows, key=sort_key, reverse=True)
    for idx, r in enumerate(sorted_rows, start=1):
        r["rank"] = idx
    return sorted_rows


@app.get("/api/radar")
def get_radar_matrix(
    fiscal_year: int = 2025, sector: str | None = None
) -> list[dict[str, Any]]:
    """
    Returns 2D scatter plot matrix data:
    X: Cash Coverage Ratio
    Y: Sloan Accrual Ratio
    Color/Category: SAFE, ACCRUAL_DIVERGENCE, ACUTE_LIQUIDITY
    """
    where_clause = (
        "WHERE f.filing_id = ("
        "SELECT f2.filing_id FROM filings f2 "
        "JOIN computed_metrics cm2 ON f2.filing_id = cm2.filing_id "
        "WHERE f2.ticker = f.ticker "
        "ORDER BY CASE WHEN f2.fiscal_year = ? THEN 0 ELSE 1 END, "
        "f2.fiscal_year DESC LIMIT 1)"
    )
    params: list[Any] = [fiscal_year]

    cond = _build_sector_condition(sector, "i.idx_sub_industry")
    if cond:
        where_clause += f" AND {cond}"

    query = f"""
    SELECT cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
           cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.flag_acute_liquidity,
           cm.flag_accrual_divergence
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    {where_clause};
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    points: list[dict[str, Any]] = []
    for r in rows:
        free = bool(r["debt_free_short_term"])
        raw_cov = r["cash_coverage_ratio"]
        cov = 25.0 if free else (float(raw_cov) if raw_cov else 0.0)
        sloan = float(r["sloan_ratio_ttm"]) if r["sloan_ratio_ttm"] else 0.0

        if r["flag_acute_liquidity"]:
            category = "ACUTE_LIQUIDITY"
            color = "#ef4444"  # Red
        elif r["flag_accrual_divergence"]:
            category = "ACCRUAL_DIVERGENCE"
            color = "#f59e0b"  # Amber
        else:
            category = "HEALTHY"
            color = "#10b981"  # Emerald

        points.append({
            "ticker": r["ticker"],
            "company_name": r["company_name"],
            "sub_industry": r["idx_sub_industry"],
            "x_cash_coverage": cov,
            "y_sloan_accrual": sloan,
            "debt_free": free,
            "category": category,
            "color": color,
        })

    return points


@app.get("/api/analytics/regression")
def get_regression_analytics(
    fiscal_year: int = 2025,
    sector: str | None = None,
    predict_x: float | None = None,
) -> dict[str, Any]:
    """
    Computes empirical Ordinary Least Squares (OLS) Linear Regression:
    Independent Variable (X): Cash Coverage Ratio
    Dependent Variable (Y): Sloan Accrual Ratio
    Provides R^2, correlation, standard error, confidence intervals,
    and identifies statistical outliers / predictive distress signals.
    """
    where_clause = (
        "WHERE f.filing_id = ("
        "SELECT f2.filing_id FROM filings f2 "
        "JOIN computed_metrics cm2 ON f2.filing_id = cm2.filing_id "
        "WHERE f2.ticker = f.ticker "
        "ORDER BY CASE WHEN f2.fiscal_year = ? THEN 0 ELSE 1 END, "
        "f2.fiscal_year DESC LIMIT 1)"
    )
    params: list[Any] = [fiscal_year]

    cond = _build_sector_condition(sector, "i.idx_sub_industry")
    if cond:
        where_clause += f" AND {cond}"

    query = f"""
    SELECT cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
           cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.flag_acute_liquidity,
           cm.flag_accrual_divergence
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    {where_clause};
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    data_points: list[dict[str, Any]] = []
    x_vals: list[float] = []
    y_vals: list[float] = []

    for r in rows:
        free = bool(r["debt_free_short_term"])
        raw_cov = r["cash_coverage_ratio"]
        x = 5.0 if free else (float(raw_cov) if raw_cov is not None else 0.5)
        x = min(max(x, 0.0), 8.0)
        y = float(r["sloan_ratio_ttm"]) if r["sloan_ratio_ttm"] is not None else 0.0

        x_vals.append(x)
        y_vals.append(y)
        data_points.append({
            "ticker": r["ticker"],
            "company_name": r["company_name"],
            "sub_industry": r["idx_sub_industry"],
            "x": round(x, 2),
            "y": round(y, 4),
        })

    n = len(x_vals)
    if n < 3:
        return {"status": "insufficient_data", "sample_size": n}

    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n
    ss_xx = sum((xi - mean_x) ** 2 for xi in x_vals)
    ss_yy = sum((yi - mean_y) ** 2 for yi in y_vals)
    ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x_vals, y_vals, strict=False))

    slope = ss_xy / ss_xx if ss_xx != 0 else 0.0
    intercept = mean_y - slope * mean_x

    residuals = [yi - (slope * xi + intercept) for xi, yi in zip(x_vals, y_vals, strict=False)]
    ss_res = sum(r ** 2 for r in residuals)
    r_squared = max(0.0, 1.0 - (ss_res / ss_yy)) if ss_yy > 0 else 0.0
    corr_r = (slope / abs(slope) if slope != 0 else 1.0) * math.sqrt(r_squared)
    se_res = math.sqrt(ss_res / (n - 2)) if n > 2 else 0.0

    outliers = []
    for dp, res in zip(data_points, residuals, strict=False):
        z = res / se_res if se_res > 0 else 0.0
        dp["residual"] = round(res, 4)
        dp["z_residual"] = round(z, 2)
        if z > 1.25:
            dp["anomaly_status"] = "HIGH_ACCRUAL_ANOMALY"
            outliers.append(dp)
        elif z < -1.25:
            dp["anomaly_status"] = "EXCESS_CFO_EFFICIENCY"
        else:
            dp["anomaly_status"] = "EQUILIBRIUM"

    trendline = []
    step = 0.5
    curr_x = 0.0
    max_x = max(x_vals) if x_vals else 5.0
    while curr_x <= max_x + 0.5:
        y_hat = slope * curr_x + intercept
        trendline.append({
            "x": round(curr_x, 1),
            "y": round(y_hat, 4),
            "upper_band": round(y_hat + 1.5 * se_res, 4),
            "lower_band": round(y_hat - 1.5 * se_res, 4),
        })
        curr_x += step

    forecast = None
    if predict_x is not None:
        pred_y = slope * predict_x + intercept
        risk_class = (
            "HIGH_DISTRESS_RISK"
            if pred_y > 0.10 and predict_x < 0.5
            else ("MODERATE_RISK" if pred_y > 0.05 else "HEALTHY_LIQUIDITY")
        )
        if predict_x >= 1.0:
            takeaway = (
                f"At {predict_x:.2f}x cash coverage, the issuer holds Rp {predict_x:.2f} "
                f"in cash for every Rp 1.00 of debt due this year. The expected Sloan Accrual "
                f"of {pred_y * 100:.1f}% indicates profits are well-backed by real cash flow."
            )
        elif predict_x >= 0.5:
            takeaway = (
                f"At {predict_x:.2f}x cash coverage, cash reserves cover {predict_x * 100:.0f}% "
                f"of short-term debt. Solvency is stable but requires disciplined working capital."
            )
        else:
            takeaway = (
                f"At {predict_x:.2f}x cash coverage, immediate cash reserves are below 50% "
                f"of debt obligations due within 12 months, signaling tight liquidity."
            )

        forecast = {
            "input_cash_coverage": predict_x,
            "predicted_sloan_accrual": round(pred_y, 4),
            "confidence_lower_95": round(pred_y - 1.96 * se_res, 4),
            "confidence_upper_95": round(pred_y + 1.96 * se_res, 4),
            "risk_assessment": risk_class,
            "plain_english_takeaway": takeaway,
        }

    return {
        "status": "success",
        "model_type": "Ordinary Least Squares (OLS) Linear Regression",
        "sample_size": n,
        "parameters": {
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "r_squared": round(r_squared, 4),
            "correlation_r": round(corr_r, 4),
            "residual_std_error": round(se_res, 4),
            "equation_formula": f"SloanAccrual = {intercept:.4f} + ({slope:.4f} * CashCoverage)",
        },
        "trendline": trendline,
        "outliers": outliers,
        "forecast": forecast,
    }


@app.get("/api/ml/distress-rankings")
def get_ml_distress_rankings(
    fiscal_year: int = 2025, sector: str | None = None
) -> list[dict[str, Any]]:
    """
    Ranks all issuers by multivariate logistic distress probability P(Distress).
    Applies calibrated empirical weights across Cash Coverage, Sloan Accrual,
    CFO Margin, and PSAK 72 Contract Exposure.
    """
    where_clause = (
        "WHERE f.filing_id = ("
        "SELECT f2.filing_id FROM filings f2 "
        "JOIN computed_metrics cm2 ON f2.filing_id = cm2.filing_id "
        "WHERE f2.ticker = f.ticker "
        "ORDER BY CASE WHEN f2.fiscal_year = ? THEN 0 ELSE 1 END, "
        "f2.fiscal_year DESC LIMIT 1)"
    )
    params: list[Any] = [fiscal_year]

    cond = _build_sector_condition(sector, "i.idx_sub_industry")
    if cond:
        where_clause += f" AND {cond}"

    query = f"""
    SELECT cm.ticker, i.company_name, i.idx_sub_industry, cm.cash_coverage_ratio,
           cm.debt_free_short_term, cm.sloan_ratio_ttm, cm.cfo_ttm_idr,
           cm.revenue_ttm_idr, cm.gross_contract_exposure_ratio
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    JOIN issuers i ON cm.ticker = i.ticker
    {where_clause};
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    results: list[dict[str, Any]] = []
    for r in rows:
        eval_res = ml_suite.compute_distress_probability(r)
        results.append({
            "ticker": r["ticker"],
            "company_name": r["company_name"],
            "sub_industry": r["idx_sub_industry"],
            "cash_coverage": r["cash_coverage_ratio"],
            "debt_free": bool(r["debt_free_short_term"]),
            "sloan_accrual": r["sloan_ratio_ttm"],
            **eval_res,
        })

    # Sort descending by distress probability
    results.sort(key=lambda x: x["distress_probability"], reverse=True)
    for rank, item in enumerate(results, start=1):
        item["risk_rank"] = rank
    return results


@app.get("/api/ml/forecast/{ticker}")
def get_ml_forecast(ticker: str, years: int = 2) -> dict[str, Any]:
    """
    Returns time-series trend projections (FY 2026-2027) for CFO and Cash Coverage
    fitted on historical audited filings with 90% confidence bands.
    """
    t = ticker.strip().upper()
    res = ml_suite.forecast_cash_flow_trajectory(t, forecast_years=years)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@app.get("/api/ml/feature-importance")
def get_ml_feature_importance() -> list[dict[str, Any]]:
    """Returns empirical feature sensitivity matrix and academic references."""
    return ml_suite.get_feature_importance_matrix()


@app.get("/api/metrics/{ticker}")
def get_issuer_metrics(ticker: str) -> dict[str, Any]:
    """Returns 4-year trend and detailed computed metrics for an issuer."""
    t = ticker.strip().upper()
    issuer = repo.get_issuer(t)
    if not issuer:
        raise HTTPException(status_code=404, detail=f"Issuer {t} not found")

    query = """
    SELECT f.fiscal_year, f.period_code, cm.*
    FROM computed_metrics cm
    JOIN filings f ON cm.filing_id = f.filing_id
    WHERE cm.ticker = ?
    ORDER BY f.fiscal_year ASC;
    """
    with repo.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(query, (t,)).fetchall()]

    return {
        "ticker": t,
        "company_name": issuer.company_name,
        "history": rows,
    }


@app.get("/api/calk/{ticker}")
def get_calk_breakdown(ticker: str) -> dict[str, Any]:
    """Returns CALK footnote breakdown and verbatim grounding audit trail."""
    t = ticker.strip().upper()
    samples_dir = ROOT_DIR / "data" / "calk_samples"
    files = list(samples_dir.glob(f"{t}_*.txt"))
    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"CALK sample not found for {t}. Available: WIKA, TOTL, PTPP, ADHI, WSKT, ACST",
        )

    text = files[0].read_text(encoding="utf-8")
    footnote_num = "Catatan 8" if "Catatan 8" in text else "Catatan 7"
    extraction = calk_extractor.extract_from_text(
        ticker=t,
        fiscal_year=2023,
        source_text=text,
        footnote_number=footnote_num,
        footnote_title="Trade Receivables & Contract Assets",
        page_number=45,
    )
    return extraction.model_dump()


@app.get("/api/news/daily")
def get_daily_news_snapshot() -> dict[str, Any]:
    """Returns latest daily news sentiment snapshot produced by the cron job."""
    return load_daily_news()


@app.get("/api/cron/daily-news")
@app.post("/api/news/daily/refresh")
def run_daily_news_cron() -> dict[str, Any]:
    """Executes daily RSS news sentiment refresh across all covered IDX issuers."""
    issuers = get_issuers()
    return refresh_daily_news(issuers, max_per_ticker=3, max_workers=8)


@app.get("/api/news/{ticker}")
def get_issuer_news_sentiment(ticker: str) -> list[dict[str, Any]]:
    """
    Returns verified stock exchange disclosures and news sentiment for an issuer.
    Classified into POSITIF, NETRAL, and PERHATIAN with contextual isolation.
    """
    t = ticker.strip().upper()
    items = news_radar.get_news_for_ticker(t, max_items=5)
    return [i.model_dump() for i in items]


@app.post("/api/news/analyze-url")
def analyze_realtime_news_link(
    req: NewsAnalyzeRequest,
    x_gemini_api_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
) -> dict[str, Any]:
    """
    Real-Time News Link Sentiment + Accrual Radar Cross-Check Endpoint.
    Fetches a public news URL (or raw article text), detects the BEI ticker,
    computes deterministic sentiment signals, and cross-checks against audited XBRL data.
    """
    url = (req.url or "").strip()
    raw_text = (req.raw_text or "").strip()
    if not url and not raw_text:
        raise HTTPException(
            status_code=400,
            detail="Please enter a news URL or paste the article text.",
        )

    headline = ""
    body_text = ""
    source = "Manual Text"
    highlights: list[str] = []

    if url and not raw_text:
        fetched = fetch_article_from_url(url)
        if fetched.get("status") != "success":
            raise HTTPException(
                status_code=422, detail=fetched.get("message", "Failed to fetch URL.")
            )
        headline = fetched.get("headline", "")
        body_text = fetched.get("body_text", "")
        source = fetched.get("source", "Web Source")
        highlights = fetched.get("highlights", [])
    else:
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        headline = lines[0][:180] if lines else "Stock News Article"
        body_text = "\n".join(lines[1:] if len(lines) > 1 else lines)[:4000]
        highlights = extract_key_highlights(headline, lines)

    issuers = get_issuers()
    selected_ticker = (req.ticker or "").strip().upper()
    detected_tickers = detect_all_tickers_in_article(
        f"{headline}\n{body_text}", issuers, url=url
    )
    detected_ticker = selected_ticker or detect_ticker_in_article(
        f"{headline}\n{body_text}", issuers, url=url
    )
    if detected_ticker and detected_ticker not in detected_tickers:
        detected_tickers.insert(0, detected_ticker)

    sentiment_res = analyze_sentiment_deterministic(headline, body_text)

    fundamentals: dict[str, Any] | None = None
    company_name = ""
    sub_industry = ""
    synthesis: dict[str, Any] | None = None
    ml_forecast: dict[str, Any] | None = None

    if detected_ticker:
        screener_rows = get_screener_data(2025)
        matched_row = next((r for r in screener_rows if r["ticker"] == detected_ticker), None)
        if matched_row:
            distress_rows = get_ml_distress_rankings(2025)
            d_row = next((d for d in distress_rows if d["ticker"] == detected_ticker), {})
            fundamentals = {
                **matched_row,
                "distress_probability_pct": d_row.get("distress_probability_pct", 0.0),
                "synthetic_rating": d_row.get("synthetic_rating", "N/A"),
                "credit_classification": d_row.get("credit_classification", "N/A"),
            }
            company_name = matched_row.get("company_name", detected_ticker)
            sub_industry = matched_row.get("idx_sub_industry", "-")
            fc = ml_suite.forecast_cash_flow_trajectory(detected_ticker, forecast_years=2)
            if fc.get("status") == "success":
                ml_forecast = fc
            user_byok = (x_gemini_api_key or "").strip() or None
            synthesis = synthesize_news_vs_accrual(
                ticker=detected_ticker,
                company_name=company_name,
                fundamentals=fundamentals,
                sentiment_res=sentiment_res,
                headline=headline,
                highlights=highlights,
                api_key=user_byok,
                ml_forecast=ml_forecast,
            )

    return {
        "status": "success",
        "url": url or None,
        "source": source,
        "headline": headline,
        "highlights": highlights,
        "sentiment": sentiment_res["sentiment"],
        "matched_positive": sentiment_res["matched_positive"],
        "matched_warning": sentiment_res["matched_warning"],
        "detected_ticker": detected_ticker,
        "detected_tickers": detected_tickers,
        "company_name": company_name,
        "sub_industry": sub_industry,
        "fundamentals": fundamentals,
        "analysis_awam": synthesis["analysis_awam"] if synthesis else None,
        "analysis_expert": synthesis["analysis_expert"] if synthesis else None,
        "outlook_stance": synthesis.get("outlook_stance") if synthesis else None,
        "forecast_awam": synthesis.get("forecast_awam") if synthesis else None,
        "forecast_expert": synthesis.get("forecast_expert") if synthesis else None,
        "watchpoints": synthesis.get("watchpoints", []) if synthesis else [],
        "ml_forecast": ml_forecast,
        "engine_source": synthesis["engine_source"] if synthesis else "Sentiment Only",
        "contextual_isolation_rule": (
            "Contextual Isolation Rule Active: News sentiment is strictly secondary context "
            "and does not alter deterministic cash safeguard flags."
        ),
    }


@app.post("/api/chat")
def post_chat(
    req: ChatRequest,
    x_gemini_api_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
) -> dict[str, Any]:
    """Answers conversational financial intelligence questions using grounded RAG."""
    query = req.message.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query message cannot be empty")
    user_byok = (x_gemini_api_key or "").strip() or None
    byok_only = os.getenv("BYOK_ONLY", "true" if os.getenv("VERCEL") else "false").lower() in ("1", "true", "yes")
    answer = rag_chatbot.answer_query(
        query,
        api_key_override=user_byok,
        allow_server_key=not byok_only,
    )
    return {
        "status": "success",
        "query": query,
        "response": answer,
        "byok_used": bool(user_byok),
    }


@app.get("/api/market/quotes")
def get_market_quotes(tickers: str | None = None) -> dict[str, Any]:
    """
    Returns near-real-time IDX stock quotes (.JK via Yahoo Finance) with 5-minute cache.
    Strictly descriptive market context (no buy/sell signals or price targets).
    """
    if tickers:
        target_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        target_list = [r["ticker"] for r in get_issuers()]
    quotes = fetch_batch_quotes(target_list)
    return {"status": "ok", "count": len(quotes), "quotes": quotes}


@app.get("/api/market/quote/{ticker}")
def get_market_quote_single(ticker: str) -> dict[str, Any]:
    """Returns near-real-time IDX stock quote for a single ticker."""
    t = ticker.strip().upper()
    q = fetch_single_quote(t)
    if not q:
        raise HTTPException(status_code=404, detail=f"Live quote unavailable for {t}")
    return q


@app.get("/api/market/history/{ticker}")
def get_market_history(ticker: str, range: str = "3mo") -> dict[str, Any]:
    """Returns historical price series for Stockbit-style interactive stock chart."""
    t = ticker.strip().upper()
    hist = fetch_price_history(t, range_str=range)
    if not hist:
        raise HTTPException(status_code=404, detail=f"Price history unavailable for {t}")
    return hist


class NeuralStressRequest(BaseModel):
    ticker: str
    capital_idr: float = 10_000_000.0
    cash_shock_pct: float = 0.0
    debt_shock_pct: float = 0.0


class PortfolioHoldingItem(BaseModel):
    ticker: str
    amount_idr: float = 5_000_000.0


class PortfolioXRayRequest(BaseModel):
    holdings: list[PortfolioHoldingItem]
    cash_shock_pct: float = 0.0
    debt_shock_pct: float = 0.0


def _compute_book_cash_backing(
    repo_obj: FinancialRepository, row: dict[str, Any], capital_idr: float
) -> dict[str, Any]:
    """Computes proportional Cash, ST Debt, and CFO backing per user capital on audited Book Equity."""
    t = row["ticker"]
    equity = 0.0
    total_assets = 0.0
    try:
        with repo_obj.get_connection() as conn:
            facts = conn.execute(
                """
                SELECT cf.canonical_key, cf.value_idr
                FROM canonical_facts cf
                JOIN filings f ON f.filing_id = cf.filing_id
                WHERE f.ticker = ? AND cf.canonical_key IN ('total_equity', 'total_assets')
                ORDER BY f.fiscal_year DESC
                """,
                (t,),
            ).fetchall()
            for r in facts:
                k = r["canonical_key"]
                if k == "total_equity" and equity == 0.0:
                    equity = float(r["value_idr"] or 0.0)
                elif k == "total_assets" and total_assets == 0.0:
                    total_assets = float(r["value_idr"] or 0.0)
    except Exception:
        pass

    cash_idr = float(row.get("cash_idr") or 0.0)
    st_debt_idr = float(row.get("st_debt_idr") or 0.0)
    cfo_idr = float(row.get("cfo_ttm_idr") or 0.0)
    cap = max(float(capital_idr or 10_000_000.0), 100_000.0)

    if equity > 0:
        cash_per_modal = round(cap * (cash_idr / equity), 0)
        debt_per_modal = round(cap * (st_debt_idr / equity), 0)
        cfo_per_modal = round(cap * (cfo_idr / equity), 0)
        cfo_roe_pct = round((cfo_idr / equity) * 100.0, 2)
    else:
        cash_per_modal = 0.0
        debt_per_modal = 0.0
        cfo_per_modal = 0.0
        cfo_roe_pct = None

    cash_pct_assets = round((cash_idr / total_assets) * 100.0, 2) if total_assets > 0 else None
    return {
        "basis": "Audited Book Equity (FY 2025)",
        "equity_idr": round(equity, 0),
        "total_assets_idr": round(total_assets, 0),
        "cash_per_modal_idr": cash_per_modal,
        "debt_per_modal_idr": debt_per_modal,
        "cfo_per_modal_idr": cfo_per_modal,
        "cash_pct_assets": cash_pct_assets,
        "cfo_to_equity_pct": cfo_roe_pct,
    }


@app.post("/api/ml/neural-stress")
def post_neural_stress_simulation(req: NeuralStressRequest) -> dict[str, Any]:
    """
    Runs the self-trained 3-layer Deep Learning MLP (5 -> 16 -> 8 -> 1) on an issuer's
    audited XBRL metrics under user-defined money & stress scenarios, plus Book Equity Cash Backing.
    """
    t = req.ticker.strip().upper()
    rows = get_screener_data()
    target = next((r for r in rows if r["ticker"] == t), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Issuer {t} not found")

    res = ml_suite.run_neural_capital_stress(
        target,
        capital_idr=req.capital_idr,
        cash_shock_pct=req.cash_shock_pct,
        debt_shock_pct=req.debt_shock_pct,
    )
    backing = _compute_book_cash_backing(repo, target, req.capital_idr)

    same_sec = [
        r for r in rows
        if r.get("idx_sub_industry") == target.get("idx_sub_industry") and r["ticker"] != t
    ]
    pool = same_sec if same_sec else [r for r in rows if r["ticker"] != t]
    peer_best = None
    best_prob = 999.0
    for cand in pool:
        p_res = ml_suite.run_neural_capital_stress(
            cand,
            capital_idr=req.capital_idr,
            cash_shock_pct=req.cash_shock_pct,
            debt_shock_pct=req.debt_shock_pct,
        )
        if p_res["stressed_risk_pct"] < best_prob:
            best_prob = p_res["stressed_risk_pct"]
            peer_best = {
                "ticker": cand["ticker"],
                "company_name": cand.get("company_name"),
                "stressed_risk_pct": p_res["stressed_risk_pct"],
                "stressed_capital_at_risk_idr": p_res["stressed_capital_at_risk_idr"],
                "debt_free_short_term": bool(cand.get("debt_free_short_term")),
            }

    return {
        "status": "ok",
        "ticker": t,
        "company_name": target.get("company_name"),
        "sub_industry": target.get("idx_sub_industry"),
        "simulation": res,
        "cash_backing": backing,
        "safest_peer": peer_best,
    }


@app.post("/api/ml/portfolio-xray")
def post_portfolio_xray(req: PortfolioXRayRequest) -> dict[str, Any]:
    """
    Multi-stock Portfolio Cash-Safety X-Ray: evaluates weighted liquidity exposure,
    cash-fortress share, weakest-link ticker, and safer peer benchmark across 2-5 IDX holdings.
    """
    if not req.holdings:
        raise HTTPException(status_code=400, detail="Please add at least 1 stock holding.")

    rows = get_screener_data()
    row_map = {r["ticker"]: r for r in rows}

    evaluated: list[dict[str, Any]] = []
    total_cap = 0.0
    total_at_risk = 0.0
    safe_cap = 0.0
    flagged_cap = 0.0

    for h in req.holdings[:8]:
        t = h.ticker.strip().upper()
        amt = max(float(h.amount_idr or 0.0), 0.0)
        if amt <= 0 or t not in row_map:
            continue
        r = row_map[t]
        sim = ml_suite.run_neural_capital_stress(
            r,
            capital_idr=amt,
            cash_shock_pct=req.cash_shock_pct,
            debt_shock_pct=req.debt_shock_pct,
        )
        sub = (r.get("idx_sub_industry") or "").upper()
        is_bank = "BANK" in sub or "FINANC" in sub
        is_free = (not is_bank) and bool(r.get("debt_free_short_term"))
        cov = None if (is_bank or is_free) else float(r.get("cash_coverage_ratio") or 0.0)
        is_flagged = bool(r.get("flag_acute_liquidity") or r.get("flag_accrual_divergence") or (not is_bank and not is_free and (cov or 0.0) < 1.0))

        total_cap += amt
        total_at_risk += sim["stressed_capital_at_risk_idr"]
        if is_flagged:
            flagged_cap += amt
        else:
            safe_cap += amt

        evaluated.append({
            "ticker": t,
            "company_name": r.get("company_name"),
            "sub_industry": r.get("idx_sub_industry"),
            "is_bank": is_bank,
            "debt_free": is_free,
            "amount_idr": round(amt, 0),
            "cash_coverage": cov,
            "cfo_ttm_idr": float(r.get("cfo_ttm_idr") or 0.0),
            "stressed_risk_pct": sim["stressed_risk_pct"],
            "capital_at_risk_idr": sim["stressed_capital_at_risk_idr"],
            "is_flagged": is_flagged,
        })

    if not evaluated or total_cap <= 0:
        raise HTTPException(status_code=400, detail="No valid holdings with positive IDR amount.")

    for item in evaluated:
        item["weight_pct"] = round((item["amount_idr"] / total_cap) * 100.0, 1)

    weakest = max(evaluated, key=lambda x: x["capital_at_risk_idr"])
    # Find safer peer in weakest holding's sub-industry
    weak_row = row_map[weakest["ticker"]]
    same_sec = [
        r for r in rows
        if r.get("idx_sub_industry") == weak_row.get("idx_sub_industry") and r["ticker"] != weakest["ticker"]
    ]
    peer_bench = None
    if same_sec:
        best_p = min(
            same_sec,
            key=lambda c: ml_suite.run_neural_capital_stress(
                c, weakest["amount_idr"], req.cash_shock_pct, req.debt_shock_pct
            )["stressed_risk_pct"],
        )
        p_sim = ml_suite.run_neural_capital_stress(
            best_p, weakest["amount_idr"], req.cash_shock_pct, req.debt_shock_pct
        )
        new_total_risk = total_at_risk - weakest["capital_at_risk_idr"] + p_sim["stressed_capital_at_risk_idr"]
        peer_bench = {
            "replace_ticker": weakest["ticker"],
            "peer_ticker": best_p["ticker"],
            "peer_risk_pct": p_sim["stressed_risk_pct"],
            "portfolio_risk_before_pct": round((total_at_risk / total_cap) * 100.0, 2),
            "portfolio_risk_after_pct": round((new_total_risk / total_cap) * 100.0, 2),
        }

    return {
        "status": "ok",
        "total_capital_idr": round(total_cap, 0),
        "safe_capital_idr": round(safe_cap, 0),
        "safe_pct": round((safe_cap / total_cap) * 100.0, 1),
        "flagged_capital_idr": round(flagged_cap, 0),
        "flagged_pct": round((flagged_cap / total_cap) * 100.0, 1),
        "weighted_risk_pct": round((total_at_risk / total_cap) * 100.0, 2),
        "total_capital_at_risk_idr": round(total_at_risk, 0),
        "weakest_link": weakest,
        "peer_benchmark": peer_bench,
        "holdings": evaluated,
    }


@app.get("/", response_class=HTMLResponse)
def get_dashboard() -> str:
    """Renders interactive HTML Dashboard."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return "<h1>IDX Cash & Accrual Radar Dashboard</h1>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.app:app", host="0.0.0.0", port=8000, reload=True)
