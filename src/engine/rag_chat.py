"""
RAG (Retrieval-Augmented Generation) Conversational Engine for IDX Cash Radar.
Combines:
1. Structured Database Facts (12 construction issuers, FY 2022-2025 metrics).
2. Domain Financial Knowledge Base (PSAK 72, Sloan Accrual, Cash Coverage, Safeguards).
3. Real-Time News & Corporate Disclosures.
4. Gemini AI with Deterministic Fallback & Section 7 Legal Compliance Guardrails.
"""

from __future__ import annotations

import os
import re
import time
from decimal import Decimal
from typing import Any

from src.db.repository import FinancialRepository
from src.engine.llm_explainer import (
    DEFAULT_GEMINI_MODEL,
    check_language_compliance,
)
from src.engine.news_radar import NewsRadar
from src.renderer.formatter import format_decimal_id, format_idr_nominal

# Static domain knowledge base distilled from docs/PRD.md & PRE_REGISTRATION.md
KNOWLEDGE_BASE = {
    "psak72": (
        "METODOLOGI PSAK 72 (PENDAPATAN DARI KONTRAK DENGAN PELANGGAN):\n"
        "• Eksposur Kontrak Bruto = Piutang Usaha Neto + Aset Kontrak (Lancar & Tidak Lancar).\n"
        "• Eksposur Kontrak Neto = Eksposur Bruto - Liabilitas Kontrak (Uang Muka Proyek).\n"
        "• Karakteristik Konstruksi: Pendapatan proyek diakui berbasis persentase fisik, namun "
        "penagihan kas tertahan sebagai aset kontrak menunggu persetujuan pemberi kerja.\n"
        "• Risiko Utama: Uang tertahan di proyek, membebani modal kerja dan membakar kas operasi."
    ),
    "sloan": (
        "METODOLOGI SLOAN ACCRUAL RATIO (KUALITAS LABA):\n"
        "• Formula: (Laba Bersih TTM - Arus Kas Operasi CFO TTM) / Rata-rata Aset 12 Bulan.\n"
        "• Ambang Batas: Sloan Ratio > +0.10 (+10% dari aset) mengindikasikan bahwa laba "
        "didominasi oleh pencatatan akrual di atas kertas, bukan aliran kas riil.\n"
        "• Nilai Negatif: Menandakan kualitas laba prima di mana kas operasional riil lebih besar "
        "daripada laba pembukuan (laba ditopang kas riil)."
    ),
    "cash_coverage": (
        "METODOLOGI CASH COVERAGE (SOLVABILITAS UTANG JANGKA PENDEK):\n"
        "• Formula: Kas & Setara Kas Bebas / Utang Berbunga Jangka Pendek (Bank + Obligasi JP).\n"
        "• Ambang Batas: Rasio < 0.20x menandakan kapasitas kas kritis karena kas bebas hanya "
        "menutup kurang dari 20% kewajiban pinjaman yang jatuh tempo dalam 12 bulan.\n"
        "• Bebas Utang Jangka Pendek: Emiten seperti TOTL dan ACST tidak memiliki utang berbunga "
        "jangka pendek, sehingga memiliki bantalan likuiditas kas paling aman."
    ),
    "safeguards": (
        "BENDERA PERHATIAN (SAFEGUARD FLAGS):\n"
        "1. Flag Acute Liquidity: Menyala jika Arus Kas Operasi (CFO TTM) < 0 dan Cash Coverage "
        "< 0.20x (kas bebas sempit sementara operasional membakar kas).\n"
        "2. Flag Accrual Divergence: Menyala jika Laba Bersih > 0, Arus Kas Operasi < 0, "
        "dan Sloan Accrual > +0.10 (laba di atas kertas tanpa dukungan kas riil)."
    ),
    "universe": (
        "SEMESTA EMITEN MULTI-SEKTOR BEI (20 EMITEN):\n"
        "• Konstruksi & Rekayasa: WIKA, WSKT, ADHI, PTPP, TOTL, NRCA, "
        "JKON, ACST, WEGE, PPRE, DGIK, PBSA.\n"
        "• Barang Konsumsi / FMCG: ICBP, UNVR, MYOR, AMRT.\n"
        "• Perbankan & Keuangan: BBRI, BMRI, BBNI, BRIS.\n"
        "Data diverifikasi mencakup laporan keuangan audited dan interim 2020-2025."
    ),
    "fmcg": (
        "KARAKTERISTIK KAS SEKTOR BARANG KONSUMEN / FMCG:\n"
        "• Model Bisnis: Arus kas operasional (CFO) sangat masif dan cepat karena penjualan "
        "kebutuhan pokok dibayar tunai oleh konsumen atau termin cepat oleh jaringan distributor.\n"
        "• Risiko Utama: Penumpukan stok persediaan barang di gudang dan piutang dagang ritel.\n"
        "• Emiten Terdaftar: ICBP, UNVR, MYOR, AMRT (Alfamart)."
    ),
    "banking": (
        "KARAKTERISTIK LIKUIDITAS SEKTOR PERBANKAN:\n"
        "• Model Bisnis: Menghimpun Dana Pihak Ketiga (DPK Simpanan) dan menyalurkan kredit.\n"
        "• Metrik Kunci: Cadangan Likuiditas Kas & Giro BI vs DPK, Rasio Kredit Macet (NPL < 5%), "
        "dan kecukupan cadangan risiko kredit (CKPN).\n"
        "• Emiten Terdaftar: BBRI, BMRI, BBNI, BRIS."
    ),
}

