# Rencana Desain UI — IDX Cash & Accrual Radar (`docs/ui_plan.md`)

## 1. Subjek & Tugas Utama Layar
- **Subjek:** Alat cek fakta kas emiten BEI untuk investor dan trader ritel Indonesia yang mayoritas mengakses lewat HP (`360px` ke atas).
- **Tugas utama layar:** Membaca angka kas satu emiten (kas di bank, utang jangka pendek, arus kas operasional 12 bulan) dalam format Rupiah Indonesia, melihat status deskriptif dengan tanggal laporan, dan **mengetahui dari mana angka itu berasal** (tag XBRL resmi BEI, periode, tanggal laporan).
- **Metafora visual:** **Lembar kerja audit / rekening koran.** Tabel, baris berbatas garis tipis, dan catatan sumber yang bisa dibuka — bukan dasbor gelap neon dengan deretan kartu seragam.

---

## 2. Token Desain (Warna, Tipografi, Skala)

### 2.1 Palet Warna Bernama (Terang Default, Gelap Opsional)
| Nama Token | Mode Terang (Default) | Mode Gelap (Opsional) | Peran |
| :--- | :--- | :--- | :--- |
| `--kertas` | `#FAF8F5` | `#141413` | Latar halaman utama |
| `--lembar` | `#FFFFFF` | `#1C1C1A` | Permukaan tabel & baris catatan sumber |
| `--tinta` | `#18181B` | `#F4F3EF` | Teks utama, judul, angka positif/nol |
| `--catatan` | `#52525B` | `#A1A1AA` | Keterangan sekunder, tanggal laporan, label kolom |
| `--garis` | `#E4E0D8` | `#2E2E2A` | Garis pembatas baris & tabel |
| `--aksi` | `#1D4ED8` | `#60A5FA` | Tautan aksi, tombol utama, ring fokus keyboard |
| `--negatif` | `#B91C1C` | `#F87171` | **Khusus** angka negatif (selalu disertai tanda `-`) |
| `--hangat-teks` / `--hangat-latar` | `#78350F` / `#FEF3C7` | `#FDE68A` / `#292212` | Status deskriptif netral-hangat |

### 2.2 Tipografi & Skala Ukuran
- **Keluarga huruf utama (1 keluarga):** `Plus Jakarta Sans` (fallback `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`). Seluruh angka menggunakan `font-variant-numeric: tabular-nums`.
- **Pendamping teknis (khusus tag XML XBRL di dalam laci sumber):** `ui-monospace, Consolas, monospace` (dilarang dipakai untuk label UI biasa).
- **Skala ukuran huruf (minimum 12px, isi HP minimum 16px):**
  - Isi / paragraf / sel utama di HP: `16px` (`1rem`)
  - Judul halaman: `22px` (`1.375rem`)
  - Judul bagian: `18px` (`1.125rem`)
  - Angka sorotan emiten: `24px` (`1.5rem`)
  - Catatan sumber / tanggal laporan / sel sekunder: `13px`–`14px` (batas bawah keras `12px`, tidak ada teks `< 12px`).

---

## 3. Wireframe ASCII (HP 360px Terlebih Dahulu)

### 3.1 Layar Daftar Emiten (Screener) — `360px`
```text
+------------------------------------------+
| IDX Cash Radar              [Mode Gelap] |
| Cek fakta kas laporan XBRL BEI           |
| [Daftar Emiten] [Detail] [Cek Berita]    |
+------------------------------------------+
| Cari kode atau nama emiten...            |
| [Semua sektor v] [x] Hanya kas ops (+)   |
| Menampilkan 49 emiten (laporan FY 2025)  |
+------------------------------------------+
| KODE   | KAS VS UTANG JP   | KAS OPS 12B |
|--------+-------------------+-------------|
| WIKA   | 0,95x             | -Rp 348,0 M |
| Wijaya Karya (2025-12-31)                |
| Status: Kas menutup 95% utang JP         |
| [Lihat detail & sumber angka]            |
|------------------------------------------|
| WSKT   | 0,23x             | -Rp 559,7 M |
| Waskita Karya (2025-12-31)               |
| Status: Kas menutup 23% utang JP         |
| [Lihat detail & sumber angka]            |
+------------------------------------------+
| Catatan: bukan saran transaksi saham.    |
| Data historis mengikuti laporan BEI.     |
+------------------------------------------+
```

