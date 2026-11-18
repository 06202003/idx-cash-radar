# REPORT.md — Laporan Akhir Audit, Kredibilitas & Validasi (Fase 1–6)

> **Positioning Produk Terkini:** Alat audit fakta keuangan berbasis XBRL resmi BEI dan radar katalis berita, **tanpa klaim prediktif** dan **tanpa rekomendasi beli/jual**.

---

## 1. Status per Fase

| Fase | Branch | Status | Alasan |
| :--- | :--- | :--- | :--- |
| **Fase 1 — Audit Model** | `fase-1-model` | **SELESAI** | Audit selesai ([reports/model_audit.md](reports/model_audit.md)); klaim AUC lama (`0.9989` / `0.9685`) dicabut karena *label leakage* dan kalah dari baseline sederhana pada split waktu. |
| **Fase 2 — Copy & Klaim** | `fase-2-copy` | **SELESAI** | Klaim `"0% Halusinasi"` & AUC/L2/MLP dihapus dari tampilan utama & brief; `/metodologi` & `docs/glosarium.md` dibuat; MLP/NB/BYOK dipindah ke **Pro / Lanjutan**; disclaimer & bahasa ritel diterapkan. |
| **Fase 5 — Backtest Kasus** | `fase-5-backtest` | **SELESAI (`BUKTI TIDAK CUKUP`)** | Aturan dibekukan di `docs/backtest_rules.md`; uji pada seluruh data terverifikasi menghasilkan `BUKTI TIDAK CUKUP` (`reports/backtest.md`, `reports/backtest_events.csv`). |
| **Fase 3 — Kartu Shareable** | `fase-3-kartu` | **SELESAI** | Endpoint kartu fakta PNG `1:1` & `9:16` (`/api/card/{ticker}.png`), tombol unduh/salin, tes kepatuhan bahasa, dan tes jejak angka (`36/36 = 100.0%` terlacak ke `canonical_facts`). |
| **Fase 4 — Analytics** | `fase-4-analytics` | **SELESAI** | Plausible + counter anonim lokal (tanpa PII/API key, `docs/privacy.md`), 6 event minimum dengan prioritas `ticker_dicek` & `kartu_dibagikan`, serta dashboard `/analytics` (Top 5 ticker). |
| **Fase 6 — Universe** | `fase-6-universe` | **SELESAI** | Daftar 28 kandidat UMA/FCA/suspensi dari sumber RSS terverifikasi + tanggal akses ditulis ke `reports/universe_candidates.csv` tanpa menambah ke pipeline produksi. |

---

## 2. Temuan Buruk (Apa Adanya)

1. **Label Leakage & Pencabutan Klaim AUC Lama (Fase 1):**
   - `scripts/train_idx_models.py` (baris 88–109 & 382–398) menurunkan target `is_distress` dari `cash_coverage_ratio`, `cfo_ttm_idr`, `debt_free`, dan `flag_acute_liquidity` di periode yang sama lalu memasukkannya sebagai fitur input (`log_cov`, `neg_cfo`).
   - Pada split waktu (`Train 2022–2023 n=24 Pos=3` -> `Test 2024–2025 n=98 Pos=15`), L2 Logistic mencatat **`Recall = 0.0000` (`TP=0, FN=15, Acc=0.8469`)**, kalah dari baseline tunggal `cash_coverage < 1.0` (`Acc=0.8980, Prec=0.6000, Rec=1.0000, TP=15, FP=10, TN=73, FN=0`) dan `cash_coverage < 0.25` (`Acc=0.9898, Prec=1.0000, Rec=0.9333, TP=14, FP=0, TN=83, FN=1`).
   - Pada uji forward non-kontemporer `t -> t+1` (`Train n=24 Pos=4 -> Test n=49 Pos=8`), L2 Logistic kembali mencatat **`Recall = 0.0000` (`TP=0, FN=8`)**, sedangkan `cash_coverage < 1.0` mencatat **`Rec=1.0000` (`Acc=0.8980`)**.
2. **Backtest "Berita Positif + Kas Tertekan" Belum Memiliki Bukti Cukup (Fase 5):**
   - Hanya ditemukan **4** berita `POSITIF` bertanggal spesifik (`1` Treatment, `1` Control), dengan **`N = 0`** untuk horizon 5, 20, dan 60 hari bursa vs `^JKSE`. Draft *thread* dikosongkan.
