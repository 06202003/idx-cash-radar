"""
Unit tests for Contextual News & Disclosure Sentiment Radar (Gate 7).
Strictly verifies Section 6.2 and Section 7 of AGENTS.md.
"""

from __future__ import annotations

from decimal import Decimal

from src.db.repository import FinancialRepository
from src.engine.news_radar import (
    NewsRadar,
    NewsSentimentItem,
    classify_news_sentiment,
    sanitize_headline,
)
from src.models.metrics import (
    CashCoverageMetrics,
    ComputedFilingMetrics,
    ContractExposureMetrics,
    SafeguardEvaluation,
    SloanAccrualMetrics,
)
from src.renderer.card_renderer import DiagnosticCardRenderer


def test_sentiment_classification_keywords() -> None:
    """Verifies that keywords are classified deterministically without LLM."""
    # PERHATIAN keywords
    assert classify_news_sentiment("Penundaan Pembayaran Pokok Sukuk") == "PERHATIAN"
    assert classify_news_sentiment("Emiten Terancam Gugatan PKPU di PN Jakarta") == "PERHATIAN"
    assert (
        classify_news_sentiment("Pengumuman Suspensi Perdagangan Saham oleh Bursa")
        == "PERHATIAN"
    )
    assert classify_news_sentiment("Restrukturisasi Utang Bank Mencapai Kesepakatan") == "PERHATIAN"

    # POSITIF keywords
    assert (
        classify_news_sentiment("Raihan Kontrak Baru Proyek Tol Senilai Rp 2 Triliun")
        == "POSITIF"
    )
    assert classify_news_sentiment("Emiten Bagikan Dividen Tunai Tahun Buku 2023") == "POSITIF"
    assert classify_news_sentiment("Pelunasan Obligasi Berkelanjutan Tahap I") == "POSITIF"

    # NETRAL keywords
    assert classify_news_sentiment("Penyampaian Laporan Hasil Public Expose Tahunan") == "NETRAL"
    assert classify_news_sentiment("Rapat Umum Pemegang Saham Luar Biasa (RUPSLB)") == "NETRAL"
    assert (
        classify_news_sentiment("Keterbukaan Informasi Terkait Perubahan Alamat Kantor")
        == "NETRAL"
    )


def test_language_compliance_on_headlines() -> None:
    """Verifies that headlines with blacklisted words are rejected or sanitized."""
    # Defamatory/blacklisted words from Section 7
    bad_headline_1 = "Dugaan Manipulasi Laporan Keuangan Emiten"
    bad_headline_2 = "Indikasi Fraud dan Rekayasa Laba Proyek"
    bad_headline_3 = "Rekomendasi Beli Saham Konstruksi Target Rp 1000"

    assert sanitize_headline(bad_headline_1) is None
    assert sanitize_headline(bad_headline_2) is None
    assert sanitize_headline(bad_headline_3) is None

    # Valid factual headline passes
    good_headline = "Keterbukaan Informasi Mengenai Penundaan Pembayaran Kupon Bunga"
    assert sanitize_headline(good_headline) == good_headline


