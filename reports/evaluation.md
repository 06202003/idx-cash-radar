# Audit Kuantitatif Model Forecaster `idx-alert-bot`

## Ringkasan Eksekutif
1. **Apakah model punya edge?** **Tidak terbukti memiliki edge yang andal** pada data dev (28 saham, 5 tahun) maupun hold-out 63 hari bursa terakhir.
2. Pada hold-out terpisah (28 saham), kandidat terpilih `A1_th58` mencatat AUC `0.4728`, akurasi `61.05%` (vs majority baseline `61.85%`), dan net return sinyal bullish `0.07%` (CI 95%: `(-1.708, 1.634)`).
3. Baseline tren sederhana (`close > MA20 > MA50`) dan `always-long` di hold-out mencatat net return `-1.966%` dan `-1.543%`.
4. Penambahan kompleksitas (ensemble `HistGB`, 5 fitur baru, recency weighting) **tidak terbukti** mengalahkan `LogisticRegression` sederhana secara konsisten pada uji berpasangan.
5. Kurva trajectory `ML+5H` tidak mengalahkan baseline naif nol/drift pada MAE/RMSE OOS dan menunjukkan tingkat zig-zag tinggi pada model multi-output langsung.

## 0. Reproduksi Baseline (Before vs After pada 6 Saham Asli, 2 Tahun)
| Tag | Ticker | P(Naik 5H) | OOS Acc | Bull WR | Sinyal | Bull Avg Net Ret |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| `baseline-before` | VKTR | 32.8% | 45.0% | 36.2% | 94 | -4.35% |
| `baseline-before` | BBCA | 55.6% | 70.1% | 64.0% | 50 | 2.8% |
| `baseline-before` | BBRI | 48.1% | 53.6% | 48.3% | 89 | -0.66% |
| `baseline-before` | ADRO | 54.3% | 51.7% | 71.4% | 7 | 1.09% |
| `baseline-before` | ANTM | 39.5% | 45.5% | 36.2% | 58 | -2.94% |
| `baseline-before` | BRIS | 71.5% | 69.2% | 50.9% | 55 | 1.21% |
| `baseline-after` | VKTR | 45.7% | 52.6% | 45.3% | 106 | -0.2% |
| `baseline-after` | BBCA | 60.6% | 69.7% | 63.3% | 49 | 2.74% |
| `baseline-after` | BBRI | 47.7% | 54.0% | 48.4% | 64 | -0.23% |
| `baseline-after` | ADRO | 40.8% | 49.8% | 46.7% | 15 | -0.15% |
| `baseline-after` | ANTM | 32.7% | 52.1% | 48.9% | 90 | -1.29% |
| `baseline-after` | BRIS | 49.5% | 62.1% | 31.6% | 38 | -3.43% |

## 1. Dataset & Protokol
- **Universe:** 28 saham likuid IDX (`6` saham asli: `VKTR, BBCA, BBRI, ADRO, ANTM, BRIS` + `22` saham likuid LQ45) serta indeks `^JKSE`.
- **Periode:** 5 tahun dari Yahoo Finance (~1200 hari bursa per saham). **Keterbatasan rezim:** 5 tahun IDX masih didominasi beberapa siklus makro spesifik dan tidak mencakup krisis ekstrem seperti 2008/2020 awal.
- **Split:** `63` hari bursa terakhir dikunci sebagai **hold-out**; sisanya menjadi **dev** dengan jeda purge `5` hari sebelum hold-out.
- **Walk-forward pada dev:** Expanding window, minimal `5` fold per saham, purge gap `5` hari antara train dan test, scaling hanya di-fit pada train fold.

## 2. Baseline Wajib (Dev Set — Pooled 28 Saham & 6 Saham Asli)
| Strategi | Pooled 28: Sinyal (n_eff) | Bull WR (95% Wilson CI) | Bull Net Ret (95% Block CI) | Acc / BalAcc | Maj Acc |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `B_always_long` | 14903 (2980.6) | 44.29% (43.49, 45.09) | -0.347% (-0.508, -0.177) | 44.29% / 50.0% | 54.17% |
| `B_majority` | 1288 (257.6) | 41.07% (38.42, 43.78) | -0.962% (-1.532, -0.497) | 54.17% / 49.44% | 54.17% |
| `B_trend_rule` | 3734 (746.8) | 44.19% (42.6, 45.79) | -0.265% (-0.621, 0.133) | 52.8% / 49.95% | 54.17% |
| `B_random_200` | 784 (156.8) | 44.17% (41.02, 47.83) | -0.361% (-0.712, 0.017) | 55.1% / 50.0% | 54.17% |
| `A0 (LR Lama)` | 2152 (430.4) | 46.05% (43.95, 48.16) | -0.113% (-0.554, 0.278) | 54.57% / 50.52% | 54.17% |

