# REPORT.md (Parsial — Berhenti di Gerbang Fase 1)

> **Status Eksekusi:** Berhenti otomatis setelah **Fase 1 (Audit Model)** karena gerbang menemukan masalah serius: **KLAIM AUC LAMA TIDAK DAPAT DIPERTAHANKAN** (terbukti *label leakage* + performa *out-of-sample* model ML kalah dari aturan baseline sederhana pada metrik *recall* dan akurasi).

---

## 1. Status per Fase

| Fase | Branch | Status | Alasan |
| :--- | :--- | :--- | :--- |
| **Fase 1 — Audit Model** | `fase-1-model` | **SELESAI** | Audit selesai, ditemukan *label leakage* dan kegagalan mengalahkan baseline pada split waktu; laporan ditulis di `reports/model_audit.md`. |
| **Fase 2 — Copy & Klaim** | — | **DILEWATI (Menunggu Arahan)** | Dihentikan sesuai aturan gerbang Fase 1 sebelum masuk ke Fase 2. |
| **Fase 5 — Backtest Kasus** | — | **DILEWATI (Menunggu Arahan)** | Dihentikan sesuai aturan gerbang Fase 1. |
| **Fase 3 — Kartu Shareable** | — | **DILEWATI (Menunggu Arahan)** | Dihentikan sesuai aturan gerbang Fase 1. |
| **Fase 4 — Analytics** | — | **DILEWATI (Menunggu Arahan)** | Dihentikan sesuai aturan gerbang Fase 1. |
| **Fase 6 — Universe** | — | **DILEWATI (Menunggu Arahan)** | Dihentikan sesuai aturan gerbang Fase 1. |

---

## 2. Temuan Buruk (Melemahkan Klaim Produk)

1. **Label Leakage (Target Sirkular) pada Model Solvabilitas:**
   - Di `scripts/train_idx_models.py` (baris 88–109 untuk L2 Logistic, baris 382–398 untuk MLP), label `is_distress` dihitung langsung dari `cov` (`cash_coverage_ratio`), `cfo` (`cfo_ttm_idr`), `debt_free`, dan `flag_acute_liquidity` pada periode yang sama, lalu variabel tersebut dimasukkan sebagai fitur input (`log_cov`, `neg_cfo`).
   - Klaim `CV ROC-AUC = 0.9888` / `0.9989` (L2 Logit) dan `0.9685` (MLP) tidak valid sebagai ukuran kemampuan prediksi.
2. **Model ML Kalah dari Baseline Sederhana pada Split Waktu (`2022–2023` -> `2024–2025`):**
   - Pada uji split waktu ketat (Train `n=24`, Pos=3; Test `n=98`, Pos=15), model L2 Logistic pada threshold `0.50` mencatat **Accuracy = 0.8469**, **Precision = 0.0000**, **Recall = 0.0000** (`TP=0, FN=15`).
   - Sebaliknya, baseline 1-aturan `cash_coverage < 1.0` mencatat **Accuracy = 0.8980**, **Precision = 0.6000**, **Recall = 1.0000** (`TP=15, FN=0`), dan `cash_coverage < 0.25` mencatat **Accuracy = 0.9898**, **Precision = 1.0000**, **Recall = 0.9333** (`TP=14, FN=1`).
   - Pada uji *forward* non-kontemporer `t -> t+1` (Train `n=24` Pos=4 -> Test `n=49` Pos=8), L2 Logistic kembali mencatat **Recall = 0.0000** (`TP=0, FN=8`) sementara `cash_coverage < 1.0` mencatat **Recall = 1.0000** (`Acc = 0.8980`) dan `cash_coverage < 0.25` mencatat **Recall = 0.7500** (`Acc = 0.9592`).
3. **Sampel Historis 2020–2023 Sangat Terbatas:**
   - Basis data `idx_cash_radar.db` hanya memiliki 12 observasi di 2022 dan 12 observasi di 2023 (total 24 observasi untuk periode sebelum 2024; tahun 2020–2021 kosong di `computed_metrics`).
4. **Klaim "0% Halusinasi" & Angka AUC di UI/Brief:**
   - Klaim AUC lama masih tercantum di `docs/IDX_Cash_Radar_Product_Brief_ID.pdf` dan kode fallback UI (`0.989` di `src/web/templates/index.html`) — wajib dibersihkan di Fase 2 jika disetujui lanjut.

---

## 3. Perubahan File per Branch & Cara Menjalankan Ulang

- **Branch `fase-1-model`:**
  - `reports/model_audit.py` — skrip audit independen (leakage check, time-split, expanding window, `t -> t+1`, baseline comparison, bootstrap 95% CI).
  - `reports/model_audit.md` — laporan hasil audit lengkap.
  - `OPEN_QUESTIONS.md` — daftar pertanyaan terbuka.
  - `REPORT.md` — laporan akhir parsial ini.
- **Cara menjalankan ulang audit Fase 1 & test suite:**
  ```bash
  python reports/model_audit.py
  python -m pytest -q
  ```

---

## 4. Daftar `OPEN_QUESTIONS` (Butuh Keputusan Manusia)

Lihat rincian di `OPEN_QUESTIONS.md`:
1. Apakah model ML solvabilitas (L2 Logit & MLP) dihapus/dinonaktifkan dari klaim utama di Fase 2, atau direncanakan untuk dilatih ulang dengan label eksternal (suspensi/PKPU/gagal bayar)?
2. Sumber data historis harga & berita bertanggal mana yang disetujui untuk dipakai di Fase 5 (Backtest)?

---

## 5. Penilaian Jujur Hook "Berita vs Kas"

**Status: belum cukup bukti.** Secara konseptual, membandingkan narasi berita dengan kondisi kas XBRL masuk akal sebagai alat cek fakta, tetapi hingga Fase 1 selesai belum ada uji *backtest* historis terhadap return pasar maupun evaluasi out-of-sample pada label eksternal (suspensi/PKPU/gagal bayar), dan model solvabilitas yang ada saat ini terbukti mengandung *label leakage* serta gagal mengalahkan aturan deterministik sederhana (`cash_coverage < 1.0`).
