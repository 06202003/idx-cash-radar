# AGENTS.md — System Contract & Execution Guardrails
**Project:** IDX Cash & Accrual Radar (v2.0 — Production Intelligence & Automated Radar Platform)  
**Lead Architect:** Yehezkiel David Setiawan, S.Kom., M.Kom.  
**Role:** Senior Data Engineer, Financial Systems Architect & Deterministic Implementation Agent  
**Target Environment:** Antigravity / Cursor / Windsurf / Local CLI / Cloud VPS Workspace

---

## 1. Core Engineering Principles (Non-Negotiables)

1. **Deterministic Math First (Zero-Hallucination Baseline):**  
   Semua operasi matematika, penyesuaian de-kumulasi YTD (*Year-to-Date*), kalkulasi rasio PSAK 72, *Sloan Accrual*, *Cash Coverage*, serta pemeringkatan kohort sub-industri **wajib** dikomputasi menggunakan Python deterministik (`Decimal`, `pandas`, `scipy`). Model bahasa (LLM) dilarang keras melakukan perhitungan aritmatika.
2. **Mandatory Audit Trail:**  
   Setiap metrik numerik yang ditampilkan ke pengguna wajib membawa metadata verifikasi dokumen primer BEI: nama tag XML XBRL (`localname` & `namespace`), `contextRef`, `unitRef`, `decimals`, serta nilai nominal mentah.
3. **Strict Separation of Deterministic Math & AI Narrative (LLM as Translator Only):**  
   Fitur kecerdasan buatan (LLM) hanya difungsikan sebagai *Narrative Translator* untuk menerjemahkan angka rasio teknis dan status *safeguard* yang sudah dihitung deterministik menjadi bahasa Indonesia yang ramah, santai, dan mudah dimengerti oleh investor ritel/awam. LLM tidak boleh menghasilkan skor risiko baru di luar kalkulasi Python.
4. **Contextual Isolation for Sentiment:**  
   Data sentimen berita atau keterbukaan informasi bursa diposisikan murni sebagai *konteks sekunder* dan dilarang mengubah, menimpa, atau mencemari evaluasi bendera bahaya kas (*Safeguard Flags*) deterministik.
5. **Execution Gate Enforcement:**  
   Pengerjaan wajib mengikuti tahapan gerbang (*Gate 0* sampai *Gate 8*). Agent dilarang melompat ke tahap berikutnya sebelum Gate sebelumnya lolos pengujian *unit test* dan verifikasi.

---

## 2. Scope Boundary & Feature Roadmap

### 2.1 Lingkup Fondasi MVP (v1.2 — Selesai & Teruji)
- **Universe Data:** Sub-Industri Konstruksi Bangunan & Rekayasa Sipil (3 emiten percontohan: `ADHI`, `PTPP`, `WIKA` FY 2023).
- **Jendela Waktu:** Laporan keuangan 2020–2025 (rezim PSAK 72).
- **Pipeline Data:** Parser `lxml`, normalisasi taksonomi bursa, modul de-kumulasi YTD, 3 metrik kuantitatif, dan basis data `sqlite3`.
- **Antarmuka:** Bot Telegram (`aiogram 3.x`) berbasis Jinja2 template dan koneksi IPv4 stabil.

### 2.2 Lingkup Evolusi Produk (v2.0 — Platform Penuh)
- **Gate 5 (Automated IDX Pipeline):** Skrip pengunduh otomatis berkas XBRL dari portal/API resmi BEI untuk seluruh emiten sub-industri konstruksi (2020–2025), memperluas kohort hingga $N \ge 8$ (mengaktifkan peringkat eksak dan kuartil Q1–Q4).
- **Gate 6 (AI Executive Narrative Explainer):** Integrasi Google Gemini API (`google-genai`) untuk menghasilkan ringkasan naratif ramah manusia pada kartu diagnostik bot, dengan mekanisme *fallback* ke template murni jika kuota/koneksi offline.
- **Gate 7 (Contextual News & Disclosure Sentiment Radar):** Modul ekstraksi berita dan keterbukaan informasi emiten dari portal resmi/RSS media keuangan terkurasi, diklasifikasikan ke dalam 3 status sentimen (🟢 Positif, 🟡 Netral, 🔴 Perhatian).
- **Gate 8 (Production Deployment & Daemonization):** Konfigurasi *containerization* (`Dockerfile`, `docker-compose.yml`) dan *process supervisor* agar bot aktif 24/7 di server cloud/VPS.