## 3. Ablation A0–A8 (Dev Set, Pooled 28 Saham)
Total konfigurasi dievaluasi: **10** (peringatan *multiple testing*: makin banyak konfigurasi dicoba, makin besar risiko false discovery).

| ID | Deskripsi | Sinyal (n_eff) | Bull WR | Bull Net Ret | Acc (Maj) | AUC | Brier | LogLoss | ΔAcc vs A0 (95% CI) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| `A0` | Model lama (LR 8 feat, no purge, th=0.55) | 2152 (430.4) | 46.05% | -0.113% | 54.57% (54.17%) | 0.4977 | 0.2562 | 0.7084 | - |
| `A1` | A0 + purge gap 5H saja | 2190 (438.0) | 46.07% | -0.134% | 54.56% (54.17%) | 0.4985 | 0.2565 | 0.7091 | -0.01% [-0.23, +0.21] (tidak terbukti) |
| `A2` | A0 + threshold 0.58 saja | 1330 (266.0) | 49.62% | 0.334% | 55.65% (54.17%) | 0.4977 | 0.2562 | 0.7084 | +1.07% [+0.62, +1.52] (YA) |
| `A3` | A0 + recency weighting saja | 2617 (523.4) | 44.78% | -0.254% | 53.88% (54.17%) | 0.4887 | 0.2631 | 0.7265 | -0.69% [-1.47, +0.12] (tidak terbukti) |
| `A4` | A0 + 5 fitur OHLCV baru saja | 3023 (604.6) | 44.82% | -0.372% | 53.61% (54.17%) | 0.5021 | 0.2606 | 0.7186 | -0.96% [-1.78, -0.28] (YA) |
| `A5` | A0 + ensemble LR+HistGB saja | 2209 (441.8) | 46.99% | 0.003% | 54.82% (54.17%) | 0.4991 | 0.2554 | 0.7053 | +0.25% [-0.42, +0.97] (tidak terbukti) |
| `A6` | Gabungan A1+A2+A3+A4+A5 | 1867 (373.4) | 45.47% | -0.392% | 54.58% (54.17%) | 0.4994 | 0.2604 | 0.717 | +0.01% [-0.93, +0.90] (tidak terbukti) |
| `A7` | A6 + fitur IHSG (^JKSE) | 2030 (406.0) | 45.07% | -0.376% | 54.37% (54.17%) | 0.4956 | 0.262 | 0.7207 | -0.20% [-1.08, +0.66] (tidak terbukti) |
| `A8` | A6 + trend gate (blokir downtrend) | 784 (156.8) | 40.94% | -1.135% | 54.76% (54.17%) | 0.4994 | 0.2604 | 0.717 | +0.19% [-0.67, +1.08] (tidak terbukti) |
| `A1_th58` | LR 8 feat + purge 5H + th 0.58 (sederhana) | 1362 (272.4) | 49.12% | 0.17% | 55.55% (54.17%) | 0.4985 | 0.2565 | 0.7091 | - |

### Kalibrasi Probabilitas Kandidat Terpilih pada Dev (`A1_th58`)
| Bin Probabilitas | n | Mean Pred | Realized Up |
| :--- | ---: | ---: | ---: |
| [0.0, 0.2] | 163 | 14.2% | 58.3% |
| [0.2, 0.4] | 3422 | 34.9% | 44.0% |
| [0.4, 0.6] | 10354 | 48.0% | 43.6% |
| [0.6, 0.8] | 920 | 65.4% | 50.3% |
| [0.8, 1.0] | 44 | 83.6% | 40.9% |

### Perbandingan Khusus 6 Saham Asli pada Dev (`A0` vs `A1_th58`)
| Ticker | A0 Acc (Maj) | A0 Bull WR / Ret | A1_th58 Acc (Maj) | A1_th58 Bull WR / Ret |
| :--- | ---: | ---: | ---: | ---: |
| VKTR | 46.0% (46.29%) | 48.94% / -0.3% | 46.0% (46.29%) | 47.83% / -2.823% |
| BBCA | 64.75% (64.38%) | 52.08% / 2.008% | 65.49% (64.38%) | 60.71% / 3.111% |
| BBRI | 56.03% (56.59%) | 0.0% / -1.436% | 56.59% (56.59%) | 0.0% / 0.0% |
| ADRO | 53.8% (44.71%) | 40.0% / -0.666% | 56.59% (44.71%) | 55.56% / 1.226% |
| ANTM | 53.25% (51.39%) | 54.39% / 0.507% | 54.92% (51.39%) | 63.77% / 1.562% |
| BRIS | 61.41% (61.22%) | 53.85% / 1.776% | 61.78% (61.22%) | 71.43% / 4.577% |

