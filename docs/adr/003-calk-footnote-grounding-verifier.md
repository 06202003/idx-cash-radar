# ADR 003: Deterministic Verbatim Grounding Verifier untuk Ekstraksi Catatan Kaki CALK (PDF)

- **Status:** Accepted (Stretch Goal PRD Section 5.2)
- **Tanggal:** 16 November 2026
- **Pengambil Keputusan:** Yehezkiel David Setiawan, S.Kom., M.Kom.

## Konteks Masalah
Pada industri konstruksi BEI, pos `Piutang Usaha` dan `Aset Kontrak` pada neraca utama sering kali tidak merinci seberapa besar porsi proyek yang dikerjakan untuk **Pihak Berelasi (afiliasi pemerintah/BUMN)** dibandingkan **Pihak Ketiga (swasta murni)**, serta berapa besar alokasi **Cadangan Kerugian Penurunan Nilai (CKPN)** yang dicadangkan emiten. Rincian krusial ini hanya tersedia dalam bentuk teks naratif dan tabel pada Catatan atas Laporan Keuangan (CALK) di dokumen PDF laporan tahunan.

Penggunaan *Large Language Model* (LLM) murni untuk mengekstrak angka dari tabel PDF membawa risiko serius:
1. **Halusinasi Nilai Angka:** Model bahasa generatif rentan mengarang angka, membulatkan secara liar, atau menukar baris tahun komparatif ($t$ vs $t-1$).
2. **Keterbatasan Validasi Skema (Pydantic Trap):** Validasi Pydantic hanya mengunci tipe data (misal: memastikan field bernilai `Decimal`), tetapi sama sekali tidak dapat memverifikasi apakah angka `Rp 3.841.520.000.000` benar-benar tertulis di dokumen primer atau hasil karangan AI.
3. **Format Angka Akuntansi Indonesia:** Dokumen keuangan Indonesia menggunakan titik pemisah ribuan (`1.234.567`), koma desimal (`1.234,56`), tanda kurung untuk angka negatif/kontra aset `(1.150.000)`, dan multiplier satuan seperti *"dalam jutaan rupiah"*.

## Keputusan Arsitektur
1. **Deterministic-First Pattern Extraction:**
   Pipeline mengutamakan ekstraksi tabel deterministik berbasis ekspresi reguler (`extract_breakdown_deterministic`) yang memindai baris teks peredam satuan secara instan ($< 1\text{ ms}$), nol biaya API, dan bebas halusinasi. Panggilan LLM (Gemini API) hanya diposisikan sebagai cadangan jika tata letak tabel sangat tidak beraturan.
2. **Deterministic Verbatim Grounding Verifier:**
   Setiap klaim angka yang dihasilkan (baik oleh LLM maupun parser tabel) **wajib** melalui tahap verifikasi teks primer:
   - Modul `normalize_indonesian_number_str` dan `extract_all_numerical_tokens` memindai seluruh token numerik pada teks halaman PDF sumber.
   - Setiap angka klaim dicocokkan secara eksak (verbatim) terhadap token teks sumber dengan memperhitungkan faktor pengali satuan pelaporan (`unit_multiplier`: IDR Penuh, Ribuan, atau Jutaan).
   - Penanganan akun kontra/deduktif: Tanda kurung akuntansi `(1.150.000)` dinormalisasi nilai absolutnya terhadap klaim CKPN positif.
3. **Strict Rejection & Audit Trail Guard:**
   Jika ada **satu saja** angka klaim yang tidak ditemukan secara verbatim pada teks sumber:
   - Status ekstraksi langsung ditetapkan `is_grounding_verified = False`.
   - Angka klaim ditolak (`rejection_reason` dipublikasikan secara eksplisit).
   - Dilarang menampilkan angka halusinasi sebagai data valid ke pengguna bot.
4. **Verifikasi Persamaan Akuntansi (Mathematical Sanity Check):**
   - $\text{Pihak Ketiga} + \text{Pihak Berelasi} == \text{Total Bruto}$
   - $\text{Total Bruto} - \text{CKPN} == \text{Total Neto}$
   - Selisih toleransi dibatasi $\le 1$ unit skala pelaporan.

## Konsekuensi
- **Positif:**
  - Jaminan matematis nol halusinasi (*zero-hallucination baseline*) untuk data catatan kaki CALK.
  - Pengguna Bot Telegram dapat langsung melihat persentase ketergantungan pihak berelasi dan cadangan CKPN lewat perintah `/calk <TICKER>` lengkap dengan *audit trail* token teks primer.
  - Mendukung pembacaan PDF langsung via PyMuPDF (`fitz`) dan `pypdf`.
- **Negatif / Batasan:**
  - Hanya diterapkan pada catatan kaki sempit (Piutang Usaha & Aset Kontrak) sesuai batasan PRD Section 5.2 untuk mencegah kompleksitas *scope creep*.