### 2.3 Batasan Scope Creep (Tetap Dilarang)
- ❌ Rekomendasi Beli/Jual saham atau target harga (*price target*).
- ❌ Prediksi pergerakan harga saham berbasis *technical analysis* / *charting*.
- ❌ Model *unsupervised ML* berbasis *black-box* (misal: *Isolation Forest* acak) atau skor komposit 0–100 semu.

---

## 3. Approved Tech Stack & Licensing Rules

Hanya gunakan pustaka *open-source* dengan lisensi permisif (MIT, BSD, Apache 2.0, PSF, Public Domain):

| Komponen | Pustaka Terpilih | Lisensi | Batasan Penggunaan |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python 3.11+ | PSF | Gunakan `Decimal` atau representasi integer penuh untuk aritmatika akuntansi. |
| **XBRL XML Parser** | `lxml` | BSD | Dilarang menginstal atau mengimpor `Arelle`. |
| **Validasi & Skema** | `pydantic >= 2.0` | MIT | Validasi bentuk data, kontrak kanonikal, dan output JSON. |
| **Komputasi & Data** | `pandas`, `numpy`, `scipy` | BSD-3-Clause | De-kumulasi kuartalan, perhitungan TTM, dan statistik kohort. |
| **Database** | `sqlite3` | Public Domain | Tersemat langsung, kueri deterministik berindeks. |
| **Narrative Engine** | `jinja2` | BSD-3-Clause | Rendering kartu laporan dasar tanpa halusinasi. |
| **Bot Framework** | `aiogram >= 3.4` | MIT | Menangani bot Telegram polling non-blocking via IPv4. |
| **AI Narrative** | `google-genai` / Gemini API | Apache 2.0 | Penerjemahan teks metrik ke bahasa manusia (dilarang hitung matematika). |
| **News Ingestion** | `aiohttp`, `feedparser` / `bs4` | MIT / BSD | Ekstraksi judul berita bursa & keterbukaan informasi resmi. |
| **Testing & Linting** | `pytest`, `pytest-cov`, `ruff` | MIT | Seluruh baris kode wajib lolos `ruff check` dan tes otomatis. |

---

## 4. Repository Structure & Naming Conventions

