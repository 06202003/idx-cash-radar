# **PRODUCT REQUIREMENTS DOCUMENT (PRD)**

# **IDX Cash & Accrual Radar**

**Subjudul:** Audit-Ready XBRL Financial Data Pipeline & Deterministic Liquidity Profiling

* **Penyusun:** Yehezkiel David Setiawan, S.Kom., M.Kom.  
* **Status Dokumen:** v1.2 \- Working Draft (Pre-Spike Scope Freeze)  
* **Tanggal:** 11 November 2026  
* **Sifat Proyek:** Non-Komersial / Open-Source Engineering Portfolio & Research POC

---

# **1\. Executive Summary & Ruang Lingkup MVP**

**IDX Cash & Accrual Radar** adalah *proof-of-concept* (POC) rekayasa data (*data engineering*) yang mengekstraksi, menormalisasi, dan memprofilkan kualitas arus kas serta eksposur akrual emiten di Bursa Efek Indonesia (BEI) secara deterministik.

Proyek ini menjawab masalah klasik laporan keuangan sektor konstruksi: emiten membukukan laba bersih positif di atas kertas melalui pengakuan pendapatan progres proyek, sementara arus kas operasionalnya mengalami defisit berkepanjangan akibat penumpukan piutang dan aset kontrak yang belum tertagih.

Untuk memastikan proyek selesai dengan kualitas produksi oleh satu *engineer* dalam 4 minggu, ruang lingkup **MVP (v1.x)** dibekukan secara ketat pada:

1. **Satu Sumber Data Utama:** Berkas resmi `instance.xbrl` (dan laporan PDF pendamping untuk verifikasi baris) dari portal BEI mulai periode efektif PSAK 72 (2020–2025).  
2. **Satu Sub-Industri:** Konstruksi Bangunan & Kontraktor Rekayasa Proyek (IDX-IC Sub-Industry).  
3. **Mesin Deterministik Murni (Tier 1):** De-kumulasi arus kas YTD, normalisasi taksonomi XBRL dengan `lxml`, perhitungan 3 metrik likuiditas/akrual beserta *Peer-Percentile*, *Small-N Guard*, dan *Sustained Cash Safeguard*, serta *audit trail* ke tag XBRL asli.  
4. **Satu Antarmuka & Satu Database:** Bot Telegram (`aiogram`) di atas `SQLite3` dengan perender narasi deterministik `Jinja2`.  
5. **Satu Eksperimen Terbatas LLM (Stretch Goal):** Ekstraksi satu catatan kaki spesifik (porsi piutang/aset kontrak pihak berelasi dari PDF CALK) yang divalidasi oleh **Deterministic Verbatim Grounding Verifier** (memastikan setiap angka output ditemukan secara eksak di teks sumber halaman PDF).

Seluruh fitur tambahan (Web Dashboard Next.js/PWA, ekstraksi prospektus Penggunaan Dana IPO, dan mode LLM lokal Ollama) dipindahkan ke **Bagian 10 (Backlog Phase 2\)** dan tidak dikerjakan sebelum MVP selesai divalidasi.

# **2\. Latar Belakang Masalah & Fokus Portofolio**

* # **2.1 Masalah Teknis yang Diselesaikan**

* **Inkonsistensi Struktur Laporan Keuangan Publik:** Berkas XBRL BEI memiliki variasi penggunaan elemen taksonomi antar-emiten dan perubahan standar akuntansi lintas tahun (transisi PSAK 34 ke PSAK 72 pada tahun 2020).  
* **Distorsi Angka Kumulatif (YTD):** Laporan Laba Rugi dan Arus Kas kuartalan di BEI disajikan secara kumulatif dari awal tahun (*Year-to-Date*: 3M, 6M, 9M, 12M), sehingga analisis tren antar-kuartal tanpa proses de-kumulasi akan menghasilkan kesimpulan yang keliru.  
* **Keterbatasan LLM Murni pada Dokumen Keuangan:** Model bahasa generatif rentan salah membaca tabel tanpa garis, salah mengonversi format desimal Indonesia (`1.234,56` atau `(1.234)` untuk angka negatif), dan tidak dapat menjamin kebenaran aritmatika.

