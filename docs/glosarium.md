# Glosarium Istilah — IDX Cash & Accrual Radar

Pemetaan istilah teknis akuntansi/keuangan ke bahasa ritel yang mudah dipahami pada **Simple Mode (Retail)**. Istilah teknis tetap tersedia ketika pengguna mengaktifkan **Expert Mode (Pro Analyst)**.

| Istilah Teknis (Expert Mode) | Bahasa Ritel (Simple Mode) | Penjelasan Singkat & Sumber |
| :--- | :--- | :--- |
| **Cash-to-Short-Term Debt Coverage** (`cash_coverage_ratio`) | **Kas dibanding utang jangka pendek** | Perbandingan kas & setara kas terhadap utang berbunga yang jatuh tempo dalam 12 bulan. Nilai `< 1.0x` berarti kas lebih kecil dari utang jangka pendek; `< 0.20x` memicu penanda likuiditas ketat. |
| **Sloan Accrual Ratio (TTM)** (`sloan_ratio_ttm`) | **Laba di atas kertas vs kas yang benar-benar masuk** | Selisih antara Laba Bersih TTM dan Arus Kas Operasi (CFO) TTM dibagi rata-rata total aset. Nilai positif tinggi (`> +10%`) menandakan porsi laba yang belum berbentuk kas riil. |
| **Operating Cash Flow / CFO (TTM)** (`cfo_ttm_idr`) | **Kas masuk dari operasional (12 bulan terakhir)** | Uang kas bersih yang benar-benar masuk (atau keluar jika negatif) dari aktivitas bisnis utama selama 4 kuartal terakhir. |
| **Net Income (TTM)** (`net_income_ttm_idr`) | **Laba bersih akuntansi (12 bulan terakhir)** | Laba/rugi bersih pada laporan laba rugi 4 kuartal terakhir (berbasis akrual, belum tentu semuanya sudah diterima tunai). |
| **FLAG_ACCRUAL_DIVERGENCE** | **Penanda: Laba kertas, kas operasi negatif** | Aktif secara deterministik jika Laba TTM `> 0`, tetapi CFO TTM `< 0`, CFO kuartal tunggal `< 0`, dan rasio akrual `> 10%`. |
| **FLAG_ACUTE_LIQUIDITY** | **Penanda: Tekanan likuiditas kas jangka pendek** | Aktif secara deterministik jika CFO TTM `< 0`, emiten memiliki utang jangka pendek berbunga (`> 0`), dan rasio kas dibanding utang jangka pendek `< 0.20x`. |
| **PSAK 72 Contract Exposure** | **Tagihan & aset kontrak proyek vs uang muka** | Rasio piutang usaha + aset kontrak dikurangi liabilitas kontrak (uang muka proyek) terhadap pendapatan 12 bulan terakhir. |
| **YTD -> TTM Decumulation** | **Konversi laporan kumulatif ke 12 bulan terakhir** | Mengubah angka laporan kuartalan kumulatif (3M, 6M, 9M, 12M) menjadi kinerja 12 bulan berjalan (*Trailing Twelve Months*). |
| **Contextual Isolation Rule** | **Berita tidak mengubah penanda kas** | Sentimen berita (positif/netral/perhatian) hanya konteks tambahan dan tidak pernah menghapus penanda bahaya kas dari laporan XBRL. |

> **Catatan Keterbatasan:** Seluruh data akuntansi bersifat **historis dan tertinggal** (*lagged*), mengikuti tanggal pelaporan kuartalan/tahunan resmi BEI (`period_end_date`), dan **bukan** merupakan rekomendasi investasi atau ajakan beli/jual.