```text
idx-cash-radar/
├── AGENTS.md
├── pyproject.toml
├── README.md
├── .env.example
├── config/
│   └── taxonomy_mapping.yaml        # Kamus tag XBRL BEI hasil Spike
├── docs/
│   ├── PRD.md                       # Blueprint PRD
│   ├── PRE_REGISTRATION.md          # Ambang batas & protokol uji terkunci
│   └── adr/
│       ├── 001-psak72-window-and-ttm-buffer.md
│       └── 002-xbrl-taxonomy-normalization.md
├── scripts/
│   ├── spike_xbrl_audit.py          # Skrip inspeksi berkas XBRL (Gate 0)
│   ├── ingest_filings.py            # CLI ekstraksi & penyimpanan ke SQLite (Gate 1)
│   ├── run_case_evaluation.py       # CLI evaluasi retrospektif 2020-2025 (Gate 2)
│   ├── benchmark_latency.py         # Pengukur latensi kueri SQLite (Gate 4)
│   └── download_idx_filings.py      # Otomasi pengunduhan laporan dari BEI (Gate 5)
├── src/
│   ├── __init__.py
│   ├── models/
│   │   ├── canonical.py             # Skema Pydantic pos keuangan kanonikal
│   │   └── metrics.py               # Skema Pydantic hasil rasio, flag & AI narrative
│   ├── parser/
│   │   ├── xbrl_reader.py           # Ekstraktor elemen, unit, dan context lxml
│   │   ├── normalizer.py            # Pemetaan tag bursa ke skema kanonikal
│   │   └── sanity_check.py          # Validator rekonsiliasi 4-Way Sanity Check
│   ├── engine/
│   │   ├── decumulator.py           # Logika konversi YTD -> Standalone Q & TTM
│   │   ├── calculator.py            # Kalkulasi 3 metrik inti & zero-denominator guard
│   │   ├── cohort.py                # Peringkat eksak, kuartil, dan median N-kecil
│   │   ├── safeguards.py            # Evaluasi boolean FLAG_ACCRUAL & FLAG_LIQUIDITY
│   │   ├── llm_explainer.py         # Narator bahasa manusiawi berbasis Gemini (Gate 6)
│   │   └── news_radar.py            # Pemindai berita & keterbukaan informasi (Gate 7)
│   ├── db/
│   │   ├── schema.sql               # DDL tabel SQLite3
│   │   └── repository.py            # Akses kueri deterministik
│   ├── renderer/
│   │   ├── templates/
│   │   │   ├── card_construction.j2 # Template kartu sektor konstruksi
│   │   │   └── card_empty_state.j2  # Template informasi luar cakupan
│   │   ├── card_renderer.py         # Perender Jinja2
│   │   └── formatter.py             # Format desimal/ribuan Indonesia
│   └── bot/
│       └── main.py                  # Entrypoint Bot Telegram aiogram
└── tests/
    ├── test_xbrl_reader.py
    ├── test_sanity_check.py
    ├── test_decumulator.py
    ├── test_calculator_guards.py
    ├── test_safeguards.py
    ├── test_renderer.py
    ├── test_bot_handlers.py
    ├── test_language_compliance.py
    ├── test_llm_explainer.py        # Pengujian AI narrative & fallback (Gate 6)
    └── test_news_radar.py            # Pengujian parser berita & isolasi konteks (Gate 7)
```

---

## 5. Mathematical & Financial Accounting Specifications (Locked)

### 5.1 De-kumulasi Kuartal Tunggal & Perhitungan TTM
- $Q_1 = \text{YTD}_{3M}$
- $Q_2 = \text{YTD}_{6M} - \text{YTD}_{3M}$
- $Q_3 = \text{YTD}_{9M} - \text{YTD}_{6M}$
- $Q_4 = \text{YTD}_{12M} - \text{YTD}_{9M}$ (Diberi flag `is_audit_derived_q4 = True`)
- $\text{TTM}_t = \sum_{i=0}^{3} \text{Kuartal\_Tunggal}_{t-i} = \text{YTD}_t + \text{FY}_{t-1} - \text{YTD}_{t-4}$

### 5.2 Metrik 1: Intensitas Eksposur Kontrak PSAK 72
- $\text{Gross Exposure}_t = \text{Piutang Usaha}_t + \text{Aset Kontrak (Lancar + Non-Lancar)}_t$
- $\text{Net Exposure}_t = \text{Gross Exposure}_t - \text{Liabilitas Kontrak (Uang Muka Proyek)}_t$
- **Revenue Contraction Guard:** Jika $\text{Pendapatan}_{\text{TTM}, t} \le 0$ atau kontraksi $> 50\%$ YoY, rasio dinonaktifkan (`revenue_contraction_guard = True`).

### 5.3 Metrik 2: Sloan Accrual Ratio (TTM)
$$\text{Sloan Ratio}_{\text{TTM}, t} = \frac{\text{Laba Bersih}_{\text{TTM}, t} - \text{CFO}_{\text{TTM}, t}}{(\text{Total Aset}_t + \text{Total Aset}_{t-4}) / 2}$$

