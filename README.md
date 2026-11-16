# 📡 IDX Cash & Accrual Radar (v2.0)
> **Audit-Ready XBRL Financial Data Pipeline & Deterministic Liquidity Profiling for IDX Construction Sector**  
> *Proof-of-Concept & Production Portfolio Platform by Yehezkiel David Setiawan, S.Kom., M.Kom.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-102%20passed-brightgreen.svg)](https://pytest.org/)

---

## 📌 Latar Belakang & Masalah Bisnis

Pada industri konstruksi di Bursa Efek Indonesia (BEI), emiten kerap membukukan **laba bersih positif di atas kertas** melalui metode pengakuan pendapatan berbasis persentase penyelesaian fisik (*percentage-of-completion* di bawah rezim **PSAK 72 / IFRS 15**). Namun, arus kas operasionalnya (*Cash Flow from Operations* / CFO) mengalami defisit kronis karena dana tertahan dalam bentuk tagihan piutang dan aset kontrak yang belum ditagihkan atau belum dicairkan oleh pemberi kerja. Fenomena ini menyebabkan krisis likuiditas akut pada sejumlah BUMN Karya (seperti kasus gagal bayar obligasi WIKA dan WSKT).

**IDX Cash & Accrual Radar** adalah platform data engineering dan intelijen finansial deterministik yang mengekstraksi, menormalisasi, memprofilkan kualitas arus kas, serta mendeteksi distorsi laba akrual emiten konstruksi BEI secara objektif dan bebas halusinasi.

---

## 🏛️ Prinsip Rekayasa Utama (*Non-Negotiables*)

1. **Deterministic Math First (Zero-Hallucination Baseline):**  
   Semua operasi matematika, penyesuaian de-kumulasi YTD, kalkulasi rasio PSAK 72, *Sloan Accrual*, *Cash Coverage*, serta pemeringkatan kuartil kohort dikomputasi menggunakan Python deterministik (`Decimal`, `pandas`, `scipy`). Model bahasa (LLM) dilarang keras melakukan perhitungan aritmatika.
2. **Mandatory Audit Trail:**  
   Setiap angka metrik membawa metadata verifikasi dokumen primer BEI: nama tag XML XBRL (`localname` & `namespace`), `contextRef`, `unitRef`, `decimals`, nilai mentah, dan hash SHA-256 berkas.
3. **Strict Separation of Math & AI Narrative (LLM as Translator Only):**  
   Google Gemini API (`google-genai`) hanya difungsikan sebagai *Narrative Translator* dan *RAG Conversational Assistant* untuk menerjemahkan angka rasio teknis menjadi bahasa Indonesia yang ramah investor ritel (maksimal 3–4 kalimat). Tersedia mekanisme *deterministic fallback* jika API offline.
4. **Contextual Isolation untuk Sentimen Berita:**  
   Keterbukaan informasi dan berita bursa diposisikan sebagai konteks sekunder. Berita positif (misal: "Raihan Kontrak Baru Rp 5 Triliun") **tidak dapat** membatalkan atau menurunkan bendera bahaya kas (`FLAG_ACUTE_LIQUIDITY`).
5. **Deterministic Verbatim Grounding Verifier (CALK PDF):**  
   Pencegahan halusinasi angka pada ekstraksi catatan kaki laporan keuangan (CALK). Setiap angka yang diekstrak diverifikasi secara verbatim terhadap token teks sumber halaman PDF primer. Jika ada angka yang tidak cocok, ekstraksi otomatis ditolak (*rejected*).
6. **Kepatuhan Hukum & Bahasa Non-Tuduhan:**  
   Sistem dilarang menggunakan kata-kata tuduhan pidana (*"manipulasi"*, *"window dressing"*, *"laporan palsu"*, *"fraud"*, *"bangkrut"*, *"saham gorengan"*, *"rekomendasi beli/jual"*). Seluruh output menggunakan terminologi matematis deskriptif faktual.

---

## 📐 Metodologi Kuantitatif

### 1. De-kumulasi Kuartal Tunggal & Trailing Twelve Months (TTM)
Karena laporan keuangan kuartalan di BEI disajikan secara kumulatif (*Year-to-Date*):
* $Q_1 = \text{YTD}_{3M}$
* $Q_2 = \text{YTD}_{6M} - \text{YTD}_{3M}$
* $Q_3 = \text{YTD}_{9M} - \text{YTD}_{6M}$
* $Q_4 = \text{YTD}_{12M} - \text{YTD}_{9M}$ (ditandai `is_audit_derived_q4 = True`)
* $\text{TTM}_t = \text{YTD}_t + \text{FY}_{t-1} - \text{YTD}_{t-4}$

### 2. Tiga Pilar Metrik Inti
* **Pilar 1: Intensitas Eksposur Kontrak PSAK 72:**
  $$\text{Gross Exposure} = \text{Piutang Usaha} + \text{Aset Kontrak (Lancar + Non-Lancar)}$$
  $$\text{Net Exposure} = \text{Gross Exposure} - \text{Liabilitas Kontrak (Uang Muka Proyek)}$$
  *Dilengkapi Revenue Contraction Guard jika pendapatan TTM $\le 0$ atau anjlok $> 50\%$ YoY.*
* **Pilar 2: Sloan Accrual Ratio (TTM):**
  $$\text{Sloan Ratio}_{\text{TTM}} = \frac{\text{Laba Bersih}_{\text{TTM}} - \text{CFO}_{\text{TTM}}}{(\text{Total Aset}_t + \text{Total Aset}_{t-4}) / 2}$$
  *Mendeteksi sinyal laba semu ketika rasio melampaui $+0.10$ (+10% dari total aset).*
* **Pilar 3: Cash-to-Short-Term Interest-Bearing Debt Coverage:**
  $$\text{Cash Coverage} = \frac{\text{Kas dan Setara Kas}}{\text{Utang Berbunga Jangka Pendek}}$$
  *Dilengkapi Debt-Free Guard untuk emiten bebas utang jangka pendek (seperti TOTL & ACST).*

### 3. Safeguard Flags
* **`FLAG_ACCRUAL_DIVERGENCE`:** Laba Bersih $> 0$, $\text{CFO}_{\text{TTM}} < 0$, $\text{CFO}_{Q} < 0$, dan $\text{Sloan Ratio} > 0.10$.
* **`FLAG_ACUTE_LIQUIDITY`:** $\text{CFO}_{\text{TTM}} < 0$, utang jangka pendek $> 0$, dan $\text{Cash Coverage} < 0.20\text{x}$.

---

## 🏢 Semesta Data Emiten (12 Emiten Konstruksi BEI)

| Kode | Nama Perusahaan | Profil Neraca Kas & Likuiditas |
| :---: | :--- | :--- |
| `TOTL` | Total Bangun Persada Tbk | 🟢 Bebas Utang JP, Arus Kas Operasi Mandiri |
| `ACST` | Acset Indonusa Tbk | 🟢 Bebas Utang JP, Struktur Modal Bersih |
| `PBSA` | Paramita Bangun Sarana Tbk | 🟢 Rasio Kas Sangat Kuat (> 200x) |
| `JKON` | Jaya Konstruksi Manggala Pratama Tbk | 🟢 Rasio Kas Kuat (> 13x) |
| `WEGE` | Wika Gedung Tbk | 🟢 Rasio Kas Solid (> 4x) |
| `NRCA` | Nusa Raya Cipta Tbk | 🟢 Rasio Kas Solid (> 2x) |
| `DGIK` | Nusa Konstruksi Enjiniring Tbk | 🟡 Rasio Kas Terkendali (~0.56x) |
| `ADHI` | Adhi Karya (Persero) Tbk | 🟡 Rasio Kas Terkendali (~0.55x) |
| `PTPP` | PP (Persero) Tbk | 🟡 Rasio Kas Terkendali (~0.51x) |
| `WIKA` | Wijaya Karya (Persero) Tbk | 🔴 Historis Tekanan Kas & Beban Utang Berbunga Tinggi |
| `WSKT` | Waskita Karya (Persero) Tbk | 🔴 Restrukturisasi Utang & Tekanan Likuiditas Akut |
| `PPRE` | PP Presisi Tbk | 🔴 Rasio Kas Sempit (< 0.20x) |

---

## 🤖 Antarmuka Perintah Bot Telegram (`aiogram 3.x`)

* `/check <KODE>` (atau ketik langsung kode saham, misal `TOTL`): Kartu diagnostik komprehensif, evaluasi metrik 3 pilar, audit trail data XBRL primer, dan ringkasan eksekutif AI.
* `/ticker`: Direktori lengkap 12 emiten konstruksi yang tercakup.
* `/top`: Klasemen solvabilitas kas & likuiditas seluruh industri (FY 2025).
* `/compare <K1> <K2>`: Komparasi *head-to-head* ketahanan kas dan profil utang (contoh: `/compare WIKA TOTL`).
* `/trend <KODE>`: Evolusi tren arus kas dan solvabilitas historis 4 tahun (2022–2025).
* `/calk <KODE>`: Rincian catatan kaki CALK (Pihak Berelasi vs Pihak Ketiga & CKPN) dengan verifikasi grounding verbatim.
* `/ask <PERTANYAAN>`: Asisten percakapan RAG menjawab pertanyaan finansial berbasis database dan metodologi akuntansi.
* `/help`: Panduan lengkap metodologi dan interpretasi rasio.

---

## 📁 Struktur Repositori

```text
idx-cash-radar/
├── pyproject.toml                   # Konfigurasi dependensi, ruff, & pytest
├── Dockerfile                       # Kontainerisasi produksi (Python 3.11-slim)
├── docker-compose.yml               # Supervisor orkestrasi container keep-alive
├── config/
│   └── taxonomy_mapping.yaml        # Kamus tag XBRL BEI cor/2020-01-01
├── data/
│   ├── raw_xbrl/                    # 48 berkas XBRL riil (12 emiten x 4 tahun)
│   └── calk_samples/                # Sampel catatan kaki laporan keuangan CALK
├── docs/
│   ├── PRD.md                       # Blueprint Product Requirements Document
│   ├── PRE_REGISTRATION.md          # Protokol uji hipotesis terkunci
│   ├── DEPLOYMENT.md                # Panduan deployment VPS cloud
│   └── adr/
│       ├── 001-psak72-window-and-ttm-buffer.md
│       ├── 002-xbrl-taxonomy-normalization.md
│       └── 003-calk-footnote-grounding-verifier.md
├── scripts/
│   ├── download_idx_filings.py      # Pengunduh otomatis berkas BEI (SHA-256 verified)
│   ├── ingest_filings.py            # CLI batch ingestion ke basis data SQLite
│   ├── run_case_evaluation.py       # Evaluasi retrospektif (Known Distress vs Control)
│   └── benchmark_latency.py         # Pengukur latensi kueri database (< 50 ms)
├── src/
│   ├── parser/
│   │   ├── xbrl_reader.py           # Parser lxml zero-dimension context filter
│   │   ├── normalizer.py            # Pemetaan taksonomi bursa ke skema kanonikal
│   │   ├── sanity_check.py          # 4-Way Sanity Check toleransi Rp 1.000.000
│   │   └── pdf_calk_reader.py       # Pembaca PDF & pelacak halaman catatan kaki CALK
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
│   ├── renderer/
│   │   ├── card_renderer.py         # Perender template Jinja2
│   │   ├── formatter.py             # Formatter angka & mata uang Indonesia
│   │   └── templates/               # Template kartu diagnostik Telegram
│   └── bot/
│       └── main.py                  # Entrypoint Bot Telegram aiogram 3.x (IPv4)
└── tests/                           # 87 automated unit & integration tests
```

---

## 🚀 Cara Menjalankan Proyek

### 1. Prasyarat Lingkungan
* Python 3.11 atau lebih baru
* Akun Bot Telegram via `@BotFather`
* (Opsional) Google Gemini API Key dari [Google AI Studio](https://aistudio.google.com/)

### 2. Instalasi Dependensi
```bash
git clone https://github.com/your-username/idx-cash-radar.git
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
Isi konfigurasi pada `.env`:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
```

### 4. Menjalankan Pengujian Otomatis (*Unit Tests*)
```bash
python -m pytest
```

### 5. Menjalankan Bot Telegram
```bash
python -m src.bot.main
```

### 6. Menjalankan via Docker (Produksi)
```bash
docker compose up -d --build
docker compose logs -f
```

---

## 📄 Lisensi & Kepatuhan Legal

Proyek ini dirilis di bawah lisensi terbuka [MIT License](LICENSE). Seluruh data laporan keuangan bersumber dari dokumen keterbukaan informasi publik Bursa Efek Indonesia (BEI) untuk tujuan edukasi, penelitian finansial, dan demonstrasi rekayasa sistem *zero-hallucination*. Proyek ini tidak memberikan rekomendasi investasi, nasihat keuangan, maupun target harga saham.
