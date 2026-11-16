"""
Canonical Pydantic models for IDX financial filings and facts.
Strict type validation and schema contract enforcement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class IssuerModel(BaseModel):
    ticker: str
    company_name: str
    idx_sub_industry: str = "Konstruksi Bangunan & Rekayasa Sipil"
    listing_status: Literal["ACTIVE", "SUSPENDED", "DELISTED"] = "ACTIVE"
    delisted_date: str | None = None


class FilingModel(BaseModel):
    filing_id: str  # Format: TICKER_YYYY_PERIOD_[FIRST|RESTATED]
    ticker: str
    fiscal_year: int
    period_code: Literal["Q1", "Q2", "Q3", "FY"]
    period_end_date: str  # YYYY-MM-DD
    filing_date: str | None = None
    is_audited: bool = False
    is_restatement: bool = False
    reporting_currency: str = "IDR"
    fx_rate_to_idr: Decimal = Decimal("1")
    sanity_check_passed: bool = False
    source_xbrl_hash: str


class CanonicalFactModel(BaseModel):
    canonical_key: str
    value_idr: Decimal
    raw_xbrl_tag: str
    raw_context_ref: str
    raw_unit_ref: str | None = None
    raw_decimals: str | None = None
    raw_lexical_value: str


class FilingExtractionResult(BaseModel):
    filing: FilingModel
    facts: list[CanonicalFactModel] = Field(default_factory=list)
    sanity_passed: bool = False
    sanity_details: list[dict[str, str | bool]] = Field(default_factory=list)


class DecumulatedQuarter(BaseModel):
    ticker: str
    fiscal_year: int
    period_code: Literal["Q1", "Q2", "Q3", "Q4"]
    period_end_date: str
    cfo_standalone_idr: Decimal | None = None
    revenue_standalone_idr: Decimal | None = None
    net_income_standalone_idr: Decimal | None = None
    is_audit_derived_q4: bool = False

