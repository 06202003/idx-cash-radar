# Laporan Backtest Kasus — Fase 5 (`reports/backtest.md`)

**Status Bukti:** **BUKTI TIDAK CUKUP**

Aturan terkunci di `docs/backtest_rules.md` diterapkan pada seluruh kejadian berita bertanggal terverifikasi di `data/daily_news_sentiment.json` dan `CURATED_DISCLOSURES` (tanpa cherry-picking, tanpa data sintetis).

## 1. Ringkasan Jumlah Kejadian

- Total berita `POSITIF` bertanggal terverifikasi: **4**
- Kelompok Uji (`TREATMENT_KAS_TERTEKAN`): **1** kejadian
- Kelompok Kontrol (`CONTROL_KAS_SEHAT`): **1** kejadian

## 2. Hasil Excess Return vs IHSG (`^JKSE`, Adjusted Close)

| Kelompok | Horizon | N Valid | Median Excess Return | Rata-rata Excess Return | Hit Rate (`Excess < 0`) |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `TREATMENT_KAS_TERTEKAN` | 5 Hari | 0 | N/A | N/A | N/A |
| `TREATMENT_KAS_TERTEKAN` | 20 Hari | 0 | N/A | N/A | N/A |
| `TREATMENT_KAS_TERTEKAN` | 60 Hari | 0 | N/A | N/A | N/A |
| `CONTROL_KAS_SEHAT` | 5 Hari | 0 | N/A | N/A | N/A |
| `CONTROL_KAS_SEHAT` | 20 Hari | 0 | N/A | N/A | N/A |
| `CONTROL_KAS_SEHAT` | 60 Hari | 0 | N/A | N/A | N/A |

## 3. Kejadian Kontra & Keterbatasan

- Tidak ada kejadian dengan horizon lengkap yang dapat dievaluasi sebagai kontra.

- **Survivorship Bias:** Universe 49 emiten hanya mencakup emiten yang masih tercatat/aktif; emiten yang delisting tidak masuk.
- **Keterbatasan Berita Historis:** `data/daily_news_sentiment.json` hanya menyimpan snapshot berita RSS terbaru (mayoritas belum memiliki horizon 20–60 hari bursa ke depan), sementara arsip Keterbukaan Informasi BEI historis 2020–2025 belum tersedia di repositori.

## 4. Draft Thread (Maks 8 Poin)

*(Draft thread dikosongkan sesuai aturan Fase 5 karena status = **BUKTI TIDAK CUKUP**: Treatment N=1, Control N=1, dan horizon 60 hari N=0 < 10.)*
