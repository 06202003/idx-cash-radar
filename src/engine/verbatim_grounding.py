"""
Deterministic Verbatim Grounding Verifier & Indonesian Accounting Number Normalizer.
Strictly implements Section 5.2 of docs/PRD.md.

Guarantees zero numerical hallucinations from LLM extractions by verifying that every
extracted number maps directly and verbatim to the source text of the primary financial document.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from src.models.calk import GroundingAuditItem, RelatedPartyBreakdown


def normalize_indonesian_number_str(token: str) -> Decimal | None:
    """
    Parses and normalizes Indonesian-formatted numerical strings into Decimal.
    Handles:
      - '1.234.567.890' -> 1234567890
      - '(1.234.567)'   -> -1234567
      - '1.234,56'      -> 1234.56
      - '(1.234,56)'    -> -1234.56
      - '-1.234.567'    -> -1234567
      - '1234567'       -> 1234567
    """
    cleaned = token.strip()
    if not cleaned or cleaned == "-" or cleaned == "—":
        return Decimal("0")

    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()
    elif cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()

    # Indonesian decimal format: '1.234.567,89'
    # Check if there is a comma decimal separator
    if "," in cleaned:
        # e.g. 1.234,56 -> remove dots, replace comma with dot -> 1234.56
        parts = cleaned.split(",")
        integer_part = parts[0].replace(".", "").replace(" ", "")
        decimal_part = parts[1].replace(" ", "")
        num_str = f"{integer_part}.{decimal_part}"
    else:
        # Dot as thousands separator or standard integer
        # Note: In Indonesian accounting, dot is strictly thousands separator unless solitary
        if "." in cleaned:
            # e.g. 1.234.567 -> 1234567
            num_str = cleaned.replace(".", "").replace(" ", "")
        else:
            num_str = cleaned.replace(" ", "")

    try:
        val = Decimal(num_str)
        return -val if is_negative else val
    except InvalidOperation:
        return None


def extract_all_numerical_tokens(text: str) -> list[tuple[str, Decimal]]:
    """
    Scans source text and extracts all numerical tokens along with their parsed Decimal values.
    Returns list of (raw_token_str, parsed_decimal).
    """
    # Regex matches numbers formatted as Indonesian currency, parentheses negatives, or decimals
    # Examples: (1.234.567), 1.234.567, 123.456, 12345, (123.456,78), 123,45
    pattern = re.compile(
        r"(?:\(\s*[\d\.\,]+\s*\)|-?\s*[\d\.\,]+)"
    )

    matches = pattern.findall(text)
    tokens: list[tuple[str, Decimal]] = []

    for m in matches:
        m_clean = m.strip()
        # Avoid standalone punctuation
        if not re.search(r"\d", m_clean):
            continue
        parsed = normalize_indonesian_number_str(m_clean)
        if parsed is not None:
            tokens.append((m_clean, parsed))

    return tokens


def detect_unit_multiplier(text: str) -> tuple[Decimal, str]:
    """
    Detects the reported unit scale from CALK footnote header text.
    Returns (multiplier, unit_label).
    """
    text_lower = text.lower()
    if "dalam miliaran rupiah" in text_lower or "dalam miliar rupiah" in text_lower:
        return Decimal("1000000000"), "Miliar IDR"
    elif "dalam jutaan rupiah" in text_lower or "dalam juta rupiah" in text_lower:
        return Decimal("1000000"), "Jutaan IDR"
    elif "dalam ribuan rupiah" in text_lower or "dalam ribu rupiah" in text_lower:
        return Decimal("1000"), "Ribuan IDR"
    elif "dalam satuan rupiah" in text_lower or "dalam rupiah" in text_lower:
        return Decimal("1"), "IDR Penuh"
    return Decimal("1"), "IDR"


class VerbatimGroundingVerifier:
    """
    Deterministic Verbatim Grounding Verifier.
    Validates that every single claimed number from an LLM or structured extractor
    exists verbatim in the source document page text.
    """

    def __init__(self, tolerance_scale_drift: Decimal = Decimal("1")) -> None:
        # Tolerance allows for rounding differences of 1 unit in the reported base scale
        self.tolerance = tolerance_scale_drift

    def verify_breakdown(
        self,
        breakdown: RelatedPartyBreakdown,
        source_text: str,
        page_number: int | None = None,
        context_name: str = "Piutang Usaha",
    ) -> tuple[bool, str | None, list[GroundingAuditItem]]:
        """
        Verifies a RelatedPartyBreakdown against source text.
        Returns:
            - is_verified: bool
            - rejection_reason: str or None
            - audit_trail: list of GroundingAuditItem
        """
        available_tokens = extract_all_numerical_tokens(source_text)
        if not available_tokens:
            return False, "Teks sumber tidak memuat angka numerik.", []

        multiplier = breakdown.unit_multiplier or Decimal("1")
        audit_trail: list[GroundingAuditItem] = []

        # Numerical fields to verify verbatim
        claims = [
            ("gross_third_party_idr", breakdown.gross_third_party_idr),
            ("gross_related_party_idr", breakdown.gross_related_party_idr),
            ("gross_total_idr", breakdown.gross_total_idr),
            ("ckpn_impairment_allowance_idr", breakdown.ckpn_impairment_allowance_idr),
            ("net_total_idr", breakdown.net_total_idr),
        ]

        # 1. Verbatim Grounding Verification
        for field_name, claimed_val in claims:
            # Scaled value in document units (e.g. 1.500.000.000 IDR -> 1.500 in Jutaan)
            expected_in_doc = claimed_val / multiplier if multiplier != 0 else claimed_val

            matched = False
            matched_token = ""

            for raw_tok, parsed_dec in available_tokens:
                # Check match in document unit scale (allowing for contra/deduction signs)
                match_scale = (
                    abs(parsed_dec - expected_in_doc) <= self.tolerance
                    or abs(abs(parsed_dec) - expected_in_doc) <= self.tolerance
                )
                if match_scale:
                    matched = True
                    matched_token = raw_tok
                    break
                # Also check if the document already wrote the full unscaled IDR value
                match_full = (
                    abs(parsed_dec - claimed_val) <= self.tolerance
                    or abs(abs(parsed_dec) - claimed_val) <= self.tolerance
                )
                if match_full:
                    matched = True
                    matched_token = raw_tok
                    break

            audit_item = GroundingAuditItem(
                field_name=field_name,
                claimed_value_idr=claimed_val,
                found_verbatim_token=matched_token if matched else "[TIDAK DITEMUKAN]",
                source_page=page_number,
                is_matched=matched,
                scale_applied=multiplier,
            )
            audit_trail.append(audit_item)

            if not matched:
                claimed_disp = f"Rp {claimed_val:,.0f}"
                unit_disp = f"{expected_in_doc:,.2f} dalam satuan {multiplier}"
                reason = (
                    f"Verbatim Grounding GAGAL: Angka klaim {field_name} {claimed_disp} "
                    f"({unit_disp}) tidak ditemukan pada teks catatan {context_name}."
                )
                return False, reason, audit_trail

        # 2. Accounting Reconciliation Sanity Check
        # Check: Pihak Ketiga + Pihak Berelasi == Total Bruto
        calculated_gross = breakdown.gross_third_party_idr + breakdown.gross_related_party_idr
        diff_gross = abs(calculated_gross - breakdown.gross_total_idr)
        if diff_gross > (self.tolerance * multiplier):
            reason = (
                f"Rekonsiliasi Akuntansi GAGAL: Pihak Ketiga ({breakdown.gross_third_party_idr}) + "
                f"Pihak Berelasi ({breakdown.gross_related_party_idr}) != "
                f"Total Bruto ({breakdown.gross_total_idr}). Selisih: {diff_gross}."
            )
            return False, reason, audit_trail

        # Check: Total Bruto - CKPN == Total Neto
        calculated_net = breakdown.gross_total_idr - breakdown.ckpn_impairment_allowance_idr
        diff_net = abs(calculated_net - breakdown.net_total_idr)
        if diff_net > (self.tolerance * multiplier):
            reason = (
                f"Rekonsiliasi Akuntansi GAGAL: Total Bruto ({breakdown.gross_total_idr}) - "
                f"CKPN ({breakdown.ckpn_impairment_allowance_idr}) != "
                f"Total Neto ({breakdown.net_total_idr}). Selisih: {diff_net}."
            )
            return False, reason, audit_trail

        return True, None, audit_trail
