"""
Self-Growing Knowledge Base Ingestor for IDX Cash & Accrual Radar.
Allows users to add new BEI tickers via structured financial statements
or uploaded XBRL (.xml / .zip) filings, computing all ratios deterministically
and persisting them into SQLite for immediate Screener, Radar, and Chatbot use.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.db.repository import FinancialRepository
from src.engine.calculator import (
    calculate_cash_coverage,
    calculate_contract_exposure,
    calculate_sloan_accrual,
)
from src.engine.llm_explainer import check_language_compliance
from src.engine.news_radar import CURATED_DISCLOSURES
from src.engine.safeguards import evaluate_safeguards
from src.models.canonical import CanonicalFactModel, FilingModel, IssuerModel
from src.models.metrics import ComputedFilingMetrics
from src.parser.normalizer import TaxonomyNormalizer
from src.parser.xbrl_reader import read_xbrl_document

CUSTOM_DISCLOSURES_PATH = Path(__file__).parents[2] / "data" / "custom_disclosures.json"
USER_XBRL_DIR = Path(__file__).parents[2] / "data" / "user_xbrl"


def load_custom_disclosures() -> None:
    """Loads persisted user-contributed disclosures into CURATED_DISCLOSURES."""
    if not CUSTOM_DISCLOSURES_PATH.exists():
        return
    try:
        data = json.loads(CUSTOM_DISCLOSURES_PATH.read_text(encoding="utf-8"))
        for ticker, items in data.items():
            t = ticker.upper()
            existing = CURATED_DISCLOSURES.setdefault(t, [])
            existing_heads = {i.get("headline") for i in existing}
            for it in items:
                if it.get("headline") not in existing_heads:
                    existing.insert(0, it)
    except Exception:
        pass


def save_custom_disclosure(ticker: str, headline: str, detail: str = "") -> None:
    """Appends a compliant user disclosure/context note for a ticker."""
    clean_hl = headline.strip()
    if not clean_hl or not check_language_compliance(f"{clean_hl} {detail}"):
        return

    entry = {
        "date": date.today().strftime("%d %b %Y"),
        "headline": clean_hl,
        "source": "Kontribusi Pengetahuan Pengguna",
    }
    if detail.strip():
        entry["detail"] = detail.strip()

    CURATED_DISCLOSURES.setdefault(ticker, []).insert(0, entry)

    CUSTOM_DISCLOSURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, list[dict[str, str]]] = {}
    if CUSTOM_DISCLOSURES_PATH.exists():
        try:
            current = json.loads(CUSTOM_DISCLOSURES_PATH.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current.setdefault(ticker, []).insert(0, entry)
    CUSTOM_DISCLOSURES_PATH.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def validate_ticker(ticker: str) -> str:
    """Validates standard 4-letter uppercase IDX ticker symbol."""
    t = ticker.strip().upper()
    if not re.match(r"^[A-Z]{4}$", t):
        raise ValueError("Kode saham BEI wajib tepat 4 huruf kapital (contoh: BBCA, ASII, PWON).")
    return t


def ingest_structured_issuer(
    repo: FinancialRepository,
    ticker: str,
    company_name: str,
    idx_sub_industry: str,
    fiscal_year: int,
    cash_idr: Decimal,
    st_debt_bank_idr: Decimal,
    st_debt_bonds_idr: Decimal,
    cfo_ttm_idr: Decimal,
    net_income_ttm_idr: Decimal,
    revenue_ttm_idr: Decimal,
    total_assets_idr: Decimal,
    total_liabilities_idr: Decimal = Decimal("0"),
    receivables_idr: Decimal = Decimal("0"),
    source_note: str | None = None,
) -> dict[str, Any]:
    """
    Validates, computes deterministic ratios, and persists a new or updated
    issuer filing into SQLite so it becomes immediately queryable across the platform.
    """
    clean_ticker = validate_ticker(ticker)
    clean_name = company_name.strip() or f"PT {clean_ticker} Tbk."
    clean_sector = idx_sub_industry.strip() or "Sektor Umum BEI"

    q1 = Decimal("1")
    cash_idr = cash_idr.quantize(q1)
    st_debt_bank_idr = st_debt_bank_idr.quantize(q1)
    st_debt_bonds_idr = st_debt_bonds_idr.quantize(q1)
    cfo_ttm_idr = cfo_ttm_idr.quantize(q1)
    net_income_ttm_idr = net_income_ttm_idr.quantize(q1)
    revenue_ttm_idr = revenue_ttm_idr.quantize(q1)
    total_assets_idr = total_assets_idr.quantize(q1)
    total_liabilities_idr = total_liabilities_idr.quantize(q1)
    receivables_idr = receivables_idr.quantize(q1)

    if total_assets_idr <= Decimal("0"):
        raise ValueError("Total Aset wajib bernilai lebih besar dari Rp 0.")

    period_end = f"{fiscal_year}-12-31"
    filing_id = f"{clean_ticker}_{fiscal_year}_FY_FIRST"

    payload_digest = hashlib.sha256(
        json.dumps(
            {
                "ticker": clean_ticker,
                "fiscal_year": fiscal_year,
                "cash": str(cash_idr),
                "st_bank": str(st_debt_bank_idr),
                "st_bonds": str(st_debt_bonds_idr),
                "cfo": str(cfo_ttm_idr),
                "ni": str(net_income_ttm_idr),
                "rev": str(revenue_ttm_idr),
                "assets": str(total_assets_idr),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    # 1. Persist Issuer & Filing header
    repo.save_issuer(
        IssuerModel(
            ticker=clean_ticker,
            company_name=clean_name,
            idx_sub_industry=clean_sector,
            listing_status="ACTIVE",
        )
    )
    repo.save_filing(
        FilingModel(
            filing_id=filing_id,
            ticker=clean_ticker,
            fiscal_year=fiscal_year,
            period_code="FY",
            period_end_date=period_end,
            filing_date=date.today().isoformat(),
            is_audited=True,
            is_restatement=False,
            reporting_currency="IDR",
            fx_rate_to_idr=Decimal("1"),
            sanity_check_passed=True,
            source_xbrl_hash=f"USER_VERIFIED_{payload_digest[:16]}",
        )
    )

    # 2. Persist Canonical Facts
    fact_specs = [
        ("cash_and_equivalents", cash_idr, "cor_CashAndCashEquivalents"),
        ("st_debt_bank_loans", st_debt_bank_idr, "cor_ShortTermBankLoans"),
        (
            "st_debt_current_maturities_bonds_sukuk_mtn",
            st_debt_bonds_idr,
            "cor_CurrentMaturitiesOfBondsPayable",
        ),
        ("total_assets", total_assets_idr, "cor_Assets"),
        ("total_liabilities", total_liabilities_idr, "cor_Liabilities"),
        ("trade_receivables_third_parties", receivables_idr, "cor_TradeReceivablesThirdParties"),
        ("revenue", revenue_ttm_idr, "cor_Revenue"),
        ("net_income", net_income_ttm_idr, "cor_ProfitLoss"),
        ("cfo", cfo_ttm_idr, "cor_NetCashFlowsFromUsedInOperatingActivities"),
    ]
    canonical_models = [
        CanonicalFactModel(
            canonical_key=k,
            value_idr=v,
            raw_xbrl_tag=tag,
            raw_context_ref=f"USER_FY_{fiscal_year}",
            raw_unit_ref="IDR",
            raw_decimals="0",
            raw_lexical_value=str(int(v)),
        )
        for k, v, tag in fact_specs
    ]
    repo.save_canonical_facts(filing_id, canonical_models)

    # 3. Deterministic Metrics & Safeguards Evaluation
    contract_m = calculate_contract_exposure(
        trade_receivables_3rd=receivables_idr,
        trade_receivables_related=Decimal("0"),
        contract_assets_current=Decimal("0"),
        contract_assets_non_current=Decimal("0"),
        contract_liabilities_current=Decimal("0"),
        contract_liabilities_non_current=Decimal("0"),
        revenue_ttm=revenue_ttm_idr,
    )
    sloan_m = calculate_sloan_accrual(
        net_income_ttm=net_income_ttm_idr,
        cfo_ttm=cfo_ttm_idr,
        total_assets_current=total_assets_idr,
    )
    cov_m = calculate_cash_coverage(
        cash_and_equivalents=cash_idr,
        st_bank_loans=st_debt_bank_idr,
        current_maturities_bank_loans=Decimal("0"),
        current_maturities_bonds_sukuk_mtn=st_debt_bonds_idr,
        current_portion_lease=Decimal("0"),
    )
    safeguards = evaluate_safeguards(
        net_income_ttm=net_income_ttm_idr,
        cfo_ttm=cfo_ttm_idr,
        cfo_single_q=cfo_ttm_idr,
        sloan_ratio_ttm=sloan_m.sloan_ratio_ttm,
        st_debt=cov_m.st_debt_idr,
        debt_free_short_term=cov_m.debt_free_short_term,
        cash_coverage=cov_m.cash_coverage_ratio,
    )

    computed = ComputedFilingMetrics(
        filing_id=filing_id,
        ticker=clean_ticker,
        period_end_date=period_end,
        is_audit_derived_q4=False,
        contract_exposure=contract_m,
        sloan_accrual=sloan_m,
        cash_coverage=cov_m,
        safeguards=safeguards,
    )
    repo.save_computed_metrics(computed)

    if source_note and source_note.strip():
        save_custom_disclosure(clean_ticker, source_note.strip())

    return {
        "status": "success",
        "ticker": clean_ticker,
        "company_name": clean_name,
        "idx_sub_industry": clean_sector,
        "fiscal_year": fiscal_year,
        "filing_id": filing_id,
        "cash_coverage": (
            "Bebas Utang"
            if cov_m.debt_free_short_term
            else f"{float(cov_m.cash_coverage_ratio or 0):.2f}x"
        ),
        "sloan_ratio_pct": round(float(sloan_m.sloan_ratio_ttm or 0) * 100, 2),
        "safeguard_status": safeguards.status_summary,
    }


def ingest_xbrl_file_bytes(
    repo: FinancialRepository,
    ticker: str,
    company_name: str,
    idx_sub_industry: str,
    fiscal_year: int,
    filename: str,
    file_bytes: bytes,
) -> dict[str, Any]:
    """
    Parses an uploaded BEI XBRL (.xml or .zip) file with lxml XBRLReader +
    TaxonomyNormalizer, computes deterministic ratios, and persists to SQLite.
    """
    clean_ticker = validate_ticker(ticker)
    USER_XBRL_DIR.mkdir(parents=True, exist_ok=True)
    target_path = USER_XBRL_DIR / f"{clean_ticker}_{fiscal_year}_{Path(filename).name}"
    target_path.write_bytes(file_bytes)

    xml_path = target_path
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(target_path, "r") as zf:
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                raise ValueError("Berkas ZIP tidak mengandung file instance XBRL (.xml).")
            extracted = USER_XBRL_DIR / f"{clean_ticker}_{fiscal_year}_instance.xml"
            extracted.write_bytes(zf.read(xml_names[0]))
            xml_path = extracted

    raw_doc = read_xbrl_document(xml_path)
    normalizer = TaxonomyNormalizer()
    extraction = normalizer.normalize(raw_doc)
    facts_map = {f.canonical_key: f.value_idr for f in extraction.facts}

    cash_val = facts_map.get("cash_and_equivalents", Decimal("0"))
    st_bank = facts_map.get("st_debt_bank_loans", Decimal("0")) + facts_map.get(
        "st_debt_current_maturities_bank_loans", Decimal("0")
    )
    st_bonds = facts_map.get("st_debt_current_maturities_bonds_sukuk_mtn", Decimal("0"))
    cfo_val = facts_map.get("cfo", Decimal("0"))
    net_val = facts_map.get("net_income", Decimal("0"))
    rev_val = facts_map.get("revenue", Decimal("0"))
    assets_val = facts_map.get("total_assets", Decimal("0"))
    liab_val = facts_map.get("total_liabilities", Decimal("0"))
    rec_val = facts_map.get("trade_receivables_third_parties", Decimal("0")) + facts_map.get(
        "trade_receivables_related_parties", Decimal("0")
    )

    if assets_val <= Decimal("0"):
        raise ValueError(
            "Tag Total Aset tidak ditemukan atau bernilai 0 di dalam XBRL XML yang diunggah."
        )

    res = ingest_structured_issuer(
        repo=repo,
        ticker=clean_ticker,
        company_name=company_name,
        idx_sub_industry=idx_sub_industry,
        fiscal_year=fiscal_year,
        cash_idr=cash_val,
        st_debt_bank_idr=st_bank,
        st_debt_bonds_idr=st_bonds,
        cfo_ttm_idr=cfo_val,
        net_income_ttm_idr=net_val,
        revenue_ttm_idr=rev_val,
        total_assets_idr=assets_val,
        total_liabilities_idr=liab_val,
        receivables_idr=rec_val,
        source_note=f"Ingesti XBRL Primer BEI ({Path(filename).name})",
    )
    res["xbrl_hash"] = raw_doc.source_hash
    res["sanity_passed"] = extraction.filing.sanity_check_passed
    return res


# Hydrate custom disclosures at module load
load_custom_disclosures()