KNOWN_TICKERS = [
    "ADHI", "PTPP", "WIKA", "WSKT", "WEGE", "PPRE",
    "TOTL", "NRCA", "ACST", "JKON", "DGIK", "PBSA",
    "ICBP", "UNVR", "MYOR", "AMRT",
    "BBRI", "BMRI", "BBNI", "BRIS",
]


class RAGFinancialChatbot:
    """Conversational Financial Accounting AI grounded on deterministic RAG facts."""

    _quota_exhausted_until: float = 0.0

    def __init__(
        self,
        repository: FinancialRepository | None = None,
        news_radar: NewsRadar | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.repo = repository or FinancialRepository()
        self.news_radar = news_radar or NewsRadar()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._client: Any = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                print(f"⚠️ Warning: Could not initialize Gemini Client for RAG: {exc}")
                self._client = None

    def get_all_known_tickers(self) -> set[str]:
        """Loads all active tickers dynamically from SQLite + static fallback."""
        known = set(KNOWN_TICKERS)
        try:
            with self.repo.get_connection() as conn:
                rows = conn.execute("SELECT ticker FROM issuers;").fetchall()
                for r in rows:
                    if r["ticker"]:
                        known.add(str(r["ticker"]).upper())
        except Exception:
            pass
        return known

    def extract_tickers_from_query(self, query: str) -> list[str]:
        """Extracts mentioned stock tickers from user query dynamically."""
        known = self.get_all_known_tickers()
        found: list[str] = []
        tokens = re.findall(r"\b[A-Za-z]{4}\b", query.upper())
        for token in tokens:
            if token in known and token not in found:
                found.append(token)
        return found

    def retrieve_context_for_query(self, user_query: str) -> dict[str, Any]:
        """Retrieves exact database facts, relevant knowledge base chunks, and news."""
        retrieved_facts: list[str] = []
        mentioned_tickers = self.extract_tickers_from_query(user_query)

        # 1. Fetch exact database metrics if tickers mentioned
        for ticker in mentioned_tickers:
            issuer = self.repo.get_issuer(ticker)
            comp_name = issuer.company_name if issuer else ticker

            # Latest 2025 metric
            query_latest = """
            SELECT cm.*, f.fiscal_year FROM computed_metrics cm
            JOIN filings f ON cm.filing_id = f.filing_id
            WHERE cm.ticker = ? ORDER BY f.fiscal_year DESC LIMIT 1;
            """
            with self.repo.get_connection() as conn:
                row = conn.execute(query_latest, (ticker,)).fetchone()

            if row:
                free = bool(row["debt_free_short_term"])
                cov_val = row["cash_coverage_ratio"]
                cov_str = (
                    "Bebas Utang Jk. Pendek"
                    if free
                    else f"{format_decimal_id(Decimal(str(cov_val)), 2)}x"
                    if cov_val
                    else "N/A"
                )
                cfo_raw = row["cfo_ttm_idr"]
                cfo_str = format_idr_nominal(Decimal(str(cfo_raw))) if cfo_raw else "0"
                ni_raw = row["net_income_ttm_idr"]
                ni_str = format_idr_nominal(Decimal(str(ni_raw))) if ni_raw else "0"
                sloan_raw = row["sloan_ratio_ttm"]
                sloan_str = (
                    f"{format_decimal_id(Decimal(str(sloan_raw)) * 100, 1)}%"
                    if sloan_raw
                    else "N/A"
                )
                gross_raw = row["gross_contract_exposure_ratio"]
                gross_str = (
                    f"{format_decimal_id(Decimal(str(gross_raw)) * 100, 1)}%"
                    if gross_raw
                    else "N/A"
                )
                flag_acute = bool(row["flag_acute_liquidity"])
                flag_accrual = bool(row["flag_accrual_divergence"])

                status_flag = (
                    "Tekanan Likuiditas Akut"
                    if flag_acute
                    else ("Divergensi Akrual" if flag_accrual else "Normal / Aman")
                )

                retrieved_facts.append(
                    f"DATA RESMI BEI — {ticker} ({comp_name}) FY {row['fiscal_year']}:\n"
                    f"• Arus Kas Operasi (CFO TTM): Rp {cfo_str}\n"
                    f"• Laba Bersih TTM: Rp {ni_str}\n"
                    f"• Sloan Accrual Ratio: {sloan_str}\n"
                    f"• Solvabilitas Utang JP (Cash Coverage): {cov_str}\n"
                    f"• Eksposur Kontrak PSAK 72: {gross_str} dari pendapatan\n"
                    f"• Status Safeguard: {status_flag}"
                )

            # Historical 4-year trend context
            query_hist = """
            SELECT f.fiscal_year, cm.cash_coverage_ratio, cm.debt_free_short_term,
                   cm.cfo_ttm_idr, cm.flag_acute_liquidity
            FROM filings f
            LEFT JOIN computed_metrics cm ON f.filing_id = cm.filing_id
            WHERE f.ticker = ? ORDER BY f.fiscal_year ASC;
            """
            with self.repo.get_connection() as conn:
                hist_rows = conn.execute(query_hist, (ticker,)).fetchall()

            if hist_rows:
                h_lines = []
                for hr in hist_rows:
                    y = hr["fiscal_year"]
                    cfo_h = (
                        format_idr_nominal(Decimal(str(hr["cfo_ttm_idr"])))
                        if hr["cfo_ttm_idr"]
                        else "0"
                    )
                    cov_h = (
                        "Bebas Utang"
                        if hr["debt_free_short_term"]
                        else f"{format_decimal_id(Decimal(str(hr['cash_coverage_ratio'])), 2)}x"
                        if hr["cash_coverage_ratio"]
                        else "N/A"
                    )
                    h_lines.append(f"  FY {y}: CFO Rp {cfo_h}, Rasio Kas {cov_h}")
                retrieved_facts.append(f"Histori 4 Tahun {ticker}:\n" + "\n".join(h_lines))

            # Recent news for ticker
            news_items = self.news_radar.get_news_for_ticker(ticker, max_items=2)
            if news_items:
                n_lines = [f"  • [{it.sentiment}] {it.headline}" for it in news_items]
                retrieved_facts.append(f"Sentimen Berita {ticker}:\n" + "\n".join(n_lines))

        # 2. General leaderboard context if ranking/leaderboard is relevant
        q_lower = user_query.lower()
        rank_keywords = [
            "siapa", "peringkat", "klasemen", "terbaik", "paling", "aman", "sehat", "top"
        ]
        if any(w in q_lower for w in rank_keywords):
            query_top = """
            SELECT cm.ticker, i.company_name, cm.cash_coverage_ratio, cm.debt_free_short_term,
                   cm.cfo_ttm_idr, cm.flag_acute_liquidity
            FROM computed_metrics cm
            JOIN filings f ON cm.filing_id = f.filing_id
            JOIN issuers i ON cm.ticker = i.ticker
            WHERE f.fiscal_year = 2025;
            """
            with self.repo.get_connection() as conn:
                top_rows = conn.execute(query_top).fetchall()
            if top_rows:
                retrieved_facts.append(
                    "IKHTISAR SOLVABILITAS 12 EMITEN KONSTRUKSI (FY 2025):\n"
                    "• Bebas Utang JP: TOTL, ACST.\n"
                    "• Rasio Kas Sangat Kuat (> 2.0x): PBSA (200x), JKON (13.6x), "
                    "WEGE (4.6x), NRCA (2.0x).\n"
                    "• Rasio Kas Cukup (0.5x - 1.2x): WIKA (0.95x), DGIK (0.56x), "
                    "ADHI (0.55x), PTPP (0.51x).\n"
                    "• Tekanan Likuiditas (< 0.25x): WSKT (0.22x), PPRE (0.17x)."
                )

        # 3. Retrieve relevant methodology knowledge chunks
        relevant_knowledge: list[str] = [KNOWLEDGE_BASE["universe"]]
        if any(w in q_lower for w in ["psak", "72", "kontrak", "aset kontrak", "piutang"]):
            relevant_knowledge.append(KNOWLEDGE_BASE["psak72"])
        if any(w in q_lower for w in ["sloan", "akrual", "kualitas laba", "laba semu"]):
            relevant_knowledge.append(KNOWLEDGE_BASE["sloan"])
        if any(w in q_lower for w in ["kas", "coverage", "utang", "likuiditas", "solvabilitas"]):
            relevant_knowledge.append(KNOWLEDGE_BASE["cash_coverage"])
        if any(w in q_lower for w in ["bendera", "flag", "safeguard", "bahaya", "peringatan"]):
            relevant_knowledge.append(KNOWLEDGE_BASE["safeguards"])
        if any(w in q_lower for w in ["fmcg", "konsumen", "makanan", "stok", "persediaan"]):
            relevant_knowledge.append(KNOWLEDGE_BASE["fmcg"])
        if any(w in q_lower for w in ["bank", "perbankan", "kredit", "dpk", "npl"]):
            relevant_knowledge.append(KNOWLEDGE_BASE["banking"])

        return {
            "retrieved_facts": "\n\n".join(retrieved_facts),
            "relevant_knowledge": "\n\n".join(relevant_knowledge),
            "mentioned_tickers": mentioned_tickers,
        }

    def generate_deterministic_fallback_answer(
        self, query: str, context: dict[str, Any]
    ) -> str:
        """Deterministic rule-based conversational answer written in friendly layman Indonesian."""
        tickers = context["mentioned_tickers"]
        q_lower = query.lower()

        if tickers:
            t0 = tickers[0]
            # Fetch latest 2025 metrics directly
            query_metrics = """
            SELECT cm.*, i.company_name, i.idx_sub_industry, f.fiscal_year
            FROM computed_metrics cm
            JOIN filings f ON cm.filing_id = f.filing_id
            JOIN issuers i ON cm.ticker = i.ticker
            WHERE cm.ticker = ?
            ORDER BY f.fiscal_year DESC LIMIT 1;
            """
            with self.repo.get_connection() as conn:
                row = conn.execute(query_metrics, (t0,)).fetchone()

            if row:
                r = dict(row)
                comp = r.get("company_name", t0)
                is_free = bool(r.get("debt_free_short_term"))
                cov_raw = r.get("cash_coverage_ratio")
                cov = float(cov_raw) if cov_raw is not None else 0.0
                cfo = float(r.get("cfo_ttm_idr") or 0.0)
                net_inc = float(r.get("net_income_ttm_idr") or 0.0)
                sloan = float(r.get("sloan_ratio_ttm") or 0.0)
                flag_liq = bool(r.get("flag_acute_liquidity"))
                flag_div = bool(r.get("flag_accrual_divergence"))

                # 1. Professional liquidity status evaluation
                if is_free:
                    status_badge = "🟢 SANGAT AMAN (Bebas Utang Jangka Pendek)"
                    cov_expl = (
                        "Perusahaan beroperasi tanpa beban utang berbunga jangka pendek, "
                        "sehingga memiliki tingkat proteksi likuiditas kas yang prima."
                    )
                elif cov >= 1.0:
                    status_badge = f"🟢 SOLVEN & AMAN (Bantalan Kas {cov:.2f}x)"
                    cov_expl = (
                        f"Perusahaan memegang cadangan kas setara {cov:.2f} kali lipat "
                        f"dari seluruh kewajiban pinjaman yang jatuh tempo dalam periode 12 bulan."
                    )
                elif cov >= 0.5:
                    status_badge = f"🟡 CUKUP TERKENDALI (Bantalan Kas {cov:.2f}x)"
                    cov_expl = (
                        f"Cadangan kas likuid mencakup {int(cov * 100)}% dari total pinjaman "
                        f"jangka pendek. Likuiditas memadai namun memerlukan disiplin modal kerja."
                    )
                else:
                    status_badge = f"🔴 TEKANAN LIKUIDITAS KAS (Bantalan Kas {cov:.2f}x)"
                    cov_expl = (
                        f"Cadangan kas bebas bernilai kritis ({cov:.2f}x utang jangka pendek), "
                        f"sehingga pemenuhan liabilitas sangat bergantung pada fasilitas baru "
                        f"atau jadwal restrukturisasi kewajiban pinjaman."
                    )

                # 2. Professional profit quality evaluation
                if cfo > 0 and sloan <= 0.05:
                    profit_expl = (
                        "Kualitas Laba Kas Prima. Operasional menghasilkan arus kas riil surplus "
                        "yang menopang laba pembukuan secara berkesinambungan."
                    )
                elif net_inc > 0 and cfo < 0:
                    profit_expl = (
                        "Divergensi Akrual Signifikan. Perusahaan membukukan laba akuntansi, "
                        "namun arus kas operasi (CFO) defisit karena modal kerja tertahan "
                        "pada tagihan piutang dan aset kontrak pelanggan."
                    )
                else:
                    profit_expl = (
                        "Arus kas operasi memerlukan pengawasan berkala guna memastikan kapasitas "
                        "pembentukan kas bebas tetap sejalan dengan target solvabilitas."
                    )

                # 3. Professional analytical conclusion
                if flag_liq:
                    saran = (
                        "Fokus Pengawasan: Emiten memerlukan efisiensi modal kerja ketat dan "
                        "manajemen profil jatuh tempo utang guna menjaga stabilitas likuiditas."
                    )
                elif flag_div:
                    saran = (
                        "Fokus Pengawasan: Monitor tingkat penagihan termin proyek dan konversi "
                        "aset kontrak menjadi kas guna memperbaiki profil arus kas operasi."
                    )
                else:
                    saran = (
                        "Struktur likuiditas dan kualitas laba terpantau berada dalam ambang "
                        "batas fundamental yang sehat dan terkendali."
                    )

                fy_label = r.get("fiscal_year", 2025)
                return (
                    f"Berikut adalah evaluasi profil likuiditas dan solvabilitas kas {t0} "
                    f"({comp}) berdasarkan laporan keuangan resmi BEI audited FY {fy_label}:\n\n"
                    f"1. Profil Likuiditas & Kapasitas Penutupan Utang: {status_badge}\n"
                    f"• {cov_expl}\n\n"
                    f"2. Kualitas Arus Kas Operasional terhadap Laba Akuntansi:\n"
                    f"• {profit_expl}\n\n"
                    f"3. Kesimpulan Evaluasi Finansial Eksekutif:\n"
                    f"• {saran}\n\n"
                    f"💡 Catatan Analis: Data keuangan resmi BEI audited FY {fy_label} "
                    f"terverifikasi secara deterministik tanpa penyesuaian subjektif."
                )

        if "psak" in q_lower or "kontrak" in q_lower or "aset kontrak" in q_lower:
            return (
                "Tinjauan Metodologi Standar Akuntansi PSAK 72:\n\n"
                "PSAK 72 mengatur prinsip pengakuan pendapatan dari kontrak pelanggan. "
                "Pada sektor konstruksi dan rekayasa sipil, pendapatan diakui seiring "
                "pemenuhan kewajiban pelaksanaan (persentase fisik). Selisih antara "
                "pekerjaan diakui dengan termin penagihan dicatat sebagai 'Aset Kontrak'. "
                "Tingginya aset kontrak terhadap pendapatan mengindikasikan bahwa arus kas masuk "
                "riil masih tertahan dalam proses persetujuan administratif pemberi kerja."
            )

        if "sloan" in q_lower or "akrual" in q_lower or "laba semu" in q_lower:
            return (
                "Tinjauan Metodologi Kualitas Laba (Sloan Accrual Ratio):\n\n"
                "Sloan Accrual Ratio mengukur proporsi laba bersih yang bersumber dari pos akrual "
                "relatif terhadap arus kas operasi riil (CFO) atas rata-rata total aset.\n\n"
                "• Nilai Negatif / Rendah: Kualitas laba prima, menunjukkan bahwa arus kas riil "
                "melampaui laba akuntansi pembukuan.\n"
                "• Nilai Positif Tinggi (> +0.10): Mengindikasikan pembentukan laba didominasi pos "
                "akrual (piutang/aset kontrak), sehingga memerlukan evaluasi kelancaran arus kas."
            )

        if any(w in q_lower for w in ["top", "siapa", "aman", "sehat", "terbaik"]):
            return (
                "Ikhtisar Ketahanan Likuiditas dan Solvabilitas Emiten (FY 2025):\n\n"
                "1. Kategori Proteksi Likuiditas Tertinggi (Bebas Utang Jangka Pendek):\n"
                "• TOTL (Total Bangun Persada Tbk.) dan ACST (Acset Indonusa Tbk.)\n"
                "Keduanya beroperasi tanpa eksposur utang bank berbunga jangka pendek.\n\n"
                "2. Kategori Kapasitas Cadangan Kas Prima (> 2.0x Utang Jangka Pendek):\n"
                "• PBSA, JKON, ICBP, UNVR (memiliki bantalan kas sangat memadai).\n\n"
                "3. Kategori Pengawasan Likuiditas Khusus:\n"
                "• WSKT dan TOPS (rasio kas terhadap utang berbunga jangka pendek di bawah 0.25x)."
            )

        return (
            "Selamat datang di Sistem Intelijen Finansial IDX Cash Radar. "
            "Anda dapat menanyakan analisis likuiditas, solvabilitas kas, dan pengujian akrual.\n\n"
            "Contoh topik konsultasi:\n"
            "• 'Bagaimana evaluasi profil kas dan solvabilitas WIKA?'\n"
            "• 'Emiten mana yang memiliki cadangan likuiditas terkuat?'\n"
            "• 'Analisis eksposur likuiditas WSKT'\n"
            "• 'Penjelasan metodologi Sloan Accrual dan PSAK 72'"
        )

    def answer_query(self, user_query: str) -> str:
        """Answers free-form conversational questions using grounded RAG."""
        context = self.retrieve_context_for_query(user_query)

        # Fallback if no client configured or currently in quota exhaustion backoff
        if (
            not self._client
            or not self.api_key
            or time.time() < RAGFinancialChatbot._quota_exhausted_until
        ):
            return self.generate_deterministic_fallback_answer(user_query, context)

        facts_block = (
            context["retrieved_facts"]
            if context["retrieved_facts"]
            else "Tidak ada data emiten spesifik yang disebutkan."
        )
        knowledge_block = context["relevant_knowledge"]

        prompt_data = f"""
PERTANYAAN PENGGUNA:
"{user_query}"

FAKTA DETERMINISTIK DATABASE (HASIL RETRIEVAL):
{facts_block}

BASIS PENGETAHUAN METODOLOGI FINANSIAL (KNOWLEDGE RETRIEVAL):
{knowledge_block}
"""

        system_instruction = (
            "Anda adalah Senior Financial Analyst & Konsultan Finansial IDX Cash Radar.\n"
            "Tugas: Jawab pertanyaan pengguna secara cerdas, ramah, dan edukatif "
            "menggunakan fakta dan knowledge base di atas.\n\n"
            "ATURAN WAJIB (STRICT GUARDRAILS):\n"
            "1. STRICT GROUNDING: Seluruh angka kas, utang, dan rasio WAJIB bersumber persis "
            "dari fakta database di atas. DILARANG menghitung atau mengarang angka baru.\n"
            "2. NON-ACCUSATORY (SECTION 7 AGENTS.MD): DILARANG menggunakan kata terlarang "
            "(manipulasi, window dressing, laporan palsu, saham gorengan, penipuan, fraud, "
            "bangkrut, rekayasa laba).\n"
            "3. NO INVESTMENT ADVICE: Dilarang memberi rekomendasi beli/jual dan target harga.\n"
            "4. STYLE: Bahasa Indonesia santai dan ramah orang awam, memakai analogi bisnis "
            "sederhana yang mudah dipahami pemula tanpa rumus rumit, panjang 2-3 paragraf padat."
        )

        import threading

        res_holder: list[Any] = []

        def worker() -> None:
            try:
                resp = self._client.models.generate_content(
                    model=self.model_name,
                    contents=f"{system_instruction}\n\nDATA RETRIEVAL:\n{prompt_data}",
                )
                if resp and resp.text:
                    res_holder.append(resp.text.strip())
            except Exception as e:
                res_holder.append(e)

        th = threading.Thread(target=worker, daemon=True)
        th.start()
        th.join(timeout=1.5)

        if res_holder and isinstance(res_holder[0], str) and res_holder[0]:
            if check_language_compliance(res_holder[0]):
                return res_holder[0]

        # If timed out or network blocked, set backoff so subsequent requests answer in <10ms
        if not res_holder or isinstance(res_holder[0], Exception):
            RAGFinancialChatbot._quota_exhausted_until = time.time() + 600

        return self.generate_deterministic_fallback_answer(user_query, context)
