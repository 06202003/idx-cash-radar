# Aturan Backtest Terkunci — Fase 5 (`docs/backtest_rules.md`)

> **Status:** DIBEKUKAN sebelum penarikan data harga historis (`adjusted close` Yahoo Finance `.JK` dan `^JKSE`).

## 1. Definisi Kelompok Uji (Treatment): "Berita Positif + Kas Tertekan"
Sebuah kejadian berita/keterbukaan informasi masuk ke kelompok uji apabila memenuhi **seluruh** syarat berikut pada tanggal publikasi `t0`:
1. **Sentimen Berita = `POSITIF`:** Diklasifikasikan secara deterministik oleh `analyze_sentiment_deterministic` (`sentiment == "POSITIF"`).
2. **Tanggal Terverifikasi:** Memiliki tanggal publikasi spesifik (`YYYY-MM-DD`, bukan sekadar `"Terbaru"` atau bulan tanpa tanggal) dan dapat dipetakan ke hari bursa `t0` (`>= tanggal publikasi`).
3. **Kas Tertekan pada Laporan XBRL Terbaru yang Tersedia Sebelum/Pada `t0`:** Memenuhi minimal satu kondisi deterministik berikut pada `computed_metrics`:
   - `cfo_ttm_idr < 0`, **ATAU**
   - `flag_acute_liquidity == 1`, **ATAU**
   - `debt_free_short_term == 0` dan `cash_coverage_ratio < 0.25`.

## 2. Definisi Kelompok Kontrol (Control): "Berita Positif + Kas Sehat"
Memenuhi syarat (1) dan (2) di atas, dengan kondisi kas pada laporan XBRL:
- `cfo_ttm_idr > 0`, **DAN**
- `flag_acute_liquidity == 0`, **DAN**
- (`debt_free_short_term == 1` **ATAU** `cash_coverage_ratio >= 1.0`).

## 3. Definisi Return & Horizon Evaluasi
- **Sumber Harga:** Yahoo Finance (`TICKER.JK` dan `^JKSE`), menggunakan **Adjusted Close**.
- **Hari Bursa `t0`:** Hari perdagangan pertama pada atau setelah tanggal publikasi berita.
- **Horizon:** `H = 5`, `20`, `60` hari bursa setelah `t0`.
- **Excess Return vs IHSG:** `R_excess(H) = (P_adj(t0 + H) / P_adj(t0) - 1) - (IHSG_adj(t0 + H) / IHSG_adj(t0) - 1)`.
- **Hit Rate (Hipotesis Konservatif):** Proporsi kejadian kelompok uji di mana `R_excess(H) < 0` (underperform IHSG setelah berita positif karena kas tertekan).

## 4. Batasan & Kriteria Kecukupan Bukti
- Jika jumlah kejadian `n < 10` per kelompok atau horizon `60` hari bursa belum tersedia untuk mayoritas berita terbaru, sistem **wajib** melaporkan `"BUKTI TIDAK CUKUP"` dan mengosongkan draf *thread*.
- **Survivorship Bias:** Universe 49 emiten saat ini hanya mencakup emiten yang masih tercatat/aktif datanya; emiten yang sudah delisting tidak termasuk.
