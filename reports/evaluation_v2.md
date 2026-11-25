# Audit Kuantitatif v2 (`idx-alert-bot`) — Protokol Terkoreksi, H1 & H2

**Commit Pra-Registrasi:** `89b2812f99d7657e93d193dd5196eb15611ced29` (`reports/prereg.md`)
**Snapshot Data:** `2026-11-25T03:08:22.532595+00:00` (`data_snapshot/manifest.json`, range `10y`)

## Ringkasan Eksekutif
1. **H1 (Volatilitas & Cone):** **TIDAK TERBUKTI** — kandidat terpilih `V2` pada `LOCK-RECENT` mencatat coverage 5H `68%`: `69.0%` dan `90%`: `89.7%` (QLIKE `-5.8284` vs `V0` `-5.6837`).
2. **H2 (Mean Reversion):** **H2 TIDAK TERBUKTI** — varian terpilih di `DISCOVERY`: `Tidak ada yang lolos koreksi Holm`.
3. **Perbandingan CI (Cacat a):** Pada `A1_th58` di `LOCK-RECENT`, CI lama (independen) adalah `(-1.7061, 1.5772)` sedangkan CI baru berkluster tanggal adalah `[-2.3008, 0.8848]` — CI lama terlalu sempit karena mengabaikan korelasi silang harian.
4. **Audit ulang v1 (Cacat d):** AUC `A0` dan `A1_th58` sebelumnya identik (`0.4728`) karena bug di `_eval_config_holdout` yang memaksa `holdout_start - HORIZON` (purge=5) untuk `A0` juga. Setelah diperbaiki, `A0` (tanpa purge) AUC=`0.532` vs `A1_th58` AUC=`0.5331`.
5. **Produksi:** Model direksional probabilistik v1 (`P(Naik 5H)`, `BULLISH/BEARISH/NETRAL`) dihapus dari tampilan default (disimpan di balik `LEGACY_ML_SIGNAL=False`) dan diganti indikator deskriptif.

## 1. Snapshot Data & Filter Likuiditas
- **Saham sebelum filter:** `28` | **Lolos filter likuiditas (median 60H >= Rp 5 Miliar):** `28` | **Dieliminasi:** `[]`
- **Bar mentah:** `66860` | **Lolos likuiditas:** `61954` (`FRESH-PAST`: `28966`, `DISCOVERY`: `29185`, `LOCK-RECENT`: `3528`).

## 2. Audit Ulang v1 pada `LOCK-RECENT` (Perbaikan Cacat a–f, Referensi Saja)
| Model | Sinyal (n_eff) | Non-Overlap n | AUC | Acc (Maj) | CI Independen (v1) | CI Kluster Tanggal (v2) | Excess vs EW Market (95% CI) | Random Matched (p2.5/p50/p97.5) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `A0` (true no-purge) | 377 (75.4) | 92 | 0.532 | 56.05% (56.73%) | (-1.1524, 1.4692) | [-1.954, 0.8079] | -0.8541% [-1.6841, -0.2877] | {'p2_5': -0.872, 'p50': -0.3892, 'p97_5': 0.1626} |
| `A1_th58` (purge=5) | 235 (47.0) | 59 | 0.5331 | 56.23% (56.73%) | (-1.7061, 1.5772) | [-2.3008, 0.8848] | -0.751% [-2.1866, 0.2821] | {'p2_5': -1.0408, 'p50': -0.4056, 'p97_5': 0.3127} |
- **Baseline Pasar `LOCK-RECENT`:** Equal-weight universe net = `-0.7601%` `[-1.9178, 0.5791]`; `^JKSE` net = `-0.9082%` `[-2.2802, 0.5403]`.
- **Non-overlapping `A1_th58` excess return:** `-1.9054%` `[-3.1016, -1.0711]`.

## 3. Pengujian H1: Prediksi Volatilitas & Cone Terkalibrasi
*Catatan: `V4` (GARCH(1,1)) dilewati karena pustaka `arch` tidak terpasang.* Total kandidat diuji: `7` (`V0, V1, V2, V3, V5, V6, V7`).

### Perbandingan Kandidat di `DISCOVERY`
| Kandidat | QLIKE | MAE log-vol | DM Loss Diff vs V0 (95% CI Kluster Tanggal) |
| :--- | ---: | ---: | :--- |
| `V0` | -6.5773 | 0.443 | 0.0 [0.0, 0.0] (p=1.0) |
| `V1` | -6.5936 | 0.4303 | -0.0161 [-0.0314, -0.0032] (p=0.014) |
| `V2` | -6.615 | 0.4338 | -0.0375 [-0.0484, -0.0279] (p=0.0) |
| `V3` | -6.5151 | 0.4148 | 0.0622 [0.0265, 0.0894] (p=0.0004) |
| `V5` | -6.4087 | 0.4136 | 0.1676 [0.1177, 0.212] (p=0.0) |
| `V6` | -6.5946 | 0.4121 | -0.0172 [-0.04, 0.0005] (p=0.0572) |
| `V7` | -6.5682 | 0.4072 | 0.009 [-0.0126, 0.0263] (p=0.4956) |

