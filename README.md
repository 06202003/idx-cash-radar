# 📡 IDX Cash & Accrual Radar (v2.0)

> **Audit-Ready XBRL Financial Data Pipeline, Web Intelligence Dashboard & Deterministic Liquidity Profiling for IDX Issuers**  
> *By Yehezkiel David Setiawan, S.Kom., M.Kom.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Web%20Dashboard-009688.svg)](https://idx-cash-radar.vercel.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-136%20passed-brightgreen.svg)](https://pytest.org/)

🌐 **Live Web Dashboard:** [idx-cash-radar.vercel.app](https://idx-cash-radar.vercel.app) · **Metodologi & Threshold:** [/metodologi](https://idx-cash-radar.vercel.app/metodologi)

---

## 📌 Latar Belakang & Masalah Bisnis

Pada laporan keuangan di Bursa Efek Indonesia (BEI) — terutama emiten konstruksi di bawah standar **PSAK 72 / IFRS 15** — perusahaan kerap membukukan **laba bersih positif di atas kertas**, sementara arus kas operasionalnya (*Cash Flow from Operations* / CFO) mengalami defisit kronis karena kas tertahan di tagihan piutang dan aset kontrak. Ketidaksinkronan antara laba akuntansi dan kas riil ini kerap mendahului tekanan likuiditas jangka pendek.

**IDX Cash & Accrual Radar** mengekstraksi laporan XBRL resmi BEI, menormalisasi taksonomi, menghitung rasio kualitas kas secara deterministik, serta menyajikannya melalui **Web Dashboard (FastAPI)** dan **Bot Telegram (`aiogram 3.x`)** dengan jejak audit dokumen primer yang dapat diverifikasi.

---

## 🏛️ Prinsip Rekayasa Utama (*Non-Negotiables*)

1. **Deterministic Math First:**  
   Seluruh de-kumulasi YTD, kalkulasi rasio PSAK 72, *Sloan Accrual Ratio*, *Cash Coverage*, dan flag bahaya kas dihitung menggunakan Python deterministik (`Decimal`, `pandas`, `scipy`). LLM dilarang keras melakukan perhitungan aritmatika.
2. **Mandatory Audit Trail:**  
   Setiap angka metrik membawa metadata verifikasi dokumen primer BEI: `raw_xbrl_tag` (`localname` & `namespace`), `raw_context_ref`, `unitRef`, `decimals`, serta hash SHA-256 berkas.
3. **Strict Separation of Math & AI Narrative (LLM as Translator Only):**  
   Google Gemini API (`google-genai`) hanya difungsikan sebagai *Narrative Translator* dan asisten tanya-jawab untuk menerjemahkan metrik deterministik menjadi bahasa Indonesia yang mudah dipahami, dilengkapi *deterministic fallback* jika API offline.
4. **Contextual Isolation untuk Sentimen Berita:**  
   Berita dan keterbukaan informasi BEI diposisikan murni sebagai konteks sekunder. Berita positif (misal raihan kontrak baru) **tidak dapat** membatalkan atau menurunkan flag tekanan kas (`FLAG_ACUTE_LIQUIDITY`).
5. **Deterministic Verbatim Grounding Verifier (CALK PDF):**  
   Setiap angka catatan kaki laporan keuangan (CALK) yang diekstrak diverifikasi secara verbatim terhadap teks sumber halaman PDF primer.
6. **Kepatuhan Hukum & Bahasa Non-Tuduhan:**  
   Platform menggunakan terminologi deskriptif faktual (diuji otomatis via `tests/test_language_compliance.py`) dan tidak memberikan rekomendasi beli/jual maupun target harga saham.

---

## 🖥️ Fitur Web Dashboard (`FastAPI` + Vercel)

* **Dual Mode (`Simple Mode` vs `Expert Mode`):** Tampilan ramah investor ritel dan mode analitik lengkap untuk analis.
* **Fundamental Screener:** Pemetaan **49 emiten BEI** lintas **5 makro sektor** (*Konstruksi & Rekayasa Sipil, FMCG & Konsumer, Perbankan & Keuangan, Energi & Pertambangan, Telekomunikasi & Menara*).
* **Stock Detail & Financials:** Grafik harga saham, diagnostik deterministik kas vs utang, inspektor catatan kaki CALK (Note 8), proyeksi CFO multi-tahun, serta simulator stres modal *What-If* (Pro/Lanjutan).
* **Daily News & URL Radar:** Pemindai berita RSS & analisis URL artikel untuk cross-check sentimen terhadap kondisi kas riil emiten.
* **AI Financial Analyst & Portfolio X-Ray:** Konsultasi interaktif berbasis data XBRL terverifikasi dan evaluasi eksposur likuiditas portofolio.
* **Halaman Transparansi (`/metodologi`):** Dokumentasi terbuka rumus deterministik, hasil evaluasi *time-series* (2022–2025), dan limitasi data.

---

## 📐 Metodologi Kuantitatif

### 1. De-kumulasi Kuartal Tunggal & Trailing Twelve Months (TTM)
* $Q_1 = \text{YTD}_{3M}$
* $Q_2 = \text{YTD}_{6M} - \text{YTD}_{3M}$
* $Q_3 = \text{YTD}_{9M} - \text{YTD}_{6M}$
* $Q_4 = \text{YTD}_{12M} - \text{YTD}_{9M}$ (ditandai `is_audit_derived_q4 = True`)
* $\text{TTM}_t = \text{YTD}_t + \text{FY}_{t-1} - \text{YTD}_{t-4}$

### 2. Tiga Pilar Metrik Inti
* **Pilar 1 — Intensitas Eksposur Kontrak PSAK 72:**  
  $\text{Gross Exposure} = \text{Piutang Usaha} + \text{Aset Kontrak (Lancar + Non-Lancar)}$  
  $\text{Net Exposure} = \text{Gross Exposure} - \text{Liabilitas Kontrak}$  
  *(Dilengkapi Revenue Contraction Guard jika pendapatan TTM $\le 0$ atau turun $> 50\%$ YoY.)*
* **Pilar 2 — Sloan Accrual Ratio (TTM):**  
  $$\text{Sloan Ratio}_{\text{TTM}} = \frac{\text{Laba Bersih}_{\text{TTM}} - \text{CFO}_{\text{TTM}}}{(\text{Total Aset}_t + \text{Total Aset}_{t-4}) / 2}$$
  *(Mendeteksi porsi laba akrual ketika rasio melampaui $+0.10$ / $+10\%$.)*
* **Pilar 3 — Cash-to-Short-Term Interest-Bearing Debt Coverage:**  
  $$\text{Cash Coverage} = \frac{\text{Kas dan Setara Kas}}{\text{Utang Berbunga Jangka Pendek}}$$
  *(Dilengkapi Debt-Free Guard untuk emiten dengan utang berbunga jangka pendek $= 0$.)*

### 3. Safeguard Flags
* **`FLAG_ACCRUAL_DIVERGENCE`:** Laba Bersih TTM $> 0$, $\text{CFO}_{\text{TTM}} < 0$, $\text{CFO}_{Q} < 0$, dan $\text{Sloan Ratio} > 0.10$.
* **`FLAG_ACUTE_LIQUIDITY`:** $\text{CFO}_{\text{TTM}} < 0$, utang jangka pendek berbunga $> 0$, dan $\text{Cash Coverage} < 0.20\text{x}$.

---

## 🤖 Antarmuka Perintah Bot Telegram (`aiogram 3.x`)

* `/check <KODE>` (atau ketik langsung kode saham, misal `TOTL`): Kartu diagnostik komprehensif, metrik 3 pilar, audit trail XBRL primer, dan ringkasan eksekutif AI.
* `/ticker`: Direktori emiten yang tercakup.
* `/top`: Klasemen solvabilitas kas & likuiditas (FY 2025).
* `/compare <K1> <K2>`: Komparasi *head-to-head* ketahanan kas dan profil utang (contoh: `/compare WIKA TOTL`).
* `/trend <KODE>`: Tren arus kas dan solvabilitas historis 4 tahun (2022–2025).
* `/calk <KODE>`: Rincian catatan kaki CALK dengan verifikasi grounding verbatim.
* `/ask <PERTANYAAN>`: Asisten percakapan berbasis database dan metodologi akuntansi.
* `/help`: Panduan metodologi dan interpretasi rasio.

---

## 📁 Struktur Repositori

```text
idx-cash-radar/
├── api/                             # Entrypoint serverless Vercel
├── pyproject.toml                   # Konfigurasi dependensi, ruff, & pytest
├── requirements.txt                 # Dependensi runtime web & Vercel
├── vercel.json                      # Konfigurasi routing & build Vercel
├── Dockerfile                       # Kontainerisasi produksi (Python 3.11-slim)
├── docker-compose.yml               # Orkestrasi container keep-alive
├── config/
│   └── taxonomy_mapping.yaml        # Kamus tag XBRL BEI cor/2020-01-01
├── data/
│   ├── raw_xbrl/                    # Berkas XBRL resmi BEI
│   └── calk_samples/                # Sampel catatan kaki laporan keuangan CALK
├── docs/
│   ├── PRD.md                       # Blueprint Product Requirements Document
│   ├── PRE_REGISTRATION.md          # Protokol uji terkunci
│   ├── DEPLOYMENT.md                # Panduan deployment VPS cloud
│   ├── glosarium.md                 # Glosarium istilah keuangan & metrik
│   └── adr/                         # Architecture Decision Records (001–003)
├── scripts/
│   ├── download_idx_filings.py      # Pengunduh otomatis berkas BEI (SHA-256 verified)
│   ├── ingest_filings.py            # CLI batch ingestion ke SQLite
│   ├── run_case_evaluation.py       # Evaluasi retrospektif (Known Distress vs Control)
│   └── benchmark_latency.py         # Pengukur latensi kueri database (< 50 ms)
├── src/
│   ├── web/
│   │   ├── app.py                   # FastAPI backend, API endpoints & /metodologi
│   │   └── templates/index.html     # Web Dashboard (Simple & Expert Mode)
│   ├── parser/
│   │   ├── xbrl_reader.py           # Parser lxml zero-dimension context filter
│   │   ├── normalizer.py            # Pemetaan taksonomi bursa ke skema kanonikal
│   │   ├── sanity_check.py          # 4-Way Sanity Check
│   │   └── pdf_calk_reader.py       # Pembaca PDF & pelacak halaman CALK
│   ├── engine/
│   │   ├── decumulator.py           # Konversi YTD -> Standalone Q & TTM
│   │   ├── calculator.py            # 3 metrik inti & zero-denominator guard
│   │   ├── cohort.py                # Small-N Guard (N >= 8), peringkat, & median
│   │   ├── safeguards.py            # Evaluator boolean bendera anomali kas
│   │   ├── verbatim_grounding.py    # Deterministic Verbatim Grounding Verifier
│   │   ├── calk_extractor.py        # Ekstraktor CALK pihak berelasi & CKPN
│   │   ├── llm_explainer.py         # Narator eksekutif Google Gemini API + fallback
│   │   ├── news_radar.py            # Klasifikasi sentimen berita & isolasi konteks
│   │   └── rag_chat.py              # Conversational RAG Engine
│   ├── db/
│   │   ├── schema.sql               # DDL skema relasional SQLite3
│   │   └── repository.py            # Repository pattern kueri deterministik
│   ├── renderer/                    # Perender Jinja2 & formatter angka Indonesia
│   └── bot/
│       └── main.py                  # Entrypoint Bot Telegram aiogram 3.x (IPv4)
└── tests/                           # 136 automated unit & integration tests
```

---

## 🚀 Cara Menjalankan Proyek

### 1. Prasyarat Lingkungan
* Python 3.11 atau lebih baru
* (Opsional) Token Bot Telegram via `@BotFather`
* (Opsional) Google Gemini API Key dari [Google AI Studio](https://aistudio.google.com/)

### 2. Instalasi Dependensi
```bash
git clone https://github.com/06202003/idx-cash-radar.git
cd idx-cash-radar
python -m venv .venv
source .venv/bin/activate  # atau .venv\Scripts\activate pada Windows
pip install -e ".[dev]"
```

### 3. Konfigurasi Lingkungan
Salin file `.env.example` menjadi `.env` dan lengkapi kuncinya:
```bash
cp .env.example .env
```
Contoh isi `.env`:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

### 4. Menjalankan Pengujian Otomatis (*Unit & Integration Tests*)
```bash
python -m pytest
```

### 5. Menjalankan Web Dashboard Secara Lokal
```bash
uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload
```
Buka `http://localhost:8000` (atau `http://localhost:8000/metodologi`).

### 6. Menjalankan Bot Telegram
```bash
python -m src.bot.main
```

### 7. Menjalankan via Docker (Produksi)
```bash
docker compose up -d --build
docker compose logs -f
```

---

## 📄 Lisensi & Kepatuhan Legal

Proyek ini dirilis di bawah lisensi terbuka [MIT License](LICENSE). Seluruh data laporan keuangan bersumber dari dokumen keterbukaan informasi publik Bursa Efek Indonesia (BEI) untuk tujuan edukasi, penelitian finansial, dan audit fakta berbasis data terbuka. Proyek ini tidak memberikan rekomendasi investasi, nasihat keuangan, maupun target harga saham.
