# Audit Kuantitatif v3 (`idx-alert-bot`) — Koreksi v2 & Uji Sekali pada `FRESH-PAST`

**Commit Pra-Registrasi v3:** `080ce1770cb408753542e0b124f03091817b4a79` (`reports/prereg_v3.md`)
**Snapshot Data:** `2026-11-25T03:08:22.532595+00:00` (`data_snapshot/manifest.json`)

## Ringkasan Eksekutif
1. **H1' (Cone Volatilitas `V2` vs `V0` di `FRESH-PAST`):** **LOLOS PENUH** — kriteria: pooled=True, binomial_n_eff=True, sharpness=True, bersyarat=True.
2. **H2' (Mean Reversion `R2` di `FRESH-PAST`):** **TIDAK TERBUKTI (TOPIK DITUTUP)** — `n=1893` (`n_eff=378.6`), gross excess=`0.062%` `[-0.4918, 0.5862]`.
3. **Koreksi CI v2 (A1):** Saat dihitung pada kuantitas yang sama (rata-rata per sinyal), CI kluster tanggal (`2.8622`) lebih lebar dari CI independen (`2.6494`) untuk `A1_th58` dan pada data sintetis berkorelasi (`0.4754` vs `0.292`).
4. **Koreksi V5 HAR (Step B):** Bug Jensen's inequality (`exp(E[log sigma])` tanpa `+0.5*var_res`) menyebabkan bias `-0.00275` dan QLIKE `-6.4087`; setelah diperbaiki QLIKE menjadi `-6.6108`, namun `V2` (`-6.6150`) tetap unggul dan lebih sederhana.
5. **Produksi:** Model probabilistik v1 tetap dimatikan (`LEGACY_ML_SIGNAL=False`); cone hanya ditampilkan bila H1' lolos penuh dan sinyal mean reversion hanya ditambahkan bila H2' lolos penuh.

## 1. Koreksi Laporan v2 (A1–A6 & B)
### A1. Perbandingan CI Lama vs Kluster Tanggal (Kuantitas Identik: Per-Sinyal Excess Return di `LOCK-RECENT`)
- **`A0`:** Independen = `(-1.6852, 0.3041)` (lebar `1.9893`) | Kluster Tanggal = `[-1.6668, 0.0718]` (lebar `1.7386`).
- **`A1_th58`:** Independen = `(-2.1355, 0.5139)` (lebar `2.6494`) | Kluster Tanggal = `[-2.3301, 0.532]` (lebar `2.8622`).
- **Data Sintetis Berkorelasi (20 saham x 100 hari, shock bersama):** Lebar Independen = `0.292` vs Lebar Kluster Tanggal = `0.4754`.
*Catatan: Di v2 sebelumnya, pusat interval bergeser karena `date_clustered_bootstrap_ci` mengambil equal-weight per tanggal sementara `independent_bootstrap_ci` mengambil equal-weight per sinyal.*

### A2 & A3. Hasil Holm Dua Sisi & Gross Excess `R1..R6` (`DISCOVERY`, Fee Simetris)
*Penyimpangan prereg v2 yang dikoreksi: `R5` memiliki `p_holm = 0.0456` pada net excess **negatif** (`-0.3572%`); laporan v2 sebelumnya menafsirkannya secara satu sisi tanpa mencatat penyimpangan.*

| Varian | n (n_eff) | Gross Excess vs EW (95% CI Kluster) | p-val (p-Holm 2-sisi) |
| :--- | ---: | ---: | ---: |
| `R1` | 3221 (644.2) | +0.0864% [-0.1988, +0.4062] | 0.5224 (1.0) |
| `R2` | 1800 (360.0) | +0.3469% [-0.0399, +0.8302] | 0.0816 (0.4896) |
| `R3` | 1431 (286.2) | -0.0046% [-0.3547, +0.3810] | 0.9948 (1.0) |
| `R4` | 1472 (294.4) | +0.1741% [-0.2279, +0.5575] | 0.4432 (1.0) |
| `R5` | 4832 (966.4) | +0.0428% [-0.2090, +0.3112] | 0.686 (1.0) |
| `R6` | 772 (154.4) | +0.4692% [-0.0634, +1.0096] | 0.0816 (0.4896) |

### A4. Penjelasan Selisih Overlap vs Non-Overlap `A1_th58` (`LOCK-RECENT`)
- Sinyal pertama tiap episode (`pos_1`): `n=45`, mean=`-1.3837%`, CI=`(-3.122, -0.6525)`.
- Sinyal lanjutan dalam episode (`pos_2plus`): `n=190`, mean=`-0.6464%`, CI=`(-2.1566, 0.68)`.

