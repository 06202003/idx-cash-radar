"""
Unit tests for Gate 6 AI Executive Narrative Explainer & Compliance Guards.
Tests deterministic fallback narratives, blacklisted words filtering,
and mocked Gemini API interactions.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from src.engine.llm_explainer import (
    AIExecutiveExplainer,
    check_language_compliance,
    generate_deterministic_fallback_narrative,
)
from src.models.metrics import (
    CashCoverageMetrics,
    ComputedFilingMetrics,
    ContractExposureMetrics,
    SafeguardEvaluation,
    SloanAccrualMetrics,
)


def create_sample_metrics(
    flag_acute_liquidity: bool = False,
    flag_accrual_divergence: bool = False,
) -> ComputedFilingMetrics:
    """Helper creating sample ComputedFilingMetrics."""
    return ComputedFilingMetrics(
        filing_id="WIKA_2023_FY",
        ticker="WIKA",
        period_end_date="2023-12-31",
        is_audit_derived_q4=True,
        contract_exposure=ContractExposureMetrics(
            gross_exposure_idr=Decimal("15000000000000"),
            net_exposure_idr=Decimal("12000000000000"),
            revenue_ttm_idr=Decimal("21400000000000"),
            gross_contract_exposure_ratio=Decimal("0.70"),
            net_contract_exposure_ratio=Decimal("0.56"),
            gross_divergence_yoy_bps=Decimal("520"),
        ),
        sloan_accrual=SloanAccrualMetrics(
            sloan_ratio_ttm=Decimal("0.085"),
            net_income_ttm_idr=Decimal("-7120000000000"),
            cfo_ttm_idr=Decimal("-2900000000000"),
            average_assets_idr=Decimal("65000000000000"),
        ),
        cash_coverage=CashCoverageMetrics(
            cash_idr=Decimal("3233071377000"),
            st_debt_idr=Decimal("20912063745000"),
            cash_coverage_ratio=Decimal("0.15"),
        ),
        safeguards=SafeguardEvaluation(
            flag_accrual_divergence=flag_accrual_divergence,
            flag_acute_liquidity=flag_acute_liquidity,
            status_summary=(
                "PERHATIAN: TEKANAN LIKUIDITAS AKUT" if flag_acute_liquidity else "NORMAL"
            ),
        ),
    )


def test_language_compliance_filter():
    # Clean text
    clean_text = "Arus kas operasi sedang tertekan karena pencairan piutang termin proyek tertahan."
    assert check_language_compliance(clean_text) is True

    # Violating texts with blacklisted words from AGENTS.md
    assert check_language_compliance("Terjadi manipulasi laporan keuangan.") is False
    assert check_language_compliance("Manajemen melakukan window dressing.") is False
    assert check_language_compliance("Ini adalah laporan palsu dan fraud.") is False
    assert check_language_compliance("Saham ini termasuk saham gorengan.") is False
    assert check_language_compliance("Rekomendasi beli saham ini sekarang.") is False
    assert check_language_compliance("Perusahaan terancam bangkrut.") is False


def test_deterministic_fallback_acute_liquidity():
    metrics = create_sample_metrics(flag_acute_liquidity=True)
    narrative = generate_deterministic_fallback_narrative(metrics, "PT Wijaya Karya (Persero) Tbk.")

    assert "WIKA" in narrative
    assert "defisit kas operasi" in narrative
    assert "utang berbunga" in narrative
    assert check_language_compliance(narrative) is True


def test_deterministic_fallback_accrual_divergence():
    metrics = create_sample_metrics(flag_accrual_divergence=True)
    narrative = generate_deterministic_fallback_narrative(metrics, "PT Wijaya Karya (Persero) Tbk.")

    assert "laba di atas kertas" in narrative
    assert "piutang dan tagihan aset kontrak" in narrative
    assert check_language_compliance(narrative) is True


def test_deterministic_fallback_normal():
    metrics = create_sample_metrics(flag_acute_liquidity=False, flag_accrual_divergence=False)
    narrative = generate_deterministic_fallback_narrative(metrics, "PT PP (Persero) Tbk.")

    assert "stabil" in narrative
    assert "likuiditas" in narrative
    assert check_language_compliance(narrative) is True


def test_ai_explainer_fallback_when_api_key_empty(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    explainer = AIExecutiveExplainer(api_key="")
    metrics = create_sample_metrics(flag_acute_liquidity=True)
    narrative = explainer.explain(metrics, "PT Wijaya Karya (Persero) Tbk.")

    assert narrative is not None
    assert len(narrative) > 20
    assert "WIKA" in narrative
    assert check_language_compliance(narrative) is True


def test_ai_explainer_mock_gemini_success():
    explainer = AIExecutiveExplainer(api_key="fake-test-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        "Kondisi kas WIKA saat ini sedang menguras dana operasi sebesar Rp 2,9T. "
        "Kas bebas yang tersedia baru menutup 15% dari utang jangka pendek yang jatuh tempo, "
        "sehingga emiten membutuhkan percepatan pencairan termin proyek."
    )
    mock_client.models.generate_content.return_value = mock_response
    explainer._client = mock_client

    metrics = create_sample_metrics(flag_acute_liquidity=True)
    narrative = explainer.explain(metrics, "PT Wijaya Karya (Persero) Tbk.")

    assert narrative == mock_response.text
    mock_client.models.generate_content.assert_called_once()


def test_ai_explainer_rejects_and_falls_back_when_ai_hallucinates_blacklisted_word():
    explainer = AIExecutiveExplainer(api_key="fake-test-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    # Mock AI generating an impermissible blacklisted word
    mock_response.text = "Perusahaan melakukan manipulasi laba dan saham ini terancam bangkrut."
    mock_client.models.generate_content.return_value = mock_response
    explainer._client = mock_client

    metrics = create_sample_metrics(flag_acute_liquidity=True)
    narrative = explainer.explain(metrics, "PT Wijaya Karya (Persero) Tbk.")

    # Must reject the AI response and fallback to clean deterministic narrative
    assert "manipulasi" not in narrative
    assert "bangkrut" not in narrative
    assert check_language_compliance(narrative) is True
    assert "defisit kas operasi" in narrative