## 4. Evaluasi Hold-Out Sekali Saja (63 Hari Bursa Terakhir, Terkunci)
Konfigurasi terpilih dari dev: **`A1_th58`** — LR 8 feat + purge 5H + th 0.58 (sederhana).

| Model / Baseline | Sinyal (n_eff) | Bull WR (95% CI) | Bull Net Ret (95% CI) | Acc / BalAcc | Maj Acc | AUC |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `A1_th58` (Terpilih) | 133 (26.6) | 44.36% (36.19, 52.84) | 0.07% (-1.708, 1.634) | 61.05% / 51.0% | 61.85% | 0.4728 |
| `A0` (Model Lama) | 237 (47.4) | 40.51% (34.46, 46.86) | -1.011% (-2.42, 0.42) | 59.35% / 50.69% | 61.85% | 0.4728 |
| `B_always_long` | 1764 (352.8) | 38.1% (35.86, 40.39) | -1.543% (-2.111, -0.919) | 38.1% / 50.0% | 61.85% | None |
| `B_majority` | 63 (12.6) | 49.21% (37.27, 61.24) | -0.404% (-3.014, 1.666) | 61.85% / 50.84% | 61.85% | None |
| `B_trend_rule` | 320 (64.0) | 30.63% (25.83, 35.88) | -1.966% (-2.885, -1.221) | 54.88% / 47.13% | 61.85% | None |
| `B_random_200` | 133 (26.6) | 38.05% (29.4, 45.45) | -1.519% (-2.629, -0.373) | 60.12% / 50.0% | 61.85% | 0.5 |

## 5. Validasi Trajectory `ML+5H` OOS (Dev Set)
| Model | MAE +1H..+5H (%) | RMSE +1H..+5H (%) | Dir Acc +1H..+5H (%) | Zig-Zag Rate |
| :--- | :--- | :--- | :--- | ---: |
| Naive Flat (0%) | [1.827, 2.558, 3.109, 3.579, 3.986] | [2.733, 3.764, 4.529, 5.184, 5.762] | [56.4, 54.8, 53.9, 53.0, 53.4] | 0.0% |
| Historical Drift | [1.833, 2.569, 3.123, 3.596, 4.015] | [2.734, 3.769, 4.537, 5.196, 5.78] | [47.1, 47.8, 48.3, 48.8, 48.0] | 0.0% |
| Ridge + ExtraTrees | [1.845, 2.601, 3.182, 3.682, 4.118] | [2.745, 3.804, 4.609, 5.306, 5.933] | [50.3, 50.0, 49.6, 49.2, 49.2] | 27.9% |
| Monotonic Ridge | [1.855, 2.618, 3.21, 3.721, 4.172] | [2.756, 3.828, 4.645, 5.357, 6.0] | [50.1, 50.2, 49.6, 49.7, 49.6] | 0.0% |
- **Empirical 68% Residual Cone Coverage (+1H..+5H):** `[61.2, 60.3, 59.8, 59.0, 57.9]%`

## 6. Keterbatasan
1. **Satu rezim makro dominan:** Data 5 tahun IDX tidak mencakup krisis sistemik penuh seperti 2008 atau kejatuhan Maret 2020 pada seluruh emiten.
2. **Tanpa fitur historis broker flow:** Penggerak utama saham lapis 2/3 seperti `VKTR` adalah akumulasi/distribusi bandar yang belum tersedia sebagai time-series historis.
3. **Biaya & slippage disederhanakan:** Asumsi flat round-trip fee `0.4%` mengabaikan spread bid-ask, antrean lot, dan auto-reject (ARA/ARB) di saham kurang likuid.
4. **Label tumpang tindih:** Horizon 5 hari membuat sampel harian berkorelasi serial; ukuran sampel efektif adalah `n / 5`.

## 7. Keputusan Adopsi ke Kode Produksi (Langkah 8)
- **Diadopsi (perbaikan kebenaran):**
  1. `market_feed.py`: Penanganan simbol berawalan `^` agar tidak ditambah `.JK`.
  2. `forecaster.py`: Purge gap `5` hari antara train dan test pada walk-forward OOS.
  3. `forecaster.py`: Threshold tunggal `0.58` pada backtest OOS dan klasifikasi `BULLISH`.
  4. `chart_renderer.py`: `bbox` gelap pada label `ML+5H` (kosmetik, bukan peningkatan akurasi) serta pelabelan kurva sebagai indikatif jika tidak mengalahkan baseline naif.
- **Ditolak / Dikembalikan ke versi sederhana:**
  - Perubahan kompleks (`HistGB` ensemble, 5 fitur tambahan, recency weighting) yang tidak terbukti mengalahkan model sederhana atau baseline terkuat secara konsisten pada paired test dan hold-out.