### A5. CI Kluster Tanggal untuk AUC di `LOCK-RECENT`
- **`A0`:** AUC = `0.532` (95% CI: `[0.5008, 0.5752]`, mencakup `0.50` -> tidak terbukti beda dari acak).
- **`A1_th58`:** AUC = `0.5331` (95% CI: `[0.5016, 0.5767]`); selisih `A1_th58 - A0` = `0.0011` `[-0.0002, 0.003]` (mencakup 0 -> tidak terbukti berbeda).

### A6. Kesimpulan Skala `sqrt(h)`
- Rasio skala empiris terhadap `+1H` di v2 (`1.425 / 1.733 / 2.001 / 2.236`) cocok dengan `sqrt(h)` (`1.414 / 1.732 / 2.000 / 2.236`), sehingga **tidak diperlukan koreksi skala**.

### Step B. Audit Bug V5 (HAR) di `DISCOVERY`
| Model | QLIKE | MAE log-vol | Mean Bias | DM Diff vs V0 (95% CI) |
| :--- | ---: | ---: | ---: | :--- |
| `V0` | -6.5773 | 0.443 | +0.00189 | +0.0000 [+0.0000, +0.0000] |
| `V2` | -6.615 | 0.4338 | +0.00194 | -0.0375 [-0.0484, -0.0279] |
| `V5_old_no_jensen` | -6.4087 | 0.4136 | -0.00275 | +0.1676 [+0.1179, +0.2120] |
| `V5_fixed_jensen` | -6.6108 | 0.4464 | +0.00233 | -0.0336 [-0.0596, -0.0111] |
| `V5_HAR_OLS_level` | 53.6246 | 0.4223 | +0.00051 | +58.5641 [-0.0205, +185.6895] |

## 2. Evaluasi Sekali pada `FRESH-PAST`: H1' (`V2` vs `V0`)
- **Pooled Coverage 68% (+1..+5H):** `V2` = `{1: 67.5, 2: 67.5, 3: 67.9, 4: 67.2, 5: 67.1}` | `V0` = `{1: 68.0, 2: 67.6, 3: 68.5, 4: 67.9, 5: 67.7}`
- **Pooled Coverage 90% (+1..+5H):** `V2` = `{1: 89.6, 2: 89.6, 3: 89.3, 4: 89.1, 5: 88.8}` | `V0` = `{1: 89.8, 2: 89.8, 3: 89.7, 4: 89.4, 5: 89.0}`
- **Uji Binomial Per Saham (`n_eff = n/5`, alpha=0.05):** `V2` 68% reject `0.0%` (0/27), 90% reject `0.0%` (0/27).
- **Ketajaman (5H):** Lebar 68% `V2=10.108%` vs `V0=10.159%` (diff `-0.076%` `[-0.6572, 0.5738]`); Winkler 68% `V2=17.494%` vs `V0=17.68%` (diff `-0.1668%` `[-1.6888, 1.7761]`).
- **Ketajaman 90% (5H):** Lebar `V2=18.731%` vs `V0=19.015%` (diff `-0.3254%`); Winkler `V2=27.724%` vs `V0=28.458%` (diff `-0.6812%` `[-3.7716, 3.5718]`).
- **Coverage Bersyarat `V2`:** 68% = `{'hi_vol': 70.8, 'lo_vol': 62.7, 'jkse_dn': 65.5}` | 90% = `{'hi_vol': 91.4, 'lo_vol': 85.7, 'jkse_dn': 87.5}`.

## 3. Evaluasi Sekali pada `FRESH-PAST`: H2' (`R2: RSI14 < 25`)
- **Jumlah Sinyal:** `n=1893` (`n_eff=378.6`)
- **Gross Excess Return (fee simetris):** `+0.0620%` (95% CI Kluster Tanggal: `[-0.4918, +0.5862]`, `p=0.8724`)
- **Net Excess Return (fee 0.4% hanya pada strategi, terpisah):** `-0.3380%` `[-0.8918, +0.1862]`
- **Random Matched (500 seed):** `p2.5=-0.2918%`, `p50=-0.0659%`, `p97.5=0.48%`
- **Tahun Kalender Positif:** `60.0%` | **Entry `open[t+1]` Gross Excess:** `-0.0435%` | **Non-Overlap (`n=585`):** `-0.0514%` `[-0.7894, +0.5709]`

## 4. Keterbatasan & Perubahan Produksi
- **Keterbatasan:** Bias penyintas (universe 28 saham likuid hari ini), tanpa broker flow historis, asumsi eksekusi tanpa slippage/ARA/ARB.
- **Perubahan Produksi:** `LEGACY_ML_SIGNAL=False` dipertahankan; cone volatilitas `V2` ditampilkan (tanpa klaim arah); sinyal mean reversion tidak ditambahkan dan topik ditutup.