### 5.4 Metrik 3: Cash-to-Short-Term Interest-Bearing Debt Coverage
$$\text{Cash Coverage}_t = \frac{\text{Kas dan Setara Kas}_t}{\text{Utang Berbunga Jangka Pendek}_t}$$
- **Debt-Free Guard:** Jika utang jangka pendek $== 0$, tetapkan `debt_free_short_term = True` dan `cash_coverage = None`.

### 5.5 Safeguards Boolean Evaluator
```python
# 1. Jalur Anomali Akrual (Laba Semu pada Emiten Untung)
flag_accrual_divergence = bool(
    net_income_ttm > 0
    and cfo_ttm < 0
    and cfo_single_q < 0
    and sloan_ratio_ttm > Decimal("0.10")
)

# 2. Jalur Tekanan Likuiditas (Berlaku untuk Emiten Untung maupun Rugi)
flag_acute_liquidity = bool(
    cfo_ttm < 0
    and not debt_free_short_term
    and st_debt > 0
    and cash_coverage < Decimal("0.20")
)
```

---

## 6. AI Executive Narrative & News Intelligence Rules (v2.0)

### 6.1 Kontrak Prompt AI Explainer (Gate 6)
AI bertindak secara eksklusif sebagai penerjemah data deterministik. Aturan sistem prompt:
1. **Dilarang Menghitung:** Dilarang melakukan operasi aritmatika atau mengubah nilai metrik dari Python.
2. **Bahasa Manusiawi Ritel:** Gunakan analogi bisnis yang sederhana dan santai (misal: "kas operasional tertekan", "uang tertahan di tagihan proyek", "daya tutup utang sempit").
3. **Maksimal 3 Kalimat:** Penjelasan harus padat, tajam, dan tidak bertele-tele.
4. **Fallback Aman:** Jika panggilan API AI gagal (*network timeout*, kuota habis, atau API key kosong), bot wajib tetap mengirim kartu Jinja2 deterministik tanpa error.

### 6.2 Kontrak Radar Sentimen Berita (Gate 7)
1. **Sumber Faktual:** Hanya membaca keterbukaan informasi resmi BEI dan media ekonomi kredibel.
2. **Isolasi Konteks:** Kategori sentimen (Positif, Netral, Perhatian) hanya ditampilkan pada blok tersendiri:
   ```text
   📰 SENTIMEN BERITA & KETERBUKAAN BEI
   • 28 Des 2023 [PERHATIAN]: Pengumuman Penundaan Pembayaran Kupon Sukuk Mudharabah
   • 15 Des 2023 [NETRAL]   : Laporan Hasil Public Expose Tahunan 2023
   ```
3. **Imunitas Flag Kas:** Berita positif sebesar apa pun (misal: "Memenangkan Kontrak Rp 5 Triliun") **tidak boleh** membatalkan atau menurunkan bendera `FLAG_ACUTE_LIQUIDITY` jika rasio kas riil tetap kritis.

---

## 7. Language Linter & Legal Compliance Rules (Strictly Enforced)

Setiap output kartu bot, teks buatan AI, pesan bantuan, dan berkas dokumentasi wajib mematuhi aturan bahasa deskriptif:

- **Daftar Kata Terlarang (Blacklist):**  
  `"Manipulasi"`, `"Window Dressing"`, `"Laporan Palsu"`, `"Saham Gorengan"`, `"Penipuan"`, `"Fraud"`, `"Bangkrut"`, `"Rekayasa Laba"`, `"Rekomendasi Beli"`, `"Rekomendasi Jual"`.
- **Pengganti Deskriptif:**  
  Gunakan *"Divergensi akrual berada di kuartil tertinggi"*, *"Arus kas operasi bernilai negatif selama minimal 2 periode berurutan"*, atau *"Kapasitas kas menutup kurang dari 20% utang jangka pendek berbunga"*.
- **Pemeriksaan Otomatis:** Repositori wajib memuat pengujian `tests/test_language_compliance.py` yang memindai seluruh template antarmuka, prompt AI, dan respon sistem dari kata-kata terlarang tersebut.