3. **Keterbatasan Akses API `idx.co.id` untuk Kandidat Baru (Fase 6):**
   - Pengecekan otomatis ketersediaan XBRL 2020–2025 ke endpoint `idx.co.id` untuk kandidat baru di `reports/universe_candidates.csv` tidak dapat diakses otomatis (butuh verifikasi manual).
4. **Jejak Tag XBRL (Fase 3):**
   - `36/36 (100.0%)` sampel acak angka akuntansi di `/api/screener` terlacak ke `raw_xbrl_tag` + `raw_context_ref` di `canonical_facts`; data harga pasar (Yahoo Finance) dan sentimen berita RSS merupakan data eksternal non-XBRL.

---

## 3. Perubahan File per Branch & Cara Menjalankan Ulang

- **`fase-1-model`:** `reports/model_audit.py`, `reports/model_audit.md`, `OPEN_QUESTIONS.md`, `REPORT.md`.
- **`fase-2-copy`:** `docs/glosarium.md`, `src/web/app.py` (`/metodologi`), `src/web/templates/index.html`, `scripts/generate_product_brief_pdf.py`, `docs/IDX_Cash_Radar_Product_Brief_ID.html`, `docs/IDX_Cash_Radar_Product_Brief_ID.pdf`.
- **`fase-5-backtest`:** `docs/backtest_rules.md`, `reports/backtest.py`, `reports/backtest.md`, `reports/backtest_events.csv`.
- **`fase-3-kartu`:** `src/renderer/share_card.py`, `src/web/app.py` (`/api/card/{ticker}.png`, `/api/card/{ticker}`), `src/web/templates/index.html`, `tests/test_share_card.py`, `tests/test_number_traceability.py`.
- **`fase-4-analytics`:** `docs/privacy.md`, `src/web/app.py` (`/api/analytics/event`, `/api/analytics/summary`, `/analytics`), `src/web/templates/index.html`, `tests/test_analytics.py`.
- **`fase-6-universe`:** `reports/build_universe_candidates.py`, `reports/universe_candidates.csv`, `OPEN_QUESTIONS.md`, `REPORT.md`.

**Cara menjalankan ulang seluruh laporan & verifikasi:**
```bash
python reports/model_audit.py
python reports/backtest.py
python reports/build_universe_candidates.py
python -m pytest -q
```

---

## 4. Daftar `OPEN_QUESTIONS` (Butuh Keputusan Manusia)

Lihat `OPEN_QUESTIONS.md`:
1. Pelatihan ulang model solvabilitas menggunakan label eksternal independen (suspensi/PKPU/gagal bayar) sebagai pekerjaan masa depan.
2. Pengumpulan **arsip Keterbukaan Informasi BEI 2022–2025** untuk menguji ulang backtest Fase 5.
3. Verifikasi manual ketersediaan berkas XBRL 2020–2025 di `idx.co.id` bagi 28 kandidat UMA/FCA/suspensi di `reports/universe_candidates.csv` sebelum masuk pipeline produksi.

---

## 5. Penilaian Jujur Hook "Berita vs Kas"

**Status: belum teruji, bukan terbantah.** Pada Fase 5, aturan deterministik `"berita positif + kas tertekan"` telah dibekukan sebelum melihat harga, namun data historis berita bertanggal terverifikasi di repositori hanya menghasilkan 1 kejadian uji dan 1 kejadian kontrol (`N = 0` pada horizon 5, 20, dan 60 hari bursa), sehingga hipotesis tersebut belum dapat diuji secara statistik. Untuk mengujinya secara sah di masa depan dibutuhkan: **(1)** arsip **Keterbukaan Informasi BEI 2022–2025** (dan berita media dengan stempel tanggal pasti) minimal 20–30 kejadian per kelompok, **(2)** histori laporan keuangan XBRL per kuartal 2020–2025 yang lengkap (termasuk emiten yang telah *delisting* untuk mengurangi *survivorship bias*), dan **(3)** seri harga harian *adjusted close* Yahoo Finance (`.JK` dan `^JKSE`) untuk seluruh tanggal kejadian tersebut.