# **2.2 Nilai Jual Rekayasa (Engineering Value Proposition)**

Sebagai portofolio teknis, proyek ini mendemonstrasikan:

* **Deterministic Data Pipeline:** Kemampuan memproses dokumen regulasi XML/XBRL yang tidak seragam menjadi skema relasional yang tervalidasi persamaan akuntansinya.  
* **Domain-Aware Financial Modeling:** Penanganan khusus terhadap akuntansi kontrak konstruksi (PSAK 72), uang muka proyek (*contract liabilities*), dan de-kumulasi periode laporan.  
* **Post-LLM Verbatim Grounding Check:** Pemahaman bahwa validasi tipe data (`Pydantic`) hanya mengunci struktur JSON, sehingga diperlukan algoritma verifikasi pencocokan teks/angka pasca-ekstraksi untuk mendeteksi halusinasi angka pada dokumen PDF.

# **3\. Keputusan Arsitektur: Apa yang Sengaja TIDAK Dibuat (Trade-Offs)**

* **Tidak Menggunakan Skor Tunggal (0–100):** Menghindari presisi semu (*pseudo-precision*) dan bobot subjektif; setiap pilar metrik ditampilkan terpisah.  
* **Tidak Menggunakan Model Unsupervised ML (Isolation Forest):** Populasi sub-industri konstruksi di BEI terlalu kecil (N ≈ 15--25 emiten) untuk pelatihan ML tanpa *overfitting*. Statistik persentil empiris dan median lebih transparan.  
* **Tidak Mengekstrak Klaim Berita Bebas (Free-Text News Scraper):** Mengekstrak angka dari berita media massa memiliki risiko salah baca yang tinggi dan melanggar prinsip keandalan data primer.  
* **Tidak Melakukan Audit Prospektus Pra-IPO di MVP:** Calon emiten IPO hanya memiliki laporan tahunan di PDF (tanpa XBRL kuartalan dan tanpa *peer group* sebanding), serta membawa risiko hukum tinggi jika dipublikasikan saat masa penawaran umum berlangsung.

# **4\. Metodologi Kuantitatif & Penanganan Edge-Cases (Tier 1\)**

# **4.1 Batas Waktu Data & Regim PSAK 72 (2020–2025)**

* PSAK 72 (*Pendapatan dari Kontrak dengan Pelanggan*) berlaku efektif 1 Januari 2020, menggantikan PSAK 34 (*Kontrak Konstruksi*).  
* Untuk menjaga konsistensi definisi pos `Aset Kontrak` dan `Liabilitas Kontrak`, *backtest* dan *pipeline* utama dikunci pada periode **Q1 2020 hingga Q4 2025**. Jika data pra-2020 disertakan dalam studi kasus, pos `Tagihan Bruto kepada Pemberi Kerja` (PSAK 34\) dipetakan secara eksplisit dengan penanda *Pre-PSAK 72 Regime*.

# **4.2 De-kumulasi YTD & Kalkulasi Trailing Twelve Months (TTM)**

Karena laporan Q1 (3M), Q2 (6M), Q3 (9M), dan Q4 (12M) di BEI bersifat kumulatif sejak 1 Januari:

1. **De-kumulasi Kuartal Tunggal (Standalone Quarter):**  
   1. `Q1 = YTD_3M`  
   2. `Q2 = YTD_6M - YTD_3M`  
   3. `Q3 = YTD_9M - YTD_6M`  
   4. `Q4 = YTD_12M - YTD_9M`  
