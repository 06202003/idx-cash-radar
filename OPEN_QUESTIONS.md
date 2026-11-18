# OPEN_QUESTIONS.md

## Keputusan & Pekerjaan Masa Depan (18 Nov 2026)

1. **Q1 — Pelatihan Ulang Model Solvabilitas (Masa Depan):**
   - Klaim AUC lama (`0.9989` / `0.9685`) dicabut karena *label leakage*. Skor utama saat ini murni deterministik (`cash_coverage` dan *safeguard flags*).
   - **Pekerjaan Masa Depan:** Pelatihan ulang model solvabilitas menggunakan label eksternal independen (misalnya tanggal suspensi BEI, PKPU, atau gagal bayar obligasi) dengan *time-split* ketat.

2. **Q2 — Arsip Keterbukaan Informasi BEI 2022–2025 (Masa Depan):**
   - Fase 5 (`reports/backtest.md`) menghasilkan status `BUKTI TIDAK CUKUP` (`N=1` Treatment, `N=1` Control, `N=0` untuk horizon 5/20/60 hari bursa) karena snapshot RSS hanya memuat berita terbaru.
   - **Pekerjaan Masa Depan:** Pengumpulan **arsip Keterbukaan Informasi BEI 2022–2025** bertanggal terverifikasi (minimal 20–30 kejadian per kelompok) untuk menguji ulang aturan `docs/backtest_rules.md` terhadap harga *adjusted close* Yahoo Finance (`.JK` dan `^JKSE`).

3. **Q3 — Verifikasi XBRL Kandidat Universe Baru (Fase 6):**
   - Endpoint publik `idx.co.id` memblokir akses otomatis saat pengecekan 28 kandidat UMA/FCA/suspensi (`reports/universe_candidates.csv`), sehingga kelengkapan XBRL 2020–2025 kandidat baru perlu verifikasi manual / browser resmi BEI sebelum dimasukkan ke pipeline produksi.
