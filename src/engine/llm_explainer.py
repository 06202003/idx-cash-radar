"""
AI Executive Narrative Explainer (Gemini Layer).
Gate 6 Implementation according to AGENTS.md v2.0 Section 6 & 8.
Translates deterministic quantitative accounting metrics into clear,
accessible Indonesian explanations for retail investors, with zero hallucination
and legal compliance guardrails.
"""

from __future__ import annotations

import os
import socket
import time
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

# Force IPv4 on Windows to prevent network semaphore hangs
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
    res = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in res if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else res


socket.getaddrinfo = _ipv4_getaddrinfo

from src.models.metrics import ComputedFilingMetrics  # noqa: E402
from src.renderer.formatter import format_decimal_id, format_idr_nominal  # noqa: E402

# Load environment variables (e.g. GEMINI_API_KEY)
load_dotenv()

# Blacklisted accusatory words mandated in AGENTS.md Section 7 & 10
BLACKLISTED_WORDS = [
    "manipulasi",
    "window dressing",
    "laporan palsu",
    "saham gorengan",
    "penipuan",
    "fraud",
    "bangkrut",
    "rekayasa laba",
    "rekomendasi beli",
    "rekomendasi jual",
]

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def check_language_compliance(text: str) -> bool:
    """Verifies that the generated narrative contains no blacklisted words."""
    lowered = text.lower()
    for word in BLACKLISTED_WORDS:
        if word in lowered:
            return False
    return True


def generate_deterministic_fallback_narrative(
    metrics: ComputedFilingMetrics,
    company_name: str,
    news_items: list[Any] | None = None,
) -> str:
    """
    Deterministic rule-based fallback narrative.
    Used when GEMINI_API_KEY is not configured, API quota is exhausted,
    network times out, or when AI text fails the legal compliance check.
    """
    safeguards = metrics.safeguards
    cfo_str = format_idr_nominal(metrics.sloan_accrual.cfo_ttm_idr)
    cash_str = format_idr_nominal(metrics.cash_coverage.cash_idr)
    coverage_val = metrics.cash_coverage.cash_coverage_ratio
    cov_str = f"{format_decimal_id(coverage_val, 2)}x" if coverage_val is not None else "N/A"

    news_note = ""
    if news_items:
        sentiments = [it.sentiment for it in news_items if hasattr(it, "sentiment")]
        if "PERHATIAN" in sentiments:
            news_note = (
                " Sentimen keterbukaan bursa terkait restrukturisasi atau penundaan kewajiban "
                "mengonfirmasi ketatnya bantalan kas saat ini."
            )
        elif "POSITIF" in sentiments:
            news_note = (
                " Sentimen positif perolehan kontrak baru menjadi katalis pertumbuhan yang "
                "perlu dibarengi disiplin penagihan termin proyek."
            )

    if safeguards.flag_acute_liquidity:
        return (
            f"Secara operasional, arus kas riil {metrics.ticker} sedang mengalami tekanan "
            f"dengan defisit kas operasi Rp {cfo_str} (kas keluar lebih besar dari masuk). "
            f"Ketersediaan kas bebas Rp {cash_str} tergolong sempit karena baru menutup {cov_str} "
            f"dari utang berbunga yang jatuh tempo <= 1 tahun, sehingga disiplin "
            f"penagihan termin proyek sangat krusial.{news_note}"
        )

    if safeguards.flag_accrual_divergence:
        gross_ratio_raw = metrics.contract_exposure.gross_contract_exposure_ratio
        if gross_ratio_raw is not None:
            gross_pct = f"{format_decimal_id(gross_ratio_raw * 100, 1)}%"
        else:
            gross_pct = "tinggi"
        return (
            f"{company_name} membukukan laba di atas kertas, namun uang kas aslinya belum masuk "
            f"ke rekening karena masih tertahan pada piutang dan tagihan aset kontrak "
            f"({gross_pct} dari pendapatan). Bagi pemegang saham, realisasi pencairan kas dari "
            f"pemberi kerja menjadi kunci kualitas laba yang sesungguhnya.{news_note}"
        )

    # Normal / Sehat
    debt_free = metrics.cash_coverage.debt_free_short_term
    debt_desc = (
        "tanpa beban utang bank berbunga jangka pendek"
        if debt_free
        else f"berada pada rasio {cov_str} terhadap utang jangka pendek"
    )
    return (
        f"Kondisi kas dan solvabilitas {metrics.ticker} terpantau sehat dan stabil dengan arus kas "
        f"operasi Rp {cfo_str} yang mampu menopang aktivitas usaha. Kapasitas kas bebas saat ini "
        f"{debt_desc}, mencerminkan bantalan likuiditas yang terkendali.{news_note}"
    )