2. **Trailing Twelve Months (TTM):** Dihitung dari penjumlahan 4 kuartal tunggal berurutan terakhir atau menggunakan rumus `YTD_Current + FY_Prev - YTD_PrevYearSameQuarter` untuk meredam musiman (*seasonality*) pencairan termin proyek di akhir tahun (Q4).

   * # **4.3 Tiga Metrik Inti & Penanganan Penyebut Nol (Zero-Denominator Safe)**

   **Intensitas Modal Kerja Kontrak Bersih terhadap Pendapatan (PSAK 72 Net Contract Intensity):**

     **Masalah Rasio Pertumbuhan Biasa:** Membagi ΔEksposur dengan ΔPendapatan akan meledak (*division by zero* / distorsi ekstrem) ketika pertumbuhan pendapatan mendekati 0% atau negatif.

     **Formula Baru yang Stabil:** Mengukur perubahan rasio intensitas eksposur terhadap pendapatan TTM dalam satuan **poin persentase (percentage points / bps)** YoY:

     `Gross Contract Exposure Ratio_t = (Piutang Usaha_t + Aset Kontrak_t) / Pendapatan TTM_t`

     `Net Contract Exposure Ratio_t = ((Piutang Usaha_t + Aset Kontrak_t) - Liabilitas Kontrak_t) / Pendapatan TTM_t`

     `Divergence_YoY = (Gross Exposure Ratio_t - Gross Exposure Ratio_{t-4}) dalam poin persentase`

     **Peran Liabilitas Kontrak (Uang Muka Pelanggan):** Sistem menampilkan baik eksposur bruto maupun neto (setelah dikurangi uang muka proyek/`Liabilitas Kontrak`) agar terlihat apakah proyek didanai uang muka pemberi kerja atau murni menguras modal kerja kontraktor.

     **Guard Penyebut:** Jika `Pendapatan TTM_t <= 0` atau turun \> 50% YoY, rasio tidak dihitung dalam persentil dan langsung diberi bendera *Revenue Contraction Guard*.

   **Sloan Accrual Ratio (Berbasis TTM):**

     **Formula:**

     `Sloan Ratio_TTM = (Laba Bersih_TTM - CFO_TTM) / Rata-rata Total Aset_(t, t-4)`

     **Rasional:** Mengukur proporsi laba 12 bulan terakhir yang tidak didukung kas operasi.

   **Cash-to-Short-Term Interest-Bearing Debt Coverage:**

     **Formula:**

     `Cash Coverage_t = Kas dan Setara Kas_t / Total Liabilitas Jangka Pendek Berbunga_t`

     **Komponen Penyebut Eksplisit:** Penjumlahan dari (a) Utang Bank Jangka Pendek, (b) Bagian Lancar Utang Bank Jangka Panjang, (c) Bagian Lancar Obligasi/Sukuk/MTN, dan (d) Liabilitas Sewa Jangka Pendek. **Tidak termasuk** Utang Usaha kepada pemasok (*Trade Payables*) dan Beban Akrual.

     **Guard Penyebut:** Jika emiten memiliki utang berbunga jangka pendek \= 0, metrik ditandai `Debt-Free Short-Term` (tidak terjadi pembagian dengan nol).

# **4.4 Small-N Guard & Sustained Cash Safeguard (Anti Alert-Fatigue)**

1. **Small-N Statistical Guard:** Persentil sub-industri hanya ditampilkan jika terdapat minimal N ≥ 8 emiten konstruksi dengan laporan lengkap pada kuartal tersebut. Jika N \< 8, sistem hanya menampilkan **Angka Emiten vs. Median Sub-Industri**.  
2. **Sustained Cash Safeguard (Menggantikan Aturan 1-Kuartal yang Terlalu Sensitif):** Karena kontraktor wajar mengalami arus kas negatif pada Q1–Q3 dan baru menerima pencairan termin di Q4, bendera perhatian mutlak hanya menyala jika memenuhi syarat kumulatif:  
   * `CFO_TTM < 0` selama **minimal 2 periode laporan berturut-turut** sementara `Laba Bersih_TTM > 0`, **DAN**  
   * `Sloan Accrual Ratio_TTM > +0.10` (akrual melampaui 10% total aset), **ATAU**  
   * `Cash Coverage < 0.20x` disertai `CFO_TTM < 0`.  
