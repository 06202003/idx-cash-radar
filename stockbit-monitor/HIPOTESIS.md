# Hipotesis tabel bukti harian — ditetapkan 2026-11-22 (SEBELUM data dilihat)

Tabel: `data/evidence/YYYY-MM-DD.jsonl` (1 baris per saham per hari, lihat `evidence.py`).
Hasil diukur: `r1` (open besok → close besok) dan `r5` (open besok → close 5 hari bursa
kemudian), mentah dan relatif rata-rata universe (`rel1`, `rel5`). Sebelum biaya.

Aturan main:
- Hanya hipotesis di daftar ini yang dinilai "lolos/gagal". Kombinasi lain yang ketemu
  belakangan = ide baru, dicatat di bawah dengan tanggal, dan baru boleh dinilai di data
  SESUDAH tanggal itu.
- Minimal 20 hari bursa berbeda & 100 kejadian sebelum dinilai. t-stat per hari (bukan per
  kejadian). Lolos = |t| ≥ 2 DAN arah sama di dua paruh data.
- Kalau kondisi IHSG belum pernah "naik" selama periode data, hipotesis yang butuh kondisi
  itu ditunda, bukan dinilai gagal.

| # | Kombinasi | Dugaan | Hasil |
|---|---|---|---|
| H1 | Alert beli dominan (≥3, beli ≥2× jual) + broksum dijaga (konsentrasi 10h ≥45%) | rel5 lebih baik dari alert beli dominan tanpa dijaga | |
| H2 | Alert beli dominan + IHSG tren turun vs IHSG tren naik | rel1/rel5 lebih buruk saat IHSG tren turun | |
| H3 | Masuk watchlist + saham uptrend (harian) vs masuk watchlist + downtrend | uptrend lebih baik (r5) | |
| H4 | Pemicu adaptif C (penampung utama membuang) | rel5 negatif | |
| H5 | Pemicu adaptif D: akumulasi mulai SEBELUM harga naik vs SESUDAH | "sebelum" lebih baik (rel5) | |
| H6 | Kandidat tembok bid dicabut (WALL_PULLED sisi bid) di saham pantauan | rel1 negatif | |
| H7 | Saham dijaga (konsentrasi ≥45%): IHSG hari merah vs hijau | selisih return dijaga vs tidak dijaga mengecil saat IHSG hijau (efek "tahan turun") | |

## Klarifikasi definisi (2026-11-22, SEBELUM forward test mulai 2026-11-23)
- "Alert beli dominan" (H1, H2) hanya saham **likuid** menurut alert (ADV ≥ Rp1 M) dan harga
  ≥ Rp50. Alasan: uji coba paper menunjukkan saham Rp10-an rugi ±20% cuma dari 1 tick beli +
  1 tick jual — itu biaya spread, bukan informasi sinyal.
- Paper trading: `papertrade.py` aturan v1, mulai 2026-11-23, kertas saja.

## Ide baru (dinilai hanya di data sesudah tanggalnya)
_(kosong)_
