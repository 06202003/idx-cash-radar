# ADR 001: Penanganan Batas Regim PSAK 72 (2020) dan Buffer Lookback TTM (2019)

- **Status:** Accepted (Pre-Spike Baseline)
- **Tanggal:** 11 November 2026
- **Pengambil Keputusan:** Yehezkiel David Setiawan

## Konteks Masalah
PSAK 72 (*Pendapatan dari Kontrak dengan Pelanggan*) berlaku efektif di Indonesia mulai 1 Januari 2020, menggantikan PSAK 34 (*Kontrak Konstruksi*). Perubahan ini memperkenalkan pos neraca baru `Aset Kontrak` dan `Liabilitas Kontrak` (menggantikan `Tagihan Bruto / Kewajiban Bruto kepada Pemberi Kerja`).

Namun, dua metrik utama dalam sistem membutuhkan data historis 4 kuartal ke belakang ($t-1$ s.d. $t-4$):
1. Perhitungan *Trailing Twelve Months* (TTM) pada Q1, Q2, dan Q3 tahun 2020 membutuhkan data kuartalan tahun 2019.
2. Perhitungan perubahan intensitas eksposur kontrak tahunan (`Divergence_YoY`) pada tahun 2020 membutuhkan saldo eksposur pada kuartal yang sama tahun 2019 ($t-4$).

Jika sistem hanya mengunduh berkas mulai Q1 2020, maka nilai TTM baru terbentuk pada Q4 2020 dan `Divergence_YoY` baru terbentuk pada Q4 2021, yang memperpendek jendela evaluasi historis secara signifikan.

## Keputusan Arsitektur
1. **Buffer Lookback 2019 untuk Akun Aliran Kas & Laba Rugi:**
   Pipeline mengunduh berkas `instance.xbrl` tahun 2019 (Q1–FY 2019) sebagai *lookback buffer* untuk pos `Pendapatan`, `Laba Bersih`, `Arus Kas Operasi (CFO)`, dan `Total Aset`. Karena definisi kas operasional dan total aset tidak mengalami distorsi struktural akibat transisi PSAK 72, `Sloan Accrual Ratio TTM` dan `Cash Coverage` dapat dihitung secara utuh mulai **Q1 2020**.
2. **Aturan Transisi Pos Aset Kontrak (2019 vs 2020):**
   - Prioritas pertama: mengambil angka komparatif tahun 2019 yang disajikan kembali (*restated comparative context*) di dalam berkas `instance.xbrl` tahun 2020.
   - Prioritas kedua (jika konteks komparatif tidak memuat kuartal interim 2019): memetakan pos PSAK 34 (`Tagihan Bruto kepada Pemberi Kerja` ke `Aset Kontrak` dan `Kewajiban Bruto kepada Pemberi Kerja` ke `Liabilitas Kontrak`) dengan menempelkan penanda metadata `is_pre_psak72_mapped = True`.
3. **Isolasi Penyesuaian Audit Kuartal 4 (`is_audit_derived_q4`):**
   Karena kuartal tunggal Q4 dihitung dari $\text{FY (Audited)} - 9\text{M (Unaudited)}$, seluruh koreksi audit satu tahun penuh terkonsentrasi di angka tunggal Q4. Sistem tetap menggunakan angka TTM sebagai basis utama evaluasi tren dan menandai setiap angka kuartal tunggal Q4 dengan atribut `is_audit_derived_q4 = True`.

## Konsekuensi
- **Positif:** Jendela evaluasi efektif untuk `Sloan Ratio TTM` dan `Cash Coverage` tetap utuh mencakup 24 kuartal penuh (Q1 2020 – Q4 2025), sehingga kasus gagal bayar konstruksi yang terjadi pada 2021–2022 tetap memiliki riwayat *lead time* yang cukup.
- **Negatif / Beban Tambahan:** Membutuhkan penambahan pemetaan tag PSAK 34 tahun 2019 di dalam `config/taxonomy_mapping.yaml` yang harus diverifikasi pada saat *Spike* Minggu 0.