---

## 8. Gate-by-Gate Execution Protocol (Gate 0 s/d Gate 8)

```text
[Gate 0: Spike] ✅ ──> [Gate 1: Ingest] ✅ ──> [Gate 2: Engine] ✅ ──> [Gate 3: Bot] ✅ ──> [Gate 4: QA & Release] ✅
                                                                                                        │
    ┌───────────────────────────────────────────────────────────────────────────────────────────────────┘
    ▼
[Gate 5: Automated IDX Scraper] ✅ ──> [Gate 6: AI Narrative Explainer] ✅ ──> [Gate 7: News Sentiment] ✅ ──> [Gate 8: Production Scaling] ✅
```

### Tahap 1: Fondasi Inti Deterministik (MVP v1.2 — Selesai & Teruji)
- **GATE 0 (Taxonomy Spike) — COMPLETED:** Audit berkas XBRL riil (`ADHI`, `PTPP`, `WIKA`), pemetaan tag taksonomi `cor/2020-01-01`, dan filter konteks nol-dimensi.
- **GATE 1 (Ingestion & Normalizer) — COMPLETED:** Parser `lxml`, 4-Way Sanity Check toleransi $\text{Rp } 0$, de-kumulasi YTD/TTM, dan skema basis data SQLite3.
- **GATE 2 (Engine & Case Matrix) — COMPLETED:** 3 metrik inti, evaluasi *safeguard flags*, dan verifikasi matriks retrospektif (WIKA terdeteksi distres likuiditas, ADHI & PTPP normal).
- **GATE 3 (Telegram Bot & UI Presentation) — COMPLETED:** Template Jinja2, antarmuka bot `aiogram 3.x` non-blocking dengan penanganan IPv4 stabil.
- **GATE 4 (QA, Latency Benchmark & ADR) — COMPLETED:** 38 unit tests (100% pass), code coverage 90%, latensi kueri rata-rata **3.51 ms** ($< 50\text{ ms}$), rilis ADR 002.

### Tahap 2: Platform Inteligensi & Otomasi (v2.0 — Selesai & Teruji)
- **GATE 5 — Automated IDX Pipeline & Universe Expansion — COMPLETED:**  
  Membangun `scripts/download_idx_filings.py` yang mendukung 8 emiten konstruksi inti (`ADHI`, `PTPP`, `WIKA`, `WSKT`, `TOTL`, `NRCA`, `JKON`, `ACST`) dengan verifikasi integritas hash SHA-256 (`data/download_manifest.json`), corrupt zip guard, dan mode batch import `--import-dir` serta automated ingestion batch `scripts/ingest_filings.py --batch`.
- **GATE 6 — AI Executive Narrative Explainer (Gemini Layer) — COMPLETED:**  
  Mengintegrasikan `src/engine/llm_explainer.py` menggunakan Gemini API SDK (`google-genai`). Menghasilkan ringkasan 2–3 kalimat bahasa manusiawi pada respon bot Telegram, lengkap dengan deterministic fallback dan guardrails kepatuhan hukum non-tuduhan.
- **GATE 7 — Contextual News & Disclosure Sentiment Radar — COMPLETED:**  
  Membangun `src/engine/news_radar.py` untuk mengekstraksi keterbukaan informasi dan mengklasifikasikan sentimen secara deterministik (🟢 POSITIF, 🟡 NETRAL, 🔴 PERHATIAN). Isolasi konteks terjamin 100% lewat pengujian `tests/test_news_radar.py` (berita positif tidak dapat membatalkan `FLAG_ACUTE_LIQUIDITY`).
- **GATE 8 — Production Deployment, Containerization & Keep-Alive — COMPLETED:**  
  Menyediakan `Dockerfile` (Python 3.11-slim non-root user), `docker-compose.yml`, `.dockerignore`, dan panduan lengkap `docs/DEPLOYMENT.md` untuk menjalankan bot 24/7 di server VPS/cloud dengan health-check dan keep-alive.