def generate_deterministic_comparison_narrative(
    m1: ComputedFilingMetrics,
    name1: str,
    m2: ComputedFilingMetrics,
    name2: str,
) -> str:
    """Deterministic fallback for comparing two issuers."""
    cov1_free = m1.cash_coverage.debt_free_short_term
    cov2_free = m2.cash_coverage.debt_free_short_term
    cfo1 = m1.sloan_accrual.cfo_ttm_idr or Decimal("0")
    cfo2 = m2.sloan_accrual.cfo_ttm_idr or Decimal("0")

    cov1_str = (
        "bebas utang jangka pendek"
        if cov1_free
        else f"rasio kas {format_decimal_id(m1.cash_coverage.cash_coverage_ratio, 2)}x"
    )
    cov2_str = (
        "bebas utang jangka pendek"
        if cov2_free
        else f"rasio kas {format_decimal_id(m2.cash_coverage.cash_coverage_ratio, 2)}x"
    )

    cfo1_disp = format_idr_nominal(cfo1)
    cfo2_disp = format_idr_nominal(cfo2)

    stronger = (
        m1.ticker
        if (cov1_free and not cov2_free) or (cfo1 > cfo2 and not cov2_free)
        else m2.ticker
    )

    return (
        f"Komparasi Kas & Likuiditas: {m1.ticker} mencatatkan {cov1_str} dengan CFO TTM "
        f"Rp {cfo1_disp}, sedangkan {m2.ticker} mencatatkan {cov2_str} dengan CFO TTM "
        f"Rp {cfo2_disp}. Karakteristik neraca {stronger} memberikan bantalan kas yang relatif "
        f"lebih terlindungi dalam menghadapi jatuh tempo kewajiban jangka pendek."
    )


def generate_deterministic_trend_narrative(
    ticker: str,
    company_name: str,
    history: list[dict[str, Any]],
) -> str:
    """Deterministic fallback for historical 4-year trend evaluation."""
    if not history:
        return f"Data historis untuk {ticker} belum mencukupi untuk evaluasi tren multitahun."

    first_yr = history[0]
    latest_yr = history[-1]

    latest_cov = latest_yr.get("cash_coverage_ratio")
    first_cfo = first_yr.get("cfo_ttm_idr") or Decimal("0")
    latest_cfo = latest_yr.get("cfo_ttm_idr") or Decimal("0")

    fy_first = first_yr.get("fiscal_year")
    fy_latest = latest_yr.get("fiscal_year")

    if latest_yr.get("debt_free_short_term"):
        return (
            f"Sepanjang periode pengamatan {fy_first} hingga {fy_latest}, {ticker} konsisten "
            f"menjaga struktur modal yang kokoh tanpa beban utang jangka pendek berbunga, "
            f"memberikan stabilitas arus kas yang prima."
        )

    if latest_cfo > first_cfo and (latest_cov is not None and latest_cov >= Decimal("0.5")):
        return (
            f"Lintasan 4 tahun ({fy_first}–{fy_latest}) menunjukkan tren pemulihan arus kas "
            f"operasional pada {ticker}, di mana rasio kas menguat dan arus kas kembali menopang "
            f"perputaran modal kerja."
        )

    return (
        f"Evaluasi tren 4 tahun ({fy_first}–{fy_latest}) mengindikasikan bahwa {ticker} terus "
        f"mengelola perputaran modal kerja dan piutang proyek secara terukur agar likuiditas "
        f"kas tetap memadai dalam memenuhi liabilitas jangka pendek."
    )


