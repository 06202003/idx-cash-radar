"""
CALK Footnote Extractor with Gemini AI and Deterministic Pattern Matching.
Strictly implements Section 5.2 of docs/PRD.md.
Coupled with Verbatim Grounding Verifier to prevent any LLM hallucinations.
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from typing import Any

from src.engine.llm_explainer import (
    DEFAULT_GEMINI_MODEL,
    check_language_compliance,
)
from src.engine.verbatim_grounding import (
    VerbatimGroundingVerifier,
    detect_unit_multiplier,
    normalize_indonesian_number_str,
)
from src.models.calk import (
    CALKFootnoteExtraction,
    RelatedPartyBreakdown,
)


def extract_breakdown_deterministic(
    text: str,
    context_type: str = "receivables",  # "receivables" | "contract_assets"
) -> RelatedPartyBreakdown | None:
    """
    Deterministic rule-based table extractor for standard Indonesian CALK tables.
    Parses line-by-line financial statement disclosures.
    """
    unit_multiplier, _ = detect_unit_multiplier(text)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    third_party_val: Decimal | None = None
    related_party_val: Decimal | None = None
    gross_total_val: Decimal | None = None
    ckpn_val: Decimal = Decimal("0")
    net_total_val: Decimal | None = None

    # Line regexes
    num_extract_pattern = re.compile(r"(\(?\s*[\d\.\,]+\s*\)?)")

    for line in lines:
        line_lower = line.lower()
        nums = num_extract_pattern.findall(line)
        if not nums:
            continue

        # Take the first or most recent column figure (usually column 1 or 2)
        # We parse the last valid number on the line as the current year figure
        parsed_nums = []
        for n in nums:
            p = normalize_indonesian_number_str(n)
            if p is not None:
                parsed_nums.append(p)
        if not parsed_nums:
            continue

        # In financial statements, the current year is typically the first or second column
        cand_num = parsed_nums[0]

        # 1. Pihak ketiga
        if "pihak ketiga" in line_lower and third_party_val is None:
            third_party_val = abs(cand_num) * unit_multiplier

        # 2. Pihak berelasi
        elif "pihak berelasi" in line_lower and related_party_val is None:
            related_party_val = abs(cand_num) * unit_multiplier

        # 3. CKPN / Penurunan nilai
        elif any(
            k in line_lower
            for k in ["cadangan kerugian", "penurunan nilai", "ckpn", "impairment"]
        ):
            ckpn_val = abs(cand_num) * unit_multiplier

        # 4. Total / Jumlah
        elif any(k in line_lower for k in ["total", "jumlah", "subtotal"]):
            if "neto" in line_lower or "bersih" in line_lower:
                if net_total_val is None:
                    net_total_val = abs(cand_num) * unit_multiplier
            elif gross_total_val is None:
                gross_total_val = abs(cand_num) * unit_multiplier

    if third_party_val is None and related_party_val is None:
        return None

    # Fill defaults if missing
    third_party_val = third_party_val or Decimal("0")
    related_party_val = related_party_val or Decimal("0")
    if gross_total_val is None:
        gross_total_val = third_party_val + related_party_val
    if net_total_val is None:
        net_total_val = gross_total_val - ckpn_val

    share_pct = (
        (related_party_val / gross_total_val * Decimal("100")).quantize(Decimal("0.01"))
        if gross_total_val > 0
        else Decimal("0")
    )

    return RelatedPartyBreakdown(
        gross_third_party_idr=third_party_val,
        gross_related_party_idr=related_party_val,
        gross_total_idr=gross_total_val,
        related_party_share_pct=share_pct,
        ckpn_impairment_allowance_idr=ckpn_val,
        net_total_idr=net_total_val,
        unit_multiplier=unit_multiplier,
    )


class CALKFootnoteExtractor:
    """
    Orchestrator for CALK Footnote extraction with LLM and Grounding Verification.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.verifier = VerbatimGroundingVerifier()
        self._client: Any = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    def extract_from_text(
        self,
        ticker: str,
        fiscal_year: int,
        source_text: str,
        footnote_number: str = "Catatan 7",
        footnote_title: str = "Piutang Usaha & Aset Kontrak",
        page_number: int | None = None,
        target_context: str = "receivables",  # "receivables" | "contract_assets"
    ) -> CALKFootnoteExtraction:
        """
        Extracts footnote breakdown, applies AI or deterministic pattern extraction,
        and enforces deterministic verbatim grounding verification.
        """
        multiplier, unit_label = detect_unit_multiplier(source_text)
        breakdown: RelatedPartyBreakdown | None = None

        # Try deterministic pattern extraction first (deterministic-first, zero-cost, instant)
        breakdown = extract_breakdown_deterministic(source_text, context_type=target_context)

        # Attempt LLM extraction if deterministic pattern could not parse table
        if breakdown is None and self._client and self.api_key:
            breakdown = self._extract_with_gemini(source_text, multiplier)

        # If both fail to parse numbers
        if breakdown is None:
            return CALKFootnoteExtraction(
                ticker=ticker,
                fiscal_year=fiscal_year,
                footnote_number=footnote_number,
                footnote_title=footnote_title,
                page_number=page_number,
                unit_reported=unit_label,
                is_grounding_verified=False,
                rejection_reason=(
                    "Tidak ditemukan baris rincian Pihak Ketiga / Pihak Berelasi pada teks catatan."
                ),
                raw_source_excerpt=source_text[:500],
            )

        # Run Deterministic Verbatim Grounding Verification
        is_verified, rejection_reason, audit_trail = self.verifier.verify_breakdown(
            breakdown=breakdown,
            source_text=source_text,
            page_number=page_number,
            context_name=f"{ticker} {footnote_title}",
        )

        receivables_res = breakdown if target_context == "receivables" else None
        contract_assets_res = breakdown if target_context == "contract_assets" else None

        return CALKFootnoteExtraction(
            ticker=ticker,
            fiscal_year=fiscal_year,
            footnote_number=footnote_number,
            footnote_title=footnote_title,
            page_number=page_number,
            unit_reported=unit_label,
            trade_receivables=receivables_res,
            contract_assets=contract_assets_res,
            is_grounding_verified=is_verified,
            rejection_reason=rejection_reason,
            audit_trail=audit_trail,
            raw_source_excerpt=source_text[:500],
        )

    def _extract_with_gemini(
        self,
        source_text: str,
        unit_multiplier: Decimal,
    ) -> RelatedPartyBreakdown | None:
        """Extracts JSON structure using Gemini API."""
        prompt = (
            "Ekstrak rincian pihak ketiga vs pihak berelasi dari catatan kaki dalam format JSON.\n"
            "DILARANG menghitung atau mengubah angka. Ambil angka eksak yang tertulis pada teks.\n"
            "Format JSON:\n"
            "{\n"
            '  "third_party": "<angka string>",\n'
            '  "related_party": "<angka string>",\n'
            '  "gross_total": "<angka string>",\n'
            '  "ckpn": "<angka string atau 0>",\n'
            '  "net_total": "<angka string>"\n'
            "}\n\n"
            f"TEKS CATATAN KAKI:\n{source_text}"
        )

        try:
            resp = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            raw_txt = resp.text.strip() if resp and resp.text else ""
            if not check_language_compliance(raw_txt):
                return None

            # Clean JSON markdown fences
            if "```" in raw_txt:
                raw_txt = re.sub(r"```(?:json)?", "", raw_txt).replace("```", "").strip()

            data = json.loads(raw_txt)

            tp_raw = str(data.get("third_party", "0"))
            rp_raw = str(data.get("related_party", "0"))
            gt_raw = str(data.get("gross_total", "0"))
            ck_raw = str(data.get("ckpn", "0"))
            nt_raw = str(data.get("net_total", "0"))

            tp = normalize_indonesian_number_str(tp_raw) or Decimal("0")
            rp = normalize_indonesian_number_str(rp_raw) or Decimal("0")
            gt = normalize_indonesian_number_str(gt_raw) or Decimal("0")
            ck = normalize_indonesian_number_str(ck_raw) or Decimal("0")
            nt = normalize_indonesian_number_str(nt_raw) or Decimal("0")

            tp_idr = abs(tp) * unit_multiplier
            rp_idr = abs(rp) * unit_multiplier
            gt_idr = abs(gt) * unit_multiplier
            ck_idr = abs(ck) * unit_multiplier
            nt_idr = abs(nt) * unit_multiplier

            share_pct = (
                (rp_idr / gt_idr * Decimal("100")).quantize(Decimal("0.01"))
                if gt_idr > 0
                else Decimal("0")
            )

            return RelatedPartyBreakdown(
                gross_third_party_idr=tp_idr,
                gross_related_party_idr=rp_idr,
                gross_total_idr=gt_idr,
                related_party_share_pct=share_pct,
                ckpn_impairment_allowance_idr=ck_idr,
                net_total_idr=nt_idr,
                unit_multiplier=unit_multiplier,
            )
        except Exception:
            return None
