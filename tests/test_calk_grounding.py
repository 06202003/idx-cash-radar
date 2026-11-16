"""
Unit tests for CALK Footnote Extractor and Deterministic Verbatim Grounding Verifier.
Strictly verifies Section 5.2 and Section 7 of docs/PRD.md and AGENTS.md.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.bot.main import format_calk_response, handle_calk
from src.db.repository import FinancialRepository
from src.engine.calk_extractor import (
    CALKFootnoteExtractor,
    extract_breakdown_deterministic,
)
from src.engine.llm_explainer import check_language_compliance
from src.engine.verbatim_grounding import (
    VerbatimGroundingVerifier,
    detect_unit_multiplier,
    extract_all_numerical_tokens,
    normalize_indonesian_number_str,
)
from src.models.calk import RelatedPartyBreakdown
from src.renderer.card_renderer import DiagnosticCardRenderer


def test_normalize_indonesian_number_str() -> None:
    # Standard thousands dots
    assert normalize_indonesian_number_str("1.234.567") == Decimal("1234567")
    assert normalize_indonesian_number_str("3.841.520") == Decimal("3841520")

    # Indonesian comma decimals
    assert normalize_indonesian_number_str("1.234,56") == Decimal("1234.56")
    assert normalize_indonesian_number_str("12,34") == Decimal("12.34")

    # Parentheses negatives
    assert normalize_indonesian_number_str("(1.150.000)") == Decimal("-1150000")
    assert normalize_indonesian_number_str("( 25.000 )") == Decimal("-25000")

    # Standard minus negatives
    assert normalize_indonesian_number_str("-500.000") == Decimal("-500000")

    # Zero or dash
    assert normalize_indonesian_number_str("-") == Decimal("0")
    assert normalize_indonesian_number_str("—") == Decimal("0")
    assert normalize_indonesian_number_str("") == Decimal("0")


def test_extract_all_numerical_tokens() -> None:
    sample_text = """
    Pihak ketiga: 3.841.520
    Pihak berelasi: 2.348.910
    Cadangan penurunan nilai: (1.150.000)
    Jumlah neto: 5.040.430
    """
    tokens = extract_all_numerical_tokens(sample_text)
    token_values = [val for _, val in tokens]

    assert Decimal("3841520") in token_values
    assert Decimal("2348910") in token_values
    assert Decimal("-1150000") in token_values
    assert Decimal("5040430") in token_values


def test_detect_unit_multiplier() -> None:
    assert detect_unit_multiplier("Laporan disajikan dalam jutaan rupiah")[0] == Decimal("1000000")
    assert detect_unit_multiplier("Disajikan dalam ribuan rupiah")[0] == Decimal("1000")
    assert detect_unit_multiplier("Disajikan dalam miliar rupiah")[0] == Decimal("1000000000")
    assert detect_unit_multiplier("Disajikan dalam rupiah penuh")[0] == Decimal("1")


def test_verbatim_grounding_success_exact_match() -> None:
    verifier = VerbatimGroundingVerifier()
    source_text = """
    Catatan 8. PIUTANG USAHA (dalam jutaan rupiah)
    Pihak ketiga: 3.841.520
    Pihak berelasi: 2.348.910
    Jumlah bruto: 6.190.430
    Cadangan kerugian penurunan nilai: (1.150.000)
    Jumlah neto: 5.040.430
    """

    breakdown = RelatedPartyBreakdown(
        gross_third_party_idr=Decimal("3841520") * Decimal("1000000"),
        gross_related_party_idr=Decimal("2348910") * Decimal("1000000"),
        gross_total_idr=Decimal("6190430") * Decimal("1000000"),
        related_party_share_pct=Decimal("37.94"),
        ckpn_impairment_allowance_idr=Decimal("1150000") * Decimal("1000000"),
        net_total_idr=Decimal("5040430") * Decimal("1000000"),
        unit_multiplier=Decimal("1000000"),
    )

    is_verified, rejection_reason, audit_trail = verifier.verify_breakdown(
        breakdown=breakdown,
        source_text=source_text,
        page_number=45,
    )

    assert is_verified is True
    assert rejection_reason is None
    assert len(audit_trail) == 5
    assert all(item.is_matched for item in audit_trail)


def test_verbatim_grounding_rejects_hallucinated_number() -> None:
    verifier = VerbatimGroundingVerifier()
    source_text = """
    Catatan 8. PIUTANG USAHA (dalam jutaan rupiah)
    Pihak ketiga: 3.841.520
    Pihak berelasi: 2.348.910
    Jumlah bruto: 6.190.430
    Cadangan kerugian penurunan nilai: (1.150.000)
    Jumlah neto: 5.040.430
    """

    # Claim a third party figure that was hallucinated by LLM and doesn't exist in text
    breakdown = RelatedPartyBreakdown(
        gross_third_party_idr=Decimal("9999999") * Decimal("1000000"),
        gross_related_party_idr=Decimal("2348910") * Decimal("1000000"),
        gross_total_idr=Decimal("12348909") * Decimal("1000000"),
        related_party_share_pct=Decimal("19.02"),
        ckpn_impairment_allowance_idr=Decimal("1150000") * Decimal("1000000"),
        net_total_idr=Decimal("11198909") * Decimal("1000000"),
        unit_multiplier=Decimal("1000000"),
    )

    is_verified, rejection_reason, audit_trail = verifier.verify_breakdown(
        breakdown=breakdown,
        source_text=source_text,
        page_number=45,
    )

    assert is_verified is False
    assert rejection_reason is not None
    assert "Verbatim Grounding GAGAL" in rejection_reason
    assert "gross_third_party_idr" in rejection_reason


def test_verbatim_grounding_rejects_accounting_imbalance() -> None:
    verifier = VerbatimGroundingVerifier()
    source_text = """
    Pihak ketiga: 100
    Pihak berelasi: 50
    Jumlah bruto: 200
    Cadangan kerugian penurunan nilai: 0
    Jumlah neto: 200
    """

    # 100 + 50 != 200 (accounting violation)
    breakdown = RelatedPartyBreakdown(
        gross_third_party_idr=Decimal("100"),
        gross_related_party_idr=Decimal("50"),
        gross_total_idr=Decimal("200"),
        related_party_share_pct=Decimal("25"),
        ckpn_impairment_allowance_idr=Decimal("0"),
        net_total_idr=Decimal("200"),
        unit_multiplier=Decimal("1"),
    )

    is_verified, rejection_reason, audit_trail = verifier.verify_breakdown(
        breakdown=breakdown,
        source_text=source_text,
    )

    assert is_verified is False
    assert "Rekonsiliasi Akuntansi GAGAL" in rejection_reason


def test_deterministic_extractor_wika_sample() -> None:
    source_text = """
    (Disajikan dalam Jutaan Rupiah, kecuali dinyatakan lain)
    Catatan 8. PIUTANG USAHA
    Pihak ketiga                             3.841.520
    Pihak berelasi                           2.348.910
    Jumlah bruto                             6.190.430
    Cadangan kerugian penurunan nilai (CKPN) (1.150.000)
    Jumlah neto                              5.040.430
    """
    breakdown = extract_breakdown_deterministic(source_text)
    assert breakdown is not None
    assert breakdown.gross_third_party_idr == Decimal("3841520000000")
    assert breakdown.gross_related_party_idr == Decimal("2348910000000")
    assert breakdown.gross_total_idr == Decimal("6190430000000")
    assert breakdown.ckpn_impairment_allowance_idr == Decimal("1150000000000")
    assert breakdown.net_total_idr == Decimal("5040430000000")
    assert breakdown.related_party_share_pct == Decimal("37.94")


def test_calk_footnote_extractor_end_to_end() -> None:
    extractor = CALKFootnoteExtractor(api_key=None)
    source_text = """
    (Disajikan dalam Jutaan Rupiah, kecuali dinyatakan lain)
    Catatan 8. PIUTANG USAHA
    Pihak ketiga                             3.841.520
    Pihak berelasi                           2.348.910
    Jumlah bruto                             6.190.430
    Cadangan kerugian penurunan nilai (CKPN) (1.150.000)
    Jumlah neto                              5.040.430
    """
    res = extractor.extract_from_text(
        ticker="WIKA",
        fiscal_year=2023,
        source_text=source_text,
        footnote_number="Catatan 8",
        footnote_title="Piutang Usaha",
        page_number=45,
    )

    assert res.is_grounding_verified is True
    assert res.trade_receivables is not None
    assert res.trade_receivables.related_party_share_pct == Decimal("37.94")
    assert len(res.audit_trail) == 5


def test_calk_card_renderer() -> None:
    extractor = CALKFootnoteExtractor(api_key=None)
    source_text = """
    (Disajikan dalam Jutaan Rupiah, kecuali dinyatakan lain)
    Catatan 8. PIUTANG USAHA
    Pihak ketiga                             3.841.520
    Pihak berelasi                           2.348.910
    Jumlah bruto                             6.190.430
    Cadangan kerugian penurunan nilai (CKPN) (1.150.000)
    Jumlah neto                              5.040.430
    """
    res = extractor.extract_from_text(
        ticker="WIKA",
        fiscal_year=2023,
        source_text=source_text,
        footnote_number="Catatan 8",
        footnote_title="Piutang Usaha",
        page_number=45,
    )

    renderer = DiagnosticCardRenderer()
    card_text = renderer.render_calk_card(res)

    assert "DETAIL CATATAN KAKI (CALK): WIKA" in card_text
    assert "Pihak Berelasi" in card_text
    assert "Cadangan CKPN" in card_text
    assert "LOLOS VERBATIM (100% AKURAT)" in card_text
    assert check_language_compliance(card_text) is True


def test_format_calk_response_and_bot_handler() -> None:
    repo = FinancialRepository()
    resp = format_calk_response("WIKA", repo)

    assert "DETAIL CATATAN KAKI (CALK): WIKA" in resp
    assert "Pihak Berelasi" in resp
    assert check_language_compliance(resp) is True

    # Test bot message handler
    message = MagicMock()
    message.text = "/calk WIKA"
    message.answer = AsyncMock()
    message.bot = None

    asyncio.run(handle_calk(message))
    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "DETAIL CATATAN KAKI (CALK): WIKA" in args[0]
    assert kwargs.get("reply_markup") is not None