3. **Penanda Status Audit:** Laporan Q1, Q2, dan Q3 diberi label tegas `UNAUDITED` (tidak diaudit), sedangkan laporan tahunan FY diberi label `AUDITED`.

# **5\. Arsitektur Narasi & Stretch Goal Ekstraksi CALK (Tier 2\)**

# **5.1 Jalur Utama MVP: Deterministic Jinja2 Template Engine**

* Pada MVP, 100% narasi kartu diagnostik di Bot Telegram dirender menggunakan template deterministik `Jinja2` langsung dari tabel `SQLite`.  
* Pendekatan ini menjamin konsistensi output, waktu respons cepat, nol biaya API, dan bebas dari kesalahan interpretasi LLM.

# **5.2 Stretch Goal: Narrow CALK Footnote Extractor \+ Verbatim Grounding Verifier**

Jika Fase Minggu 1–3 selesai tepat waktu, satu fitur ekstraksi LLM sempit akan ditambahkan dengan batasan ketat:

1. **Cakupan Sempit:** Hanya mengekstrak **satu catatan kaki** (Catatan Piutang Usaha & Aset Kontrak) untuk mengambil rincian porsi Pihak Berelasi vs Pihak Ketiga serta nilai cadangan kerugian penurunan nilai (CKPN).  
2. **Koreksi Klaim Keamanan (Pydantic vs. Grounding Verifier):**  
   * `Pydantic v2` **hanya** digunakan untuk memvalidasi tipe data dan struktur skema JSON, bukan mencegah halusinasi nilai angka.  
   * Pencegahan halusinasi dilakukan oleh modul **Deterministic Verbatim Grounding Verifier** pasca-LLM:  
     * Menormalisasi format angka Indonesia pada teks PDF sumber (menghapus titik ribuan, mengubah koma desimal, mengubah `(1.234)` menjadi `-1234`).  
     * Memeriksa apakah setiap angka yang diekstrak LLM benar-benar muncul secara verbatim di halaman catatan kaki PDF yang dirujuk.  
     * Jika angka tidak ditemukan di teks sumber, ekstraksi LLM **ditolak otomatis (rejected)** dan sistem kembali menampilkan tautan halaman PDF secara manual.  
3. **Evaluasi Akurasi:** Diuji pada 20–30 halaman laporan nyata dan didokumentasikan tingkat keberhasilan ekstraksinya di dalam *Architecture Decision Record (ADR)*.

# **6\. Spesifikasi Antarmuka Bot Telegram (MVP)**

# **6.1 Kartu Diagnostik Emiten (/cek \<TICKER\>)**

Menampilkan:

* **Header & Status Audit:** Nama emiten, periode laporan, label `AUDITED` / `UNAUDITED`, dan jumlah pembanding (N emiten).  
* **3 Pilar Metrik (Angka Emiten, Median Industri, Persentil):**  
  * Intensitas Eksposur Kontrak Bruto & Neto terhadap Pendapatan TTM (+ perubahan poin persentase YoY).  
  * Sloan Accrual Ratio TTM.  
  * Cash-to-Short-Term Interest-Bearing Debt Coverage.  
* **Audit Trail Mandatori:** Nama elemen tag XBRL, konteks periode XML, dan nilai mentah langsung dari `instance.xbrl`.

# **6.2 Penanganan Saham Luar Cakupan (Empty State)**

Jika pengguna mengetik saham non-konstruksi (misal: `/cek BBCA`):

1. Menampilkan penjelasan singkat mengapa metrik konstruksi PSAK 72 tidak berlaku.  
2. Mencatat kueri ticker ke tabel `demand_log` di SQLite.  
3. (Opsional) Menampilkan data kas dasar dengan label tegas: *"Sumber: Yahoo Finance (tidak terverifikasi XBRL BEI, hanya untuk demonstrasi non-komersial)"*.

# **7\. Arsitektur Teknis & Sumber Data (100% Open Source & Simpel)**

