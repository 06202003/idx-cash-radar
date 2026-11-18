# REPORT.md (Parsial — Berhenti di Gerbang Fase 5)

> **Status Eksekusi:** Berhenti otomatis setelah **Fase 5 (Backtest Kasus)** karena status hasil backtest adalah **`BUKTI TIDAK CUKUP`** (hanya 1 kejadian Treatment, 1 kejadian Control, dan `N=0` untuk horizon 5/20/60 hari bursa).

---

## 1. Status per Fase

| Fase | Branch | Status | Alasan |
| :--- | :--- | :--- | :--- |
| **Fase 1 — Audit Model** | `fase-1-model` | **SELESAI** | Audit selesai, ditemukan *label leakage* dan model ML kalah dari baseline aturan sederhana pada split waktu (`reports/model_audit.md`). |
| **Fase 2 — Copy & Klaim** | `fase-2-copy` | **SELESAI** | Klaim `"0% Halusinasi"` & AUC lama dihapus dari halaman utama/brief; `/metodologi` & `docs/glosarium.md` dibuat; MLP/NB/BYOK dipindah ke Pro/Lanjutan; disclaimer ditambahkan. |
| **Fase 5 — Backtest Kasus** | `fase-5-backtest` | **SELESAI (BUKTI TIDAK CUKUP)** | Aturan dibekukan di `docs/backtest_rules.md`; uji pada seluruh data terverifikasi menghasilkan `BUKTI TIDAK CUKUP` (`reports/backtest.md`, `reports/backtest_events.csv`). |
| **Fase 3 — Kartu Shareable** | — | **DILEWATI** | Berhenti di gerbang Fase 5 menunggu keputusan Anda. |
| **Fase 4 — Analytics** | — | **DILEWATI** | Berhenti di gerbang Fase 5. |
| **Fase 6 — Universe** | — | **DILEWATI** | Berhenti di gerbang Fase 5. |

---

## 2. Temuan Buruk (Melemahkan Klaim Produk)

1. **Klaim AUC Lama (0.9989 / 0.9685) Dicabut (Fase 1):**
   - Terbukti *label leakage* pada `scripts/train_idx_models.py` (baris 88–109 & 382–398).
   - Pada split waktu (`Train 2022–2023 n=24 Pos=3` -> `Test 2024–2025 n=98 Pos=15`), L2 Logistic mencatat `Recall=0.0000` (`TP=0, FN=15`), kalah dari baseline sederhana `cash_coverage < 1.0` (`Acc=0.8980, Rec=1.0000, TP=15, FP=10, TN=73, FN=0`) dan `cash_coverage < 0.25` (`Acc=0.9898, Prec=1.0000, Rec=0.9333, TP=14, FP=0, TN=83, FN=1`).
2. **Backtest "Berita Positif + Kas Tertekan" Gagal Mendapat Bukti Cukup (Fase 5):**
   - Dari seluruh data berita bertanggal terverifikasi yang ada di repositori, hanya ditemukan **4** berita `POSITIF` bertanggal spesifik, menghasilkan **1** kejadian `TREATMENT_KAS_TERTEKAN` dan **1** kejadian `CONTROL_KAS_SEHAT`.
   - Jumlah kejadian valid untuk horizon **5, 20, dan 60 hari bursa adalah `0`** karena snapshot RSS hanya berisi berita terbaru.
   - Akibatnya, draft *thread* dikosongkan (`reports/backtest.md`).
3. **Jejak Tag XBRL (Fase 2):**
   - Audit SQLite menunjukkan `49 / 49` emiten memiliki baris di `canonical_facts` (`1,898` baris). Namun kutipan harga pasar (Yahoo Finance) dan sentimen berita RSS merupakan data eksternal, bukan tag XBRL.

---

## 3. Perubahan File per Branch & Cara Menjalankan Ulang

- **`fase-1-model`:** `reports/model_audit.py`, `reports/model_audit.md`, `OPEN_QUESTIONS.md`, `REPORT.md`.
- **`fase-2-copy`:** `docs/glosarium.md`, `src/web/app.py` (route `/metodologi`), `src/web/templates/index.html` (hapus AUC/L2/MLP dari utama, Pro/Lanjutan, disclaimer, bahasa ritel), `scripts/generate_product_brief_pdf.py`, `docs/IDX_Cash_Radar_Product_Brief_ID.html`, `docs/IDX_Cash_Radar_Product_Brief_ID.pdf`.
- **`fase-5-backtest`:** `docs/backtest_rules.md`, `reports/backtest.py`, `reports/backtest.md`, `reports/backtest_events.csv`, `OPEN_QUESTIONS.md`, `REPORT.md`.

**Cara menjalankan ulang:**
```bash
python reports/model_audit.py
python reports/backtest.py
python -m pytest -q
```

---

## 4. Daftar `OPEN_QUESTIONS` (Butuh Keputusan Manusia)

1. **Pelatihan Ulang Model (Masa Depan):** Terbuka untuk dilatih ulang nanti hanya jika sudah ada label eksternal independen (suspensi/PKPU/gagal bayar).
2. **Data Berita Historis Fase 5:** Apakah kita perlu mengimpor arsip Keterbukaan Informasi BEI historis (2022–2025) terlebih dahulu, atau langsung lanjut ke **Fase 3 -> 4 -> 6** dengan posisi produk murni sebagai alat audit fakta (tanpa klaim prediktif)?

---

## 5. Penilaian Jujur Hook "Berita vs Kas"

**Status: belum cukup bukti.** Aturan sudah dibekukan dan dijalankan pada seluruh data berita terverifikasi yang ada, namun karena hanya tersedia 1 kejadian uji dan 1 kejadian kontrol (dengan `N=0` untuk horizon 5/20/60 hari bursa), belum ada bukti empiris apakah kombinasi *"berita positif + kas tertekan"* berkorelasi dengan *underperformance* harga saham dibanding IHSG atau dibanding kontrol *"kas sehat"*.
