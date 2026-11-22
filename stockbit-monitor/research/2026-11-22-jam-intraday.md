# Riset 2026-11-22: jam intraday (`intraday_time.py`)

Data: bar 5 menit Yahoo, 60 hari bursa (31 Agu – 20 Nov 2026, pasar mayoritas turun/samping),
233 saham likuid (median nilai 20 hari ≥ Rp1 M) & harga ≥ Rp50, + IHSG. Jam WIB. t-stat per hari.
Titik impas per bar = 1 tick + fee 0,4%. Porsi nilai per slot = perkiraan kasar (jadwal Jumat beda,
jumlahnya jadi ±106%).

## Temuan
1. **Gerak yang cukup buat menutup biaya cuma ada di awal sesi.** Range 1 bar 5 menit dibanding titik
   impas (median): 09:05 1,15×, 09:10 0,95×, 09:15 0,87×; sesudah 09:30 tinggal 0,6–0,7×. Naik lagi
   sedikit di awal sesi 2 (13:30 0,72×) & menjelang tutup (15:45 0,71×). Di luar jam itu, satu gerak
   5 menit rata-rata tidak menutup ongkos — scalping butuh gerak beberapa bar.
2. **Keramaian:** ±16% nilai harian di 25 menit pertama, ±29% s.d. 10:00, ±56% s.d. akhir sesi 1.
   Lelang penutupan ±5%.
3. **Dorongan menjelang tutup lalu balik di lelang:** bar 15:45 rata-rata +0,061% (t +4,9), lalu
   lelang penutupan −0,047% (t −3,4). Pola paling konsisten di data ini, tapi ukurannya kecil
   dibanding biaya (±1%) → informasi, bukan strategi: jangan beli di dorongan 15:45; yang mau jual
   historis lebih baik di dorongan itu daripada di harga lelang.
4. **Awal sesi 2 cenderung turun** (bar 13:30 −0,07%, t −2,2). Lintas istirahat sendiri netral.
5. **30 menit pertama cenderung berbalik:** saham paling turun s.d. 09:30 (kuintil bawah) sisa hari
   +0,24% vs saham lain (t +2,4); paling naik −0,18% (t −1,8). Searah temuan gap naik. Kecil vs biaya.

Semua dari data LAMA & periode pasar turun → ide bertanggal I7–I8 di HIPOTESIS.md.
