# KLAIM AUC LAMA TIDAK DAPAT DIPERTAHANKAN

# Audit Model Solvabilitas — Fase 1 (`reports/model_audit.md`)

Audit independen terhadap `scripts/train_idx_models.py`, `data/models/idx_solvency_model.json`, dan `data/models/idx_solvency_mlp_v1.json`.

## 1. Temuan Label Leakage (Kebocoran Target)

**Status:** **TERBUKTI ADA LABEL LEAKAGE (CIRCULAR TARGET)**.

Pada `scripts/train_idx_models.py` (baris 88–109 untuk L2 Logistic, dan baris 382–398 untuk Neural MLP), label target `is_distress` diturunkan secara deterministik dari variabel periode yang sama (`cov`, `cfo`, `debt_free`, `flag_acute_liquidity`) yang langsung dimasukkan sebagai fitur input (`log_cov`, `neg_cfo`):

```python
# scripts/train_idx_models.py baris 89-108
debt_free = bool(r["debt_free_short_term"])
cov = 8.0 if debt_free else float(r["cash_coverage_ratio"] or 0.0)
log_cov = math.log1p(cov)
neg_cfo = 1.0 if cfo < 0 else 0.0
is_distress = int(
    bool(r["flag_acute_liquidity"])
    or (not debt_free and cov < 0.35 and cfo < 0)
    or (not debt_free and cov < 0.25)
)
X_raw.append([log_cov, sloan, cfo_margin, rec_int, neg_cfo])
```

**Konsekuensi:** Angka `CV ROC-AUC = 0.9989` (L2 Logit) dan `0.9685` (MLP) pada random 5-fold CV **bukan** mengukur kemampuan prediksi masa depan, melainkan hanya mengukur seberapa dekat regresi logistik meniru rumus `if-else` dari fitur inputnya sendiri.

## 2. Distribusi Observasi per Tahun (`idx_cash_radar.db`)

| Tahun | Total Observasi | Positif (`is_distress=1`) | Negatif (`is_distress=0`) |
| :--- | ---: | ---: | ---: |
| 2022 | 12 | 0 | 12 |
| 2023 | 12 | 3 | 9 |
| 2024 | 49 | 7 | 42 |
| 2025 | 49 | 8 | 41 |

## 3. Evaluasi Out-of-Sample Berbasis Waktu (Tanpa Random Split)

### Time Split (Train 2022-2023 -> Test 2024-2025)
- **Train:** n=24 (Pos=3, Neg=21)
- **Test:** n=98 (Pos=15, Neg=83)
- **L2 Logistic Model:** ROC-AUC=0.9992 (95% CI [0.9952, 1.0000]) | Acc=0.8469 (95% CI [0.7755, 0.9184]) | Prec=0.0000 | Rec=0.0000 | CM(TP=0, FP=0, TN=83, FN=15)
- **Baseline Aturan `cash_coverage < 1.0`:** ROC-AUC=0.9398 (95% CI [0.9026, 0.9740]) | Acc=0.8980 (95% CI [0.8367, 0.9592]) | Prec=0.6000 | Rec=1.0000 | CM(TP=15, FP=10, TN=73, FN=0)
- **Baseline Aturan `cash_coverage < 0.25`:** ROC-AUC=0.9667 (95% CI [0.8750, 1.0000]) | Acc=0.9898 (95% CI [0.9694, 1.0000]) | Prec=1.0000 | Rec=0.9333 | CM(TP=14, FP=0, TN=83, FN=1)