### 3.2 Layar Detail Emiten & Catatan Sumber — `360px`
```text
+------------------------------------------+
| <- Kembali ke daftar                     |
| WSKT — Waskita Karya (Persero) Tbk.      |
| Laporan tahunan berakhir 2025-12-31      |
| Status: Kas menutup 23% utang jangka     |
| pendek (Rp 1,42 T vs Rp 6,28 T, FY 2025) |
+------------------------------------------+
| POS LAPORAN KEUANGAN        | NILAI      |
|-----------------------------+------------|
| Kas dan setara kas          | Rp 1,42 T  |
|   [Lihat sumber angka]                   |
|   +------------------------------------+ |
|   | Tag XBRL : CashAndCashEquivalents  | |
|   | Konteks  : CurrentYearInstant      | |
|   | Tanggal  : 2025-12-31 (XBRL BEI)   | |
|   +------------------------------------+ |
| Utang berbunga jangka pdk   | Rp 6,28 T  |
|   [Lihat sumber angka]                   |
| Kas masuk operasional 12bln | -Rp 559,7 M|
|   [Lihat sumber angka]                   |
| Laba di atas kertas vs kas  | -5,5%     |
+------------------------------------------+
| [Unduh kartu 1:1] [Unduh kartu 9:16]     |
| [Salin ringkasan]                        |
+------------------------------------------+
```

---

## 4. Prinsip Desain & Tinjauan Anti-Generik

1. **Lembar audit, bukan etalase kartu:** Konten utama menggunakan tabel bergaris tipis dan daftar terstruktur. Kartu hanya dipakai untuk **kartu fakta yang memang dibagikan** (`/api/card/{ticker}.png`).
2. **Satu momen khas: laci catatan sumber XBRL inline:** Setiap angka akuntansi memiliki tombol `"Lihat sumber angka"` yang membuka catatan sumber (`raw_xbrl_tag`, `raw_context_ref`, `period_end_date`) tepat di bawah barisnya dengan satu transisi halus (dihormati oleh `prefers-reduced-motion`).
3. **Bahasa Indonesia sehari-hari & deskriptif:** Tidak ada jargon pemasaran Inggris (*Cash Fortress*, *Double Stress*, *Anti-Hype*, *Guide*, *Inspect*, *Let's Ship*), tidak ada label ALL-CAPS berjarak lebar, tidak ada emoji ikon, dan status selalu menyebut angka sumber + tanggal laporan.
4. **Aksesibel sejak 360px:** Teks isi minimal `16px` di HP, minimum absolut `12px`, angka negatif selalu memakai tanda minus `-` selain warna merah, fokus keyboard terlihat jelas (`outline: 2px solid var(--aksi)`), dan tabel lebar dapat digulir di dalam wadahnya.

### Tinjauan: Apa yang Diganti karena Terlalu Generik?
- **Diganti:** Strip 4 kartu KPI di bagian paling atas halaman (*Stock Universe*, *Total Facts*, dll.) + blok grafik kuadran besar di atas tabel screener. **Alasan:** Hampir semua dasbor SaaS/finansial generik menaruh 4 kartu KPI dekoratif sebelum pengguna bisa mencari satu emiten. Di redesain ini, halaman langsung dibuka oleh **pencarian + daftar rekening koran emiten**, sedangkan grafik/simulator diletakkan di tab/bagian lanjutan.
- **Diganti:** Latar gelap `#0b0f19` dengan aksen biru neon `#38bdf8`, badge pil dekoratif (`Audited`, `100% Grounded`, `BYOK: Active`), dan penanda bernomor (`01 /`, `02 /`). **Alasan:** Elemen-elemen tersebut adalah ciri khas template AI generik dan mengalihkan fokus dari keterbacaan angka kas.
