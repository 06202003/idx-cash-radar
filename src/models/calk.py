"""
Pydantic schemas for CALK (Catatan Atas Laporan Keuangan) Footnote Extraction.
Strictly implements Section 5.2 of docs/PRD.md.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class RelatedPartyBreakdown(BaseModel):
    """Breakdown of third party vs related party exposure and impairment allowance."""

    gross_third_party_idr: Decimal
    gross_related_party_idr: Decimal
    gross_total_idr: Decimal
    related_party_share_pct: Decimal = Field(
        description="Persentase porsi pihak berelasi terhadap total bruto"
    )
    ckpn_impairment_allowance_idr: Decimal = Field(
        default=Decimal("0"),
        description="Cadangan Kerugian Penurunan Nilai (CKPN)"
    )
    net_total_idr: Decimal = Field(
        description="Nilai neto setelah dikurangi CKPN"
    )
    unit_multiplier: Decimal = Field(
        default=Decimal("1"),
        description="Pengali satuan dalam laporan (1, 1000, 1000000)"
    )


class GroundingAuditItem(BaseModel):
    """Audit verification item for a single numerical claim."""

    field_name: str
    claimed_value_idr: Decimal
    found_verbatim_token: str
    source_page: int | None = None
    is_matched: bool
    scale_applied: Decimal = Decimal("1")


class CALKFootnoteExtraction(BaseModel):
    """Extraction of Notes to Financial Statements for Receivables & Contract Assets."""

    ticker: str
    fiscal_year: int
    footnote_number: str  # e.g. "Catatan 7" atau "Catatan 8"
    footnote_title: str
    page_number: int | None = None
    source_filename: str = ""
    unit_reported: str = "IDR"  # "IDR", "Ribuan IDR", "Jutaan IDR"
    trade_receivables: RelatedPartyBreakdown | None = None
    contract_assets: RelatedPartyBreakdown | None = None
    is_grounding_verified: bool = False
    rejection_reason: str | None = None
    audit_trail: list[GroundingAuditItem] = Field(default_factory=list)
    raw_source_excerpt: str = ""