### Evaluasi Tunggal `LOCK-RECENT` (`V2` vs `V0`)
- **QLIKE:** `V2` = `-5.8284` vs `V0` = `-5.6837` | **DM Diff:** `-0.1446` `[-0.4201, -0.0074]`
- **Coverage Pooled +1..+5H (`V2`):** 68% = `{1: 71.5, 2: 71.3, 3: 69.6, 4: 68.7, 5: 69.0}` | 90% = `{1: 91.6, 2: 91.2, 3: 90.7, 4: 89.9, 5: 89.7}`
- **Coverage Pooled +5H (`V0`):** 68% = `67.7%` | 90% = `88.6%`
- **Saham individual dalam +-6 poin (`V2`):** 68% = `60.7%`, 90% = `96.4%`
- **Coverage bersyarat 68% (`V2`):** Vol Tinggi = `70.4%`, Vol Rendah = `64.0%`, IHSG Turun = `62.9%`
- **Skala empiris vs sqrt(h):** Empiris = `{1: 0.849, 2: 1.21, 3: 1.471, 4: 1.699, 5: 1.898}` vs `sqrt(h)` = `{1: 1.0, 2: 1.414, 3: 1.732, 4: 2.0, 5: 2.236}`

## 4. Pengujian H2: Mean Reversion (6 Varian, Koreksi Holm)
| Varian | Sinyal (n_eff) | Excess Return vs EW (95% CI Kluster) | p-val (p-Holm) | Random (p2.5/p50/p97.5) | % Thn Pos | % Saham Pos | Fee 0.6% / 1.0% | Open t+1 | Non-Overlap Excess |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `R1` | 3221 (644.2) | -0.3136% [-0.5988, 0.0062] | 0.056 (0.224) | -0.5479/-0.4037/-0.2525% | 33.3% | 53.6% | -0.5136% / -0.9136% | -0.3073% | -0.1004% [-0.3627, 0.2632] |
| `R2` | 1800 (360.0) | -0.0531% [-0.4399, 0.4302] | 0.9496 (1.0) | -0.6131/-0.4138/-0.218% | 50.0% | 60.7% | -0.2531% / -0.6531% | -0.044% | 0.1952% [-0.1303, 0.6611] |
| `R3` | 1431 (286.2) | -0.4046% [-0.7547, -0.019] | 0.0416 (0.208) | -0.6367/-0.403/-0.1145% | 83.3% | 42.9% | -0.6046% / -1.0046% | -0.3606% | -0.2376% [-0.5448, 0.1089] |
| `R4` | 1472 (294.4) | -0.2259% [-0.6279, 0.1575] | 0.2228 (0.6684) | -0.623/-0.4042/-0.1787% | 66.7% | 64.3% | -0.4259% / -0.8259% | -0.132% | -0.1956% [-0.6081, 0.1861] |
| `R5` | 4832 (966.4) | -0.3572% [-0.609, -0.0888] | 0.0076 (0.0456) | -0.5171/-0.4/-0.278% | 33.3% | 53.6% | -0.5572% / -0.9572% | -0.3803% | -0.1598% [-0.4432, 0.1472] |
| `R6` | 772 (154.4) | 0.0692% [-0.4634, 0.6096] | 0.846 (1.0) | -0.6985/-0.3909/-0.0858% | 83.3% | 57.1% | -0.1308% / -0.5308% | 0.1256% | 0.169% [-0.3084, 0.6375] |

- **Status H2:** `H2 tidak terbukti` — tidak ada varian yang lolos koreksi Holm di `DISCOVERY`, sehingga `FRESH-PAST` dan `LOCK-RECENT` tidak dievaluasi.

## 5. Keterbatasan
1. **Rezim pasar:** Data 10 tahun IDX tetap terikat siklus spesifik Indonesia dan tidak menjamin stabilitas di luar rezim tersebut.
2. **Tanpa broker flow historis:** Fitur hanya OHLCV; dinamika bandarmologi/asing belum dimodelkan.
3. **Biaya & likuiditas:** Meskipun ada filter median transaksi Rp 5 Miliar/hari dan sensitivitas fee 0.6%/1.0%, eksekusi riil tetap dipengaruhi spread bid-ask dan batas ARA/ARB.
4. **Korelasi silang & label tumpang tindih:** Ditangani dengan bootstrap berkluster tanggal (blok 10 hari) dan versi posisi tunggal tidak tumpang tindih.

## 6. Perubahan Produksi (Langkah 6)
- Menghapus `P(Naik 5H)`, label `BULLISH/BEARISH/NETRAL` berbasis model, dan skor probabilitas dari tampilan default (`LEGACY_ML_SIGNAL=False`).
- Mengganti ringkasan sinyal dengan indikator deskriptif non-probabilistik (RSI14, jarak MA20/MA50, posisi range 20H, rasio volume, volatilitas).
- Cone volatilitas pada chart: dihapus karena H1 tidak memenuhi kriteria adopsi.
- Sinyal mean reversion: tidak ditambahkan karena H2 tidak lolos konfirmasi penuh.