class AIExecutiveExplainer:
    """AI Narrative Generator leveraging Google Gemini API with fallback guardrails."""

    _quota_exhausted_until: float = 0.0

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._client: Any = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                print(f"⚠️ Warning: Could not initialize Gemini Client: {exc}")
                self._client = None

    def explain(
        self,
        metrics: ComputedFilingMetrics,
        company_name: str,
        news_items: list[Any] | None = None,
    ) -> str:
        """
        Generates human-friendly executive narrative with plain-language statistical
        interpretation and news-financial data correlation.
        Falls back cleanly to deterministic narrative if API is unavailable.
        """
        # If no client or API key, or currently in quota exhaustion backoff, return fallback
        if (
            not self._client
            or not self.api_key
            or time.time() < AIExecutiveExplainer._quota_exhausted_until
        ):
            return generate_deterministic_fallback_narrative(metrics, company_name, news_items)

        # Assemble factual prompt context
        cfo_val = metrics.sloan_accrual.cfo_ttm_idr
        ni_val = metrics.sloan_accrual.net_income_ttm_idr
        cash_val = metrics.cash_coverage.cash_idr
        debt_val = metrics.cash_coverage.st_debt_idr
        cov_val = metrics.cash_coverage.cash_coverage_ratio
        gross_val = metrics.contract_exposure.gross_contract_exposure_ratio
        status_sum = metrics.safeguards.status_summary

        period_status = "Audited" if metrics.is_audit_derived_q4 else "Interim"
        cov_disp = f"{format_decimal_id(cov_val, 2)}x" if cov_val is not None else "N/A"
        gross_disp = (
            f"{format_decimal_id(gross_val * 100, 1)}%" if gross_val is not None else "N/A"
        )

        cohort_lines = []
        for cat_k, cr in metrics.cohort_ranks.items():
            if not cr.small_n_guard and cr.exact_rank and cr.total_peers:
                cohort_lines.append(
                    f"- {cat_k}: Peringkat {cr.exact_rank} dari {cr.total_peers} ({cr.quartile})"
                )
        cohort_summary = (
            "\n".join(cohort_lines) if cohort_lines else "Peringkat kohort: Belum mencukupi"
        )

        news_lines = []
        if news_items:
            for it in news_items:
                h = getattr(it, "headline", str(it))
                s = getattr(it, "sentiment", "NETRAL")
                d = getattr(it, "date", "")
                news_lines.append(f"• {d} [{s}]: {h}")
        news_summary = (
            "\n".join(news_lines) if news_lines else "Tidak ada pengumuman keterbukaan khusus."
        )

        prompt_data = f"""
Emiten: {company_name} ({metrics.ticker})
Periode: FY {metrics.period_end_date[:4]} ({period_status})
Status Kas: {status_sum}
Arus Kas Operasi (CFO TTM): Rp {format_idr_nominal(cfo_val)}
Laba Bersih TTM: Rp {format_idr_nominal(ni_val)}
Kas dan Setara Kas: Rp {format_idr_nominal(cash_val)}
Utang Berbunga Jangka Pendek: Rp {format_idr_nominal(debt_val)}
Rasio Penutupan Kas terhadap Utang JP: {cov_disp}
Rasio Eksposur Kontrak PSAK 72: {gross_disp} dari pendapatan

Posisi Dibandingkan 12 Emiten Peer Konstruksi:
{cohort_summary}

Sentimen Berita & Keterbukaan Informasi BEI Terkini:
{news_summary}
"""

        system_instruction = (
            "Anda adalah Konsultan Finansial & Penerjemah Laporan Keuangan Ramah untuk investor "
            "ritel awam di IDX Cash Radar.\n"
            "Tugas Anda:\n"
            "1. PENJELASAN RAMAH AWAM: Terjemahkan data metrik di atas ke bahasa Indonesia "
            "yang santai dan mudah dipahami pemula. Gunakan analogi bisnis sehari-hari "
            "(misal: uang tunai tertahan di proyek, kas operasional nombok, bantalan kas tipis "
            "untuk bayar utang bank segera).\n"
            "2. KORELASI BERITA: Korelasikan sentimen berita/keterbukaan bursa terkini dengan "
            "fakta uang kas riil secara logis.\n\n"
            "ATURAN MUTLAK (STRICT GUARDRAILS):\n"
            "1. DILARANG menghitung aritmatika atau mengubah nilai nominal angka.\n"
            "2. DILARANG memberikan rekomendasi beli/jual dan memprediksi harga saham.\n"
            "3. DILARANG menggunakan kata tuduhan: manipulasi, window dressing, laporan palsu, "
            "saham gorengan, penipuan, fraud, bangkrut, rekayasa laba.\n"
            "4. Maksimal 3 kalimat padat, mengalir alami, ramah pemula, dan langsung ke intinya."
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=f"{system_instruction}\n\nDATA METRIK & BERITA:\n{prompt_data}",
            )
            narrative = response.text.strip() if response and response.text else ""

            # Verify legal compliance on AI response
            if narrative and check_language_compliance(narrative):
                return narrative
            else:
                print("⚠️ AI output violated compliance. Falling back to deterministic narrative.")
                return generate_deterministic_fallback_narrative(metrics, company_name, news_items)

        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                AIExecutiveExplainer._quota_exhausted_until = time.time() + 1800
            print(f"⚠️ Gemini API call failed ({exc}). Using deterministic fallback narrative.")
            return generate_deterministic_fallback_narrative(metrics, company_name, news_items)

    def explain_comparison(
        self,
        m1: ComputedFilingMetrics,
        name1: str,
        m2: ComputedFilingMetrics,
        name2: str,
    ) -> str:
        """Generates AI comparative synthesis between two issuers with compliance guardrails."""
        if (
            not self._client
            or not self.api_key
            or time.time() < AIExecutiveExplainer._quota_exhausted_until
        ):
            return generate_deterministic_comparison_narrative(m1, name1, m2, name2)

        cov1_disp = (
            "Bebas Utang"
            if m1.cash_coverage.debt_free_short_term
            else f"{format_decimal_id(m1.cash_coverage.cash_coverage_ratio, 2)}x"
        )
        cov2_disp = (
            "Bebas Utang"
            if m2.cash_coverage.debt_free_short_term
            else f"{format_decimal_id(m2.cash_coverage.cash_coverage_ratio, 2)}x"
        )

        prompt_data = f"""
Emiten 1: {name1} ({m1.ticker})
- Kas & Setara Kas: Rp {format_idr_nominal(m1.cash_coverage.cash_idr)}
- Utang JP Berbunga: Rp {format_idr_nominal(m1.cash_coverage.st_debt_idr)}
- Rasio Kas: {cov1_disp}
- Arus Kas Operasi (CFO TTM): Rp {format_idr_nominal(m1.sloan_accrual.cfo_ttm_idr)}
- Status Safeguard: {m1.safeguards.status_summary}

Emiten 2: {name2} ({m2.ticker})
- Kas & Setara Kas: Rp {format_idr_nominal(m2.cash_coverage.cash_idr)}
- Utang JP Berbunga: Rp {format_idr_nominal(m2.cash_coverage.st_debt_idr)}
- Rasio Kas: {cov2_disp}
- Arus Kas Operasi (CFO TTM): Rp {format_idr_nominal(m2.sloan_accrual.cfo_ttm_idr)}
- Status Safeguard: {m2.safeguards.status_summary}
"""
        system_instruction = (
            "Anda adalah Senior Financial Analyst & Narrative Translator untuk IDX Cash Radar.\n"
            "Tugas: Bandingkan profil ketahanan kas, beban utang JP, dan arus kas kedua emiten "
            "dalam bahasa Indonesia yang santai dan mudah dipahami investor pemula.\n"
            "ATURAN WAJIB:\n"
            "1. DILARANG menghitung atau mengubah nilai angka.\n"
            "2. DILARANG memberikan rekomendasi beli/jual dan target harga saham.\n"
            "3. DILARANG menggunakan kata tuduhan tidak patuh hukum atau spekulasi negatif.\n"
            "4. Maksimal 2-3 kalimat padat, informatif, dan edukatif."
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=f"{system_instruction}\n\nDATA PERBANDINGAN:\n{prompt_data}",
            )
            narrative = response.text.strip() if response and response.text else ""
            if narrative and check_language_compliance(narrative):
                return narrative
            return generate_deterministic_comparison_narrative(m1, name1, m2, name2)
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                AIExecutiveExplainer._quota_exhausted_until = time.time() + 1800
            print(f"⚠️ Gemini comparison failed ({exc}). Using fallback.")
            return generate_deterministic_comparison_narrative(m1, name1, m2, name2)

    def explain_trend(
        self,
        ticker: str,
        company_name: str,
        history: list[dict[str, Any]],
    ) -> str:
        """Generates AI trend analysis across 4 fiscal years (2022-2025)."""
        if (
            not self._client
            or not self.api_key
            or time.time() < AIExecutiveExplainer._quota_exhausted_until
        ):
            return generate_deterministic_trend_narrative(ticker, company_name, history)

        hist_lines = []
        for h in history:
            yr = h.get("fiscal_year")
            cfo_str = format_idr_nominal(h.get("cfo_ttm_idr"))
            cov_val = h.get("cash_coverage_ratio")
            free = h.get("debt_free_short_term")
            if free:
                cov_str = "Bebas Utang"
            elif cov_val is not None:
                cov_str = f"{format_decimal_id(cov_val, 2)}x"
            else:
                cov_str = "N/A"
            badge = h.get("status_badge", "N/A")
            hist_lines.append(f"- FY {yr}: CFO Rp {cfo_str}, Rasio Kas {cov_str}, Status: {badge}")

        prompt_data = (
            f"Emiten: {company_name} ({ticker})\nRiwayat 4 Tahun:\n" + "\n".join(hist_lines)
        )

        system_instruction = (
            "Anda adalah Senior Financial Analyst & Narrative Translator untuk IDX Cash Radar.\n"
            "Tugas: Jelaskan perjalanan tren arus kas operasional (CFO) dan solvabilitas kas "
            "emiten selama 4 tahun terakhir dalam bahasa Indonesia yang santai, edukatif, "
            "dan mudah dipahami investor pemula.\n"
            "ATURAN WAJIB:\n"
            "1. DILARANG menghitung atau mengubah nilai angka.\n"
            "2. DILARANG memberikan saran investasi atau target harga saham.\n"
            "3. DILARANG menggunakan kata tuduhan tidak patuh hukum.\n"
            "4. Maksimal 2-3 kalimat padat, informatif, dan edukatif."
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=f"{system_instruction}\n\nDATA TREN:\n{prompt_data}",
            )
            narrative = response.text.strip() if response and response.text else ""
            if narrative and check_language_compliance(narrative):
                return narrative
            return generate_deterministic_trend_narrative(ticker, company_name, history)
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                AIExecutiveExplainer._quota_exhausted_until = time.time() + 1800
            print(f"⚠️ Gemini trend failed ({exc}). Using fallback.")
            return generate_deterministic_trend_narrative(ticker, company_name, history)
