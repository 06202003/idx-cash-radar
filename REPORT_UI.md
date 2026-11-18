# REPORT_UI.md — Laporan Redesain UI Fase 7 (`fase-7-ui`)

## 1. Token Desain Akhir
- **Metafora:** Lembar kerja audit / rekening koran (*audit ledger*).
- **Palet Warna (Mode Terang Default, Mode Gelap Opsional):**
  - `--kertas`: `#FAF8F5` (gelap `#141413`) — latar halaman utama
  - `--lembar`: `#FFFFFF` (gelap `#1C1C1A`) — permukaan tabel & panel
  - `--tinta`: `#18181B` (gelap `#F4F3EF`) — teks utama & angka positif
  - `--catatan`: `#52525B` (gelap `#A1A1AA`) — keterangan sekunder & tanggal laporan
  - `--garis`: `#E4E0D8` (gelap `#2E2E2A`) — pembatas tabel/baris
  - `--aksi`: `#1D4ED8` (gelap `#60A5FA`) — tombol aksi utama, tautan, ring fokus keyboard
  - `--negatif`: `#B91C1C` (gelap `#F87171`) — khusus angka negatif (selalu disertai tanda minus `-`)
  - `--hangat-teks` / `--hangat-latar`: `#78350F` / `#FEF3C7` — status deskriptif netral-hangat
- **Tipografi & Skala:**
  - Keluarga utama: `Plus Jakarta Sans` (`tabular-nums` pada seluruh angka).
  - Pendamping teknis: `ui-monospace, Consolas, monospace` hanya di dalam laci sumber XBRL (`"Lihat sumber angka"`).
  - Ukuran: isi `16px` (`1rem`), batas minimum absolut `12px` (`13px`–`15px` untuk catatan/tabel).

---

## 2. Daftar Elemen yang Dihapus & Alasannya
1. **Latar navy/gelap neon (`#0b0f19` + `#38bdf8` glow) & strip 4 kartu KPI atas:** diganti menjadi kertas terang `#FAF8F5` dan langsung membuka pencarian + tabel rekening koran emiten agar tidak menyerupai template dasbor SaaS generik.
2. **Grid kartu seragam berbayangan & badge pil dekoratif (`Audited`, `100% Grounded`, `Official`, `BYOK: Active`):** dihapus; diganti tabel bergaris tipis dan laci sumber inline `"Lihat sumber angka"` yang membuka `raw_xbrl_tag` + `raw_context_ref`.
3. **Latar pil pada status netral (`.status-plain`):** dibuang di akhir fase agar hanya kondisi perhatian yang memakai sorotan hangat.
4. **Penanda bernomor (`01 /`, `02 /`), titik tengah (`·`), panah (`→`) di tombol, emoji ikon di web & template bot, serta istilah pemasaran Inggris (`Cash Fortress`, `Double Stress`, `Anti-Hype`, `Guide`, `Inspect`, `Let's Ship`):** dihapus/diganti ke Bahasa Indonesia sehari-hari (sentence case, kata kerja aktif).
5. **Status vonis tanpa konteks:** diganti kalimat deskriptif beserta angka sumber & tanggal laporan (contoh: *"Kas menutup 23% utang jangka pendek (laporan 2025-12-31)"*).

---

## 3. Screenshot Sebelum & Sesudah
- **Sebelum (`main`):**
  - `docs/ui_shots/before_screener_1280.png`
  - `docs/ui_shots/before_screener_360.png`
- **Sesudah (`fase-7-ui`, 1280px & 360px + Kartu PNG):**
  - `docs/ui_shots/after_screener_1280.png` & `docs/ui_shots/after_screener_360.png`
  - `docs/ui_shots/after_detail_1280.png` & `docs/ui_shots/after_detail_360.png` (dengan laci sumber XBRL terbuka)
  - `docs/ui_shots/after_news_1280.png` & `docs/ui_shots/after_news_360.png`
  - `docs/ui_shots/after_card_1x1.png` & `docs/ui_shots/after_card_9x16.png`

---

## 4. Cakupan yang Diubah & Halaman yang Belum Disentuh
- **Diubah:** `src/web/templates/index.html`, `src/web/app.py` (`/metodologi`, `/analytics`, `xbrl_sources` di `/api/metrics/{ticker}`, `ticker_tidak_ditemukan`), `src/renderer/share_card.py`, `src/renderer/templates/*.j2`, `scripts/generate_product_brief_pdf.py`, `scripts/generate_cofounder_pitch_deck_id.py`, `docs/ui_plan.md`.
- **Belum disentuh (di luar cakupan bahasa Indonesia / versi lama):**
  - `scripts/generate_cofounder_pitch_deck.py` & `docs/IDX_Cash_Radar_CoFounder_Deck.html` (versi bahasa Inggris lama).
  - `deploy_web/index.html` (salinan statis lama).
  - `docs/PRD.md` & `docs/adr/*.md` (dokumen arsitektur historis).

---

## 5. Hasil Verifikasi `pytest`
- **`python -m pytest -q`:** **`136 passed`** (termasuk seluruh tes di `tests/test_language_compliance.py`).
