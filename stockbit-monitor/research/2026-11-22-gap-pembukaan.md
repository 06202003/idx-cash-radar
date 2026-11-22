# Riset 2026-11-22: gap pembukaan (`gap_open.py`)

Data: harian Yahoo 442 saham (Des 2024 – 19 Nov 2026), saham likuid (median nilai 20 hari ≥ Rp1 M)
dan harga ≥ Rp50: 91.663 saham-hari. Kelompok dari gap = open / close kemarin − 1 (diketahui saat
open). Hari terkunci ARA = beli tidak terisi; terkunci ARB = baru bisa jual open besok. t-stat per hari.

## Temuan
1. **Beli open → jual close itu rugi secara struktur.** Gap datar (±0,5%): mentah −0,15%, tapi setelah
   2 tick + fee −1,9%. Biaya pulang-pergi ±1,7% di saham-saham ini; edge intraday harus lebih besar dari itu.
2. **Gap naik ≥ +5% cenderung turun sampai close** (sudut pandang pemegang barang, tanpa biaya):
   median −2,1%, cuma 34% naik; paruh 2025 median −0,6%, paruh 2026 −2,8%; negatif di semua tren IHSG
   (naik −1,1%, samping −3,0%, turun −2,8% rata-rata). Gap +2..+5%: −0,7% (lemah, positif saat IHSG naik).
   → Pemegang barang yang gap naik besar: jual di open historis lebih baik dari tahan s.d. close;
     yang belum punya: jangan beli di open.
3. **Gap turun ≤ −5%: tidak ada edge.** Mentah rata-rata +1,5% tapi median 0%; setelah 1 tick + fee
   median −1,0%, untung 41%; 19% terkunci ARB seharian. (Kalau cuma lihat yang TIDAK terkunci, kelihatan
   +3,5% — itu bocoran info akhir hari, jangan dipakai.)
4. **Saat IHSG sendiri buka gap ≥ +1%**, saham yang buka datar cenderung naik s.d. close (mentah +1,0%),
   gap IHSG ≤ −1% sebaliknya (−1,5%). Hanya ±18–22 hari → keyakinan rendah.

Semua dari data LAMA → ide bertanggal I4–I6 di HIPOTESIS.md.