* # **7.1 Tech Stack MVP yang Dipangkas**

* **Runtime:** Python 3.11+ (PSF License).  
* **XBRL Parser:** `lxml` (BSD License) — mem-parsing `instance.xbrl` secara langsung berdasarkan namespace dan contextRef tanpa beban dependensi `Arelle`.  
* **Data Validation & Math:** `Pydantic v2` (MIT) untuk validasi skema & persamaan akuntansi (Aset \= Liabilitas \+ Ekuitas), serta `Pandas` / `SciPy` (BSD-3-Clause) untuk de-kumulasi YTD dan perhitungan persentil.  
* **Database Tunggal:** `SQLite3` (Public Domain) — tanpa server database eksternal untuk kemudahan reproduksi portofolio.  
* **Narrative Renderer:** `Jinja2` (BSD-3-Clause).  
* **Bot Interface:** `aiogram 3.x` (MIT).  
* **PDF Extractor (Khusus Stretch Goal):** `pdfplumber` / `pypdfium2` (MIT / Apache 2.0) \+ `google-genai` SDK dengan *Verbatim Grounding Verifier*.  
* **Testing & Linting:** `pytest` & `Ruff` (MIT).

# **7.2 Sumber Data Publik (Non-Komersial)**

* **Berkas XBRL & PDF Laporan Keuangan:** Diunduh dari portal keterbukaan BEI (`idx.co.id`) untuk emiten sub-industri konstruksi periode 2020–2025.  
* **Klasifikasi Sub-Industri:** Daftar Saham IDX-IC (Sektor Infrastruktur / Industri \- Sub-industri Konstruksi Bangunan).  
* **Data Kasus Historis:** Pengumuman resmi suspensi, restatement, dan notasi khusus BEI/OJK pada periode 2020–2025.

# **8\. Metodologi Evaluasi Studi Kasus (Pengganti Klaim Statistik N-Kecil)**

Mengingat jumlah emiten konstruksi di BEI terbatas (\~18–25 emiten) dan jumlah kasus gagal bayar/restatement terdokumentasi pada periode 2020–2025 hanya berkisar 3–8 emiten, penggunaan ambang batas persentase statistik (seperti "Recall 70%") tidak bermakna secara statistik.

# **8.1 Evaluasi Kualitatif Berbasis Matriks Kasus (2020–2025)**

Evaluasi disajikan secara transparan sebagai **Studi Kasus Retrospektif** yang mendokumentasikan seluruh populasi emiten konstruksi dalam tiga kelompok:

3. **Known Distress / Restatement Cases (True Positives & False Negatives):** Untuk setiap emiten konstruksi yang mengalami suspensi gagal bayar utang atau penyajikan kembali laporan keuangan (2020–2025), sistem mencatat pada kuartal ke berapa sebelum kejadian (*Lead Time in Quarters*) indikator *Sustained Cash Safeguard* atau persentil ekstrem mulai menyala, atau mencatat kegagalan deteksi jika indikator tidak menyala.  
4. **Flagged Non-Distress Cases (False Alarms Inspection):** Setiap emiten sehat yang menyalakan indikator dianalisis penyebab akuntansinya secara transparan (misal: ekspansi proyek baru yang didanai ekuitas).  
5. **External Review:** Sebelum studi kasus dipublikasikan di repositori, pemetaan akun XBRL dan rumus de-kumulasi ditinjau minimal oleh 1 rekan praktisi akuntansi/auditor untuk memverifikasi ketepatan komponen akun.

# **8.2 Kriteria Keberhasilan Teknis & Pivot (Honest Engineering Criteria)**

* **Kriteria Validitas Parser:** 100% berkas `instance.xbrl` pada sampel uji lulus pengecekan otomatis persamaan neraca (Aset \= Liabilitas \+ Ekuitas) dan rekonsiliasi saldo kas.  
* **Kriteria Pivot Metodologi:** Jika setelah de-kumulasi YTD dan penyesuaian PSAK 72 metrik tidak menunjukkan perbedaan pola antara emiten yang gagal bayar (seperti kasus BUMN Karya 2020–2024) dan emiten konstruksi yang sehat, maka proyek diposisikan murni sebagai **Open-Source IDX XBRL Parser & Cash Flow Visualizer** tanpa klaim deteksi anomali.

  * # **9\. Kepatuhan Hukum & Lisensi**