def test_rss_xml_parser() -> None:
    """Verifies that standard RSS XML is properly extracted into NewsSentimentItem."""
    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Berita Keterbukaan Informasi</title>
        <item>
          <title>Perolehan Kontrak Baru Bendungan Senilai Rp 1,5 T</title>
          <pubDate>Mon, 18 Dec 2023 10:00:00 +0700</pubDate>
          <link>https://example.com/news/1</link>
          <source>Keterbukaan BEI</source>
        </item>
        <item>
          <title>Penundaan Pembayaran Bunga Sukuk Jatuh Tempo</title>
          <pubDate>Thu, 28 Dec 2023 15:30:00 +0700</pubDate>
          <link>https://example.com/news/2</link>
          <source>Keterbukaan BEI</source>
        </item>
      </channel>
    </rss>
    """
    radar = NewsRadar()
    items = radar.parse_rss_feed(sample_rss)

    assert len(items) == 2
    assert items[0].sentiment == "POSITIF"
    assert items[0].date == "18 Dec 2023"
    assert items[0].source == "Keterbukaan BEI"

    assert items[1].sentiment == "PERHATIAN"
    assert items[1].date == "28 Dec 2023"


def test_contextual_isolation_safeguards_immunity() -> None:
    """
    CRITICAL TEST (AGENTS.md Section 6.2 Rule 3):
    Positive news (e.g. winning Rp 5 Trillion contracts) MUST NEVER
    override, disable, or dilute FLAG_ACUTE_LIQUIDITY.
    """
    radar = NewsRadar()

    # Distressed issuer state (like WIKA in 2023)
    distressed_safeguards = SafeguardEvaluation(
        flag_accrual_divergence=False,
        flag_acute_liquidity=True,
        status_summary="PERHATIAN: TEKANAN LIKUIDITAS AKUT",
    )

    # Overwhelmingly positive news
    super_positive_news = [
        NewsSentimentItem(
            date="28 Des 2023",
            sentiment="POSITIF",
            headline="Raihan Kontrak Baru Super Megah Senilai Rp 10 Triliun",
            source="Keterbukaan BEI",
        ),
        NewsSentimentItem(
            date="29 Des 2023",
            sentiment="POSITIF",
            headline="Perolehan Dividen Anak Usaha Bertumbuh Signifikan",
            source="Keterbukaan BEI",
        ),
    ]

    # Verify isolation
    assert radar.verify_contextual_isolation(distressed_safeguards, super_positive_news) is True
    # The flag MUST still be True!
    assert distressed_safeguards.flag_acute_liquidity is True
    assert distressed_safeguards.status_summary == "PERHATIAN: TEKANAN LIKUIDITAS AKUT"


def test_card_renderer_with_news_section() -> None:
    """Verifies that the news block renders properly in Jinja2 when news is present."""
    renderer = DiagnosticCardRenderer()

    metrics = ComputedFilingMetrics(
        filing_id="WIKA_2023_FY",
        ticker="WIKA",
        period_end_date="2023-12-31",
        is_audit_derived_q4=True,
        contract_exposure=ContractExposureMetrics(
            gross_exposure_idr=Decimal("1000000000"),
            net_exposure_idr=Decimal("800000000"),
            revenue_ttm_idr=Decimal("2000000000"),
            gross_contract_exposure_ratio=Decimal("0.50"),
            net_contract_exposure_ratio=Decimal("0.40"),
        ),
        sloan_accrual=SloanAccrualMetrics(
            net_income_ttm_idr=Decimal("-7000000000"),
            cfo_ttm_idr=Decimal("-2000000000"),
            average_assets_idr=Decimal("50000000000"),
            sloan_ratio_ttm=Decimal("-0.10"),
        ),
        cash_coverage=CashCoverageMetrics(
            cash_idr=Decimal("3000000000"),
            st_debt_idr=Decimal("20000000000"),
            cash_coverage_ratio=Decimal("0.15"),
        ),
        safeguards=SafeguardEvaluation(
            flag_acute_liquidity=True,
            status_summary="PERHATIAN: TEKANAN LIKUIDITAS AKUT",
        ),
    )

    news_items = [
        NewsSentimentItem(
            date="28 Des 2023",
            sentiment="PERHATIAN",
            headline="Pengumuman Penundaan Pembayaran Kupon Sukuk",
        ),
        NewsSentimentItem(
            date="15 Des 2023",
            sentiment="NETRAL",
            headline="Laporan Hasil Public Expose Tahunan 2023",
        ),
    ]

    card_text = renderer.render_construction_card(
        metrics=metrics,
        company_name="PT Wijaya Karya (Persero) Tbk",
        news_items=news_items,
    )

    # Check presence of the dedicated section
    assert "📰 SENTIMEN BERITA & KETERBUKAAN BEI" in card_text
    assert "28 Des 2023 [PERHATIAN]: Pengumuman Penundaan Pembayaran Kupon Sukuk" in card_text
    assert "15 Des 2023 [NETRAL]: Laporan Hasil Public Expose Tahunan 2023" in card_text


def test_bot_format_includes_news_radar() -> None:
    """Verifies that format_bot_response_for_ticker integrates news radar."""
    from src.bot.main import format_bot_response_for_ticker

    repo = FinancialRepository()
    card_wika = format_bot_response_for_ticker("WIKA", repo)

    assert "📰 SENTIMEN BERITA & KETERBUKAAN BEI" in card_wika
    assert "PERHATIAN" in card_wika
    assert "Penundaan Pembayaran Pokok Sukuk" in card_wika
