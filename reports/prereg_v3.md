# Pra-Registrasi Audit Kuantitatif v3 (`idx-alert-bot`)

**Tanggal:** 2026-11-25  
**Status:** Didaftarkan dan di-commit sebelum evaluasi tunggal pada segmen `FRESH-PAST`.  
**Data:** Membaca eksklusif dari `data_snapshot/` (tanpa unduh ulang). `LOCK-RECENT` dilarang dipakai untuk konfirmasi baru.

---

## 1. Catatan Bias Penyintas (*Survivorship Bias*)
Universe terdiri dari 28 saham yang **likuid hari ini** (2026). Saham yang dulunya likuid namun kemudian bangkrut, delisting, atau menjadi tidak likuid tidak termasuk dalam sampel. Bias penyintas ini **cenderung menguntungkan strategi mean reversion** (karena saham yang bertahan cenderung memantul setelah penurunan tajam, sedangkan yang gagal tidak tercatat).

---

## 2. Hipotesis H1' (Cone Volatilitas pada `FRESH-PAST`)
- **Kandidat:** `V0` (std historis 60 hari) vs **`V2`** (EWMA `lambda=0.97`, pemenang `DISCOVERY` dengan QLIKE `-6.6150` vs `V5_log_jensen` `-6.6108` serta lebih sederhana).
- **Titik tengah cone:** `0` (garis datar, tanpa klaim arah). Lebar menggunakan skala `sqrt(h)` x `V2` x kuantil empiris kausal residual terstandar.
- **Kriteria Lolos H1' di `FRESH-PAST` (SEMUA harus terpenuhi):**
  1. **Coverage pooled:** level `68%` dan `90%` berada dalam `+-3` poin untuk setiap horizon `+1..+5`.
  2. **Per saham (5H):** uji binomial dua sisi memakai `n_eff = n / 5` pada `alpha = 0.05`; tidak lebih dari `2 * alpha` (`10%`) saham yang menolak nominal `68%` dan `90%`.
  3. **Ketajaman (*Sharpness*):** *Winkler interval score* dan lebar rata-rata cone kandidat `<= V0` pada coverage setara, dengan CI selisih berkluster tanggal (`block_size=10`, `5000` resample).
  4. **Coverage bersyarat:** pada rezim vol tinggi, vol rendah, dan saat IHSG turun (`ret_5d < 0`), coverage 68% dan 90% berada dalam `+-6` poin pooled.

---

## 3. Hipotesis H2' (Satu Varian Mean Reversion pada `FRESH-PAST`)
- **Aturan Seleksi dari `DISCOVERY`:** Memilih antara `R2` (`RSI14 < 25`) atau `R6` (`R3 & RSI14 < 35`) berdasarkan **batas bawah CI 95% berkluster tanggal tertinggi pada gross excess** (seri → pilih `R2` karena lebih sederhana).
  - Hasil `DISCOVERY` (gross excess, simetris tanpa fee): `R2` CI `[-0.0399%, +0.8302%]`, `R6` CI `[-0.0634%, +1.0096%]`.
  - **Varian terpilih untuk diuji SEKALI di `FRESH-PAST`:** **`R2` (`RSI14 < 25`)**.
- **Pernyataan:** Gross excess return 5 hari `R2` terhadap *equal-weight* universe (fee simetris) bernilai `> 0`. Entry utama `close[t+1]`, exit `close[t+6]`.
- **Kriteria Lolos H2' di `FRESH-PAST` (SEMUA harus terpenuhi):**
  1. Batas bawah CI 95% berkluster tanggal pada **gross excess** `> 0` (net excess dengan fee `0.4%` hanya pada strategi dilaporkan terpisah).
  2. Mengalahkan persentil `97.5` baseline acak berfrekuensi identik (`500` seed).
  3. Minimal `60%` tahun kalender memiliki gross excess positif.
  4. Efek bertahan positif pada entry `open[t+1]`.
  5. Hasil versi non-overlapping (posisi tunggal per saham) tidak berlawanan tanda (tetap `> 0`).
- **Penutupan Topik:** Jika `H2'` gagal (hasil nol/tidak lolos kriteria di atas), **topik mean reversion ditutup** dan tidak ada varian lain yang akan dicoba.