### Expanding Window 1 (Train 2022-2023 -> Test 2024)
- **Train:** n=24 (Pos=3, Neg=21)
- **Test:** n=49 (Pos=7, Neg=42)
- **L2 Logistic Model:** ROC-AUC=1.0000 (95% CI [1.0000, 1.0000]) | Acc=0.8571 (95% CI [0.7551, 0.9388]) | Prec=0.0000 | Rec=0.0000 | CM(TP=0, FP=0, TN=42, FN=7)
- **Baseline Aturan `cash_coverage < 1.0`:** ROC-AUC=0.9286 (95% CI [0.8716, 0.9768]) | Acc=0.8776 (95% CI [0.7755, 0.9592]) | Prec=0.5385 | Rec=1.0000 | CM(TP=7, FP=6, TN=36, FN=0)
- **Baseline Aturan `cash_coverage < 0.25`:** ROC-AUC=0.9286 (95% CI [0.7500, 1.0000]) | Acc=0.9796 (95% CI [0.9388, 1.0000]) | Prec=1.0000 | Rec=0.8571 | CM(TP=6, FP=0, TN=42, FN=1)

### Expanding Window 2 (Train 2022-2024 -> Test 2025)
- **Train:** n=73 (Pos=10, Neg=63)
- **Test:** n=49 (Pos=8, Neg=41)
- **L2 Logistic Model:** ROC-AUC=1.0000 (95% CI [1.0000, 1.0000]) | Acc=0.9184 (95% CI [0.8367, 0.9796]) | Prec=1.0000 | Rec=0.5000 | CM(TP=4, FP=0, TN=41, FN=4)
- **Baseline Aturan `cash_coverage < 1.0`:** ROC-AUC=0.9512 (95% CI [0.9024, 0.9881]) | Acc=0.9184 (95% CI [0.8367, 0.9796]) | Prec=0.6667 | Rec=1.0000 | CM(TP=8, FP=4, TN=37, FN=0)
- **Baseline Aturan `cash_coverage < 0.25`:** ROC-AUC=1.0000 (95% CI [1.0000, 1.0000]) | Acc=1.0000 (95% CI [1.0000, 1.0000]) | Prec=1.0000 | Rec=1.0000 | CM(TP=8, FP=0, TN=41, FN=0)

### Non-Leaky Forward Target t -> t+1 (Train 2022-2023 -> Test 2024->2025)
- **Train:** n=24 (Pos=4, Neg=20)
- **Test:** n=49 (Pos=8, Neg=41)
- **L2 Logistic Model:** ROC-AUC=0.9909 (95% CI [0.9592, 1.0000]) | Acc=0.8367 (95% CI [0.7347, 0.9388]) | Prec=0.0000 | Rec=0.0000 | CM(TP=0, FP=0, TN=41, FN=8)
- **Baseline Aturan `cash_coverage < 1.0`:** ROC-AUC=0.9390 (95% CI [0.8856, 0.9857]) | Acc=0.8980 (95% CI [0.7959, 0.9796]) | Prec=0.6154 | Rec=1.0000 | CM(TP=8, FP=5, TN=36, FN=0)
- **Baseline Aturan `cash_coverage < 0.25`:** ROC-AUC=0.8750 (95% CI [0.7083, 1.0000]) | Acc=0.9592 (95% CI [0.8980, 1.0000]) | Prec=1.0000 | Rec=0.7500 | CM(TP=6, FP=0, TN=41, FN=2)

## 4. Kesimpulan Audit & Keputusan Gerbang Fase 1

1. **Klaim AUC Lama Gugur:** Angka `0.9888` / `0.9989` (dan MLP `0.9685`) berasal dari target sirkular (*label leakage*) + *random split*.
2. **Sampel Positif Sangat Kecil:** Data historis 2022–2023 hanya berisi 24 observasi (Pos=3). Pada uji forward non-leakage `t -> t+1`, hanya terdapat 4 kasus positif di train dan 8 kasus di test.
3. **Perbandingan vs Baseline Sederhana:** Pada label yang sama, aturan tunggal `cash_coverage < 0.25` sudah menyamai atau mendekati performa model ML, sementara model tidak memiliki keunggulan prediktif independen terhadap kejadian gagal bayar/suspensi eksternal karena tidak ada label eksternal di database.
4. **Keputusan Gerbang:** **KLAIM AUC LAMA TIDAK DAPAT DIPERTAHANKAN**. Angka AUC lama wajib dihapus dari halaman depan, brief, dan materi promosi.
