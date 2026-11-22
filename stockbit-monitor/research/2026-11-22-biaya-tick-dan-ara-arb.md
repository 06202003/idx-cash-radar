# Riset 2026-11-22: biaya tick (layak scalping) & rentetan ARA/ARB

Data: harian Yahoo, 442 saham (cache bot, 1 tahun; 216 saham universe 2 tahun), s.d. 2026-11-20.
Catatan: universe 216 bot TIDAK memuat big cap (BBCA/BBRI/TLKM/BMRI/ASII) — isinya mayoritas
saham kecil-menengah. Survivorship: hanya saham yang masih ada sekarang.

## 1. Biaya tick vs gerak harian (`scalp_cost.py`)
Titik impas 1 kali scalping = 1 tick spread + fee 0,4% (0,15% beli + 0,25% jual).
Rasio = titik impas / median range harian (high-low) 60 hari terakhir. Makin kecil makin layak.

| Pita harga | tick | impas | range harian | rasio |
|---|---|---|---|---|
| < Rp200 | 1,24% | 1,64% | 6,6% | 0,27 |
| Rp200–500 | 0,63% | 1,03% | 5,3% | 0,20 |
| Rp500–2.000 | 0,54% | 0,94% | 3,7% | 0,25 |
| Rp2.000–5.000 | 0,36% | 0,76% | 3,6% | 0,22 |
| ≥ Rp5.000 | 0,36% | 0,76% | 3,1% | 0,22 |

- Paling layak (likuid ≥ Rp10 M/hari): SINI, TEBE, ASLI, ARKO, KETR, PACK, CSMI, PKPK, INET, RATU, PTRO.
- Tidak layak: **GOTO** (Rp27, tick 3,7% → impas 4,1% > range harian 3,8%: secara struktur mustahil
  untung scalping lewat spread), BNBR, ULTJ, CMNT, AYAM, UNVR, BBCA (range cuma 2,5%).
- Range harian periode ini membesar karena pasar anjlok; spread nyata di saham tipis bisa > 1 tick
  (cek dari data orderbook mulai 2026-11-23).

## 2. Rentetan ARA/ARB (`ara_arb_chains.py`)
Hari terkunci = O=H=L=C dengan |ret| ≥ 5% (dideteksi dari data; batas auto-reject berubah selama
periode: mayoritas ±10%, sempat −15%, sejak Okt 2026 dominan −7%).

**Risiko ARB (saham likuid ≥ Rp1 M/hari, 359 kejadian):**
- Sekali kena ARB terkunci: 38% lanjut ≥ 2 hari, 10% ≥ 3 hari.
- Rugi sampai PALING CEPAT bisa jual (open hari pertama tidak terkunci, dihitung dari close sebelum
  ARB pertama): median **−17,7%**, 10% terburuk **−28%**. Rentetan 1 hari −12,9%, 2 hari −25%, 3+ −31%.
- Tanda awal (lemah): naik ≥ 30% dalam 20 hari sebelum ARB → P(≥ 3 hari) 16% vs 8% kalau naik < 10%.
  IHSG tren turun → P(≥ 2 hari) 43% vs 35% saat IHSG naik.

**Pantulan sesudah ARB — TIDAK layak.** Versi awal (+6,8%) bocor info masa depan (memilih "hari
pertama lepas kunci"). Tanpa bocoran: setelah hari terkunci ARB, beli open kalau gap ≤ −5%:
45% ternyata terkunci ARB lagi (terjebak), median −1,3%, cuma 37% untung (24% di luar krisis
Okt–Nov 2026); rata-rata +2,4% cuma ditarik segelintir pantulan besar.

**Kejar sesudah ARA — negatif, konsisten.** Beli open sesudah hari terkunci ARA (likuid):
sesudah ARA ke-1 −2,2%/hari (t −3,3), ke-2 −4,2% (t −4,6), ke-3+ −3,4% (t −3,7); untung cuma 7–13%.
38–51% terkunci ARA lagi (praktis tidak terisi), sisanya rugi.

Semua temuan di atas dari data LAMA → dicatat sebagai ide bertanggal di HIPOTESIS.md, sah setelah
lolos di data sesudah 2026-11-22.
