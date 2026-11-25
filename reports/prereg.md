# Pra-Registrasi Audit Kuantitatif v2 (`idx-alert-bot`)

**Tanggal:** 2026-11-25  
**Status:** Didaftarkan di muka sebelum pengunduhan snapshot dan sebelum menjalankan evaluasi apa pun.  
**Prinsip:** Tidak ada perubahan hipotesis, parameter, atau kriteria adopsi setelah melihat hasil. Penyimpangan (bila terpaksa karena kendala teknis) dicatat sebagai catatan terpisah.

---

## 1. Universe & Filter Likuiditas
- **Universe:** 28 saham IDX (`VKTR`, `BBCA`, `BBRI`, `ADRO`, `ANTM`, `BRIS`, `BMRI`, `BBNI`, `TLKM`, `ISAT`, `EXCL`, `ASII`, `UNTR`, `PTBA`, `ITMG`, `INCO`, `MEDC`, `PGAS`, `AKRA`, `ICBP`, `INDF`, `MYOR`, `KLBF`, `AMRT`, `MAPI`, `UNVR`, `CPIN`, `SMGR`) + indeks `^JKSE`.
- **Snapshot Data:** Unduh maksimal `10y` OHLCV harian dari Yahoo Finance satu kali ke `data_snapshot/` beserta tanggal unduh dan hash SHA256. *(Catatan teknis lingkungan: karena `pyarrow`/`fastparquet` tidak terpasang, snapshot disimpan dalam format CSV terkompresi `.csv.gz` atau `.csv` dengan SHA256 manifest, tetap dibekukan dan dibaca offline).*
- **Filter Likuiditas Tetap:** Baris pada tanggal `t` lolos filter jika **median nilai transaksi harian 60 hari (`close * volume`) sampai `t` >= Rp 5.000.000.000** (Rp 5 Miliar). Saham atau hari di bawah ambang ini dieliminasi dan jumlahnya dilaporkan.

## 2. Pembagian Segmen Waktu (Ketat, Tidak Boleh Dicampur)
Untuk setiap saham (setelah mengunduh hingga `10y` data):
1. **`LOCK-RECENT`:** `126` hari bursa terakhir (~6 bulan). Catatan: 63 hari terakhir sudah terlihat di audit v1 untuk model direksional. Dievaluasi **SEKALI** di akhir untuk H1 dan H2.
2. **`DISCOVERY`:** Jendela `5 tahun` dari audit v1 dikurangi `126` hari bursa terakhir, dengan jeda purge `5` hari sebelum `LOCK-RECENT`. Dipakai untuk memilih kandidat H1 dan varian H2 (walk-forward bersarang, purge `5` hari).
3. **`FRESH-PAST`:** Seluruh data yang lebih lama dari jendela `5 tahun` v1 (dengan jeda purge `5` hari sebelum `DISCOVERY`). Belum pernah dianalisis. Dipakai **HANYA** untuk konfirmasi H2, dievaluasi **SEKALI**. Jika suatu saham tidak memiliki `>= 120` baris pada `FRESH-PAST` atau total sampel `FRESH-PAST` terlalu kecil (`< 500` baris pooled), status H2 otomatis diturunkan menjadi **"eksploratori, tidak terkonfirmasi"** apa pun hasilnya.

## 3. Protokol Statistik & Baseline
- **Bootstrap Berkluster Tanggal:** Agregasikan return (atau metrik) per tanggal lintas saham (*equal-weight*), lalu lakukan *moving block bootstrap* atas tanggal dengan panjang blok `10` hari bursa dan `5000` resample (`seed=42`).
- **Baseline Acak:** Frekuensi sinyal identik dengan strategi yang dibandingkan pada segmen yang sama, `500` seed, melaporkan persentil `2.5 / 50 / 97.5`.
- **Baseline Pasar:** Return *equal-weight* seluruh universe yang lolos filter likuiditas pada tanggal yang sama, dan return `^JKSE`. Return strategi dilaporkan sebagai **excess return** terhadap *equal-weight* universe (netralisasi beta).
- **Entry & Biaya (No Look-Ahead):** Fitur pada hari `t` hanya memakai data hingga penutupan `t`. Entry utama H2 = `close[t+1]`, exit = `close[t+6]` (holding 5 hari bursa). Sensitivitas entry = `open[t+1]` ke `close[t+6]`. Biaya round-trip utama = `0.4%`, sensitivitas = `0.6%` dan `1.0%`.