2. **Bahasa Deskriptif Murni:** Seluruh teks menggunakan pernyataan matematis deskriptif (*"Rasio kas terhadap utang berbunga jangka pendek sebesar 0,14x, berada di bawah median sub-industri 0,62x"*). Dilarang menggunakan istilah tuduhan seperti *"Manipulasi"*, *"Window Dressing"*, *"Laporan Palsu"*, atau *"Saham Gorengan"*.  
3. **Fakta Regulasi Resmi:** Penyebutan nama emiten pada dokumentasi studi kasus hanya merujuk pada pengumuman resmi BEI/OJK yang telah dipublikasikan, disertai nomor surat pengumuman bursa.  
4. **Disclaimer Non-Komersial:** Repositori mencantumkan bahwa perangkat lunak dan sampel data hanya digunakan untuk demonstrasi rekayasa sistem, bukan layanan komersial atau nasihat investasi.

# **10\. Roadmap Eksekusi 4 Minggu (Diawali Spike) & Backlog Phase 2**

# **10.1 Roadmap MVP (4 Minggu untuk Solo Engineer)**

| Tahap | Durasi | Fokus Eksekusi | Deliverable & Bukti Terukur |
| :---- | :---- | :---- | :---- |
| **Minggu 0 (Spike)** | **Hari 1–3** | **XBRL Taxonomy Spike** | Mengunduh berkas `instance.xbrl` untuk **5 emiten konstruksi x 4 kuartal (20 file)**. Memetakan tag riil aset kontrak, piutang, utang berbunga, dan CFO di Jupyter/script sederhana sebelum membuat arsitektur kode. |
| **Minggu 1** | **Hari 4–10** | **Parser, De-cumulator & SQLite** | Membangun `lxml` parser, kamus `taxonomy_mapping.yaml` dari hasil Spike, modul de-kumulasi YTD, penyimpanan `SQLite`, dan unit test persamaan neraca (`pytest`). |
| **Minggu 2** | **Hari 11–17** | **3 Metrik, Safeguard & Evaluasi Kasus** | Implementasi 3 metrik TTM, *Small-N Guard*, *Sustained Cash Safeguard*, dan menjalankan evaluasi retrospektif 2020–2025 untuk seluruh emiten sub-industri konstruksi. |
| **Minggu 3** | **Hari 18–24** | **Bot Telegram, Jinja2 & Audit Trail** | Membangun Bot Telegram (`aiogram`) dengan template `Jinja2` dan pencetakan *audit trail* (tag XBRL \+ nilai asli). *(Stretch Goal: ekstraksi 1 catatan CALK dengan Verbatim Grounding Verifier).* |
| **Minggu 4** | **Hari 25–30** | **Audit Sampel, Benchmark & Demo** | Verifikasi manual 20% angka hasil parsing terhadap laporan PDF asli, pengukuran benchmark waktu kueri SQLite riil, penulisan ADR di GitHub, dan rekaman video demo 60–90 detik. |

# **10.2 Backlog Phase 2 (Ditunda Setelah MVP Selesai)**

Fitur berikut **dikeluarkan dari lingkup MVP** untuk mencegah *scope creep*:

* **Web Dashboard (Next.js / PWA)** dan panel visualisasi interaktif.  
* **Watchlist Push Notification Engine** dan otomatisasi *polling* rilis laporan kuartalan baru.  
* **Ekstraksi Rencana Penggunaan Dana (Use of Proceeds)** dari PDF Prospektus aksi korporasi.  
* **Dukungan Multi-LLM Lokal (Ollama)** dan ekspansi ke sub-industri non-keuangan lainnya (Komoditas/Energi).