---

## 4. Hipotesis H1: Prediksi Volatilitas 5 Hari & Cone Terkalibrasi
- **Pernyataan:** Volatilitas 5 hari ke depan dapat diprediksi dari OHLCV lebih baik daripada volatilitas historis konstan, dan cone berpusat di `0` (garis datar) dapat dikalibrasi ke coverage nominal `68%` dan `90%` (toleransi `+-3` poin).
- **Kandidat (maksimal 8):**
  - `V0`: Std historis 60 hari konstan (baseline)
  - `V1`: EWMA `lambda = 0.94`
  - `V2`: EWMA `lambda = 0.97`
  - `V3`: Estimator range Garman-Klass rolling 20 hari
  - `V4`: GARCH(1,1) — dilewati karena pustaka `arch` tidak tersedia di lingkungan
  - `V5`: HAR sederhana (vol 1/5/22 hari, regresi Ridge `alpha=10.0`, fit walk-forward dengan purge 5 hari)
  - `V6`: Campuran `0.5 * V1 + 0.5 * V3`
  - `V7`: Campuran `0.5 * V1 + 0.5 * V5`
- **Target & Metrik:** Target = realized vol harian 5 hari ke depan (`sqrt(mean(r_{t+1..t+5}^2))`). Metrik: **QLIKE**, **MAE log-vol**, uji **Diebold-Mariano berpasangan** terhadap `V0` dengan bootstrap berkluster tanggal.
- **Cone:** Titik tengah = `0` (tidak ada prediksi arah). Lebar horizon `h` (`+1..+5`) = `pred_sigma_t * empirical_quantile(standardized_residuals_h)` dari jendela expanding kausal sebelum `t` (dengan purge `h` hari, minimal 60 sampel).
- **Kriteria Lolos H1 (SEMUA harus terpenuhi di `LOCK-RECENT`):**
  1. Coverage `68%` dan `90%` berada dalam `+-3` poin pada pooled `LOCK-RECENT`, DAN minimal `70%` saham individual berada dalam `+-6` poin;
  2. QLIKE lebih baik daripada `V0` dengan CI 95% selisih tidak mencakup nol (ATAU bila setara, cone kandidat memenuhi coverage sementara cone `V0` tidak).

---

## 5. Hipotesis H2: Mean Reversion Jangka Pendek
- **Pernyataan:** Setelah penurunan/oversold jangka pendek, return 5 hari ke depan lebih tinggi daripada baseline pasar (*equal-weight* universe) setelah biaya.
- **Varian Aturan (6 varian tetap, tanpa grid, koreksi Holm):**
  - `R1`: `RSI14 < 30`
  - `R2`: `RSI14 < 25`
  - `R3`: `ret_3d < -1.5 * sqrt(3) * sigma_ewma_94` (sigma harian kausal EWMA 0.94)
  - `R4`: `close < lower_bollinger(20, 2)` (`MA20 - 2 * std20`)
  - `R5`: `(close - MA20) < -1.5 * ATR14`
  - `R6`: `R3` DAN `RSI14 < 35`
- **Prosedur:**
  1. Evaluasi `R1..R6` di `DISCOVERY` dengan koreksi **Holm-Bonferroni** pada p-value bootstrap berkluster tanggal atas excess return.
  2. Pilih paling banyak **SATU** varian terbaik yang lolos koreksi Holm (`p_holm < 0.05`). Jika tidak ada yang lolos, hentikan dan laporkan **"H2 tidak terbukti"**.
  3. Jika ada yang lolos, evaluasi varian tersebut **SEKALI** di `FRESH-PAST` dan **SEKALI** di `LOCK-RECENT`.
- **Kriteria Lolos H2 (SEMUA harus terpenuhi):**
  1. Excess net return di `FRESH-PAST` positif dengan batas bawah CI 95% berkluster tanggal `> 0`;
  2. Tanda excess return positif di `DISCOVERY` dan `LOCK-RECENT`;
  3. Minimal `60%` tahun kalender bernilai excess return positif;
  4. Tetap positif pada biaya `0.6%`;
  5. Mengalahkan persentil `97.5` baseline acak berfrekuensi sama;
  6. Efek tidak hilang pada entry `open[t+1]`.
  *(Jika `FRESH-PAST` tidak tersedia/memadai, status H2 otomatis menjadi **"eksploratori, tidak terkonfirmasi"**).*
