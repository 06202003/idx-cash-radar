# Laporan Implementasi Bot Telegram Fase 8 (`REPORT_BOT.md`)

**Branch:** `fase-8-telegram` (terpisah dari `main`, siap diuji/review tanpa di-merge ke `main`)  
**Dasar Perancangan:** [Morning_Confluence_Alert_Brief_ID.pdf](docs/Morning_Confluence_Alert_Brief_ID.pdf) dengan perubahan wajib kepatuhan, privasi (UU PDP), dan auditabilitas.

---

## 1. Apa yang Dibangun

1. **Worker Bot & Scheduler Terpisah dari Vercel (Docker + PostgreSQL/Supabase):**
   - [src/bot/worker.py](src/bot/worker.py), [Dockerfile.bot](Dockerfile.bot), [docker-compose.bot.yml](docker-compose.bot.yml), dan panduan [docs/DEPLOYMENT_BOT.md](docs/DEPLOYMENT_BOT.md).
   - [src/bot/pg_store.py](src/bot/pg_store.py) & [src/bot/schema_pg.sql](src/bot/schema_pg.sql): Memakai PostgreSQL/Supabase (`DATABASE_URL`); menolak SQLite pada mode produksi.
   - Mendukung batas maksimal **20 ticker per pengguna**, validasi kode saham (`^[A-Z0-9]{4,5}$`), penanganan `TelegramRetryAfter`, retry pengiriman, dan auto-cleanup saat `TelegramForbiddenError` (pengguna memblokir bot).
   - **Pengiriman Idempoten:** Menggunakan `delivery_key` unik (`chat_id:tanggal:alert_type:scope`) di `alert_logs` agar restart worker tidak pernah mengirim pesan ganda.

2. **Perintah & Mode Interaksi Bot Telegram:**
   - `/start`, `/bantuan` (panduan), `/tentang` (tautan `/metodologi` & kebijakan privasi).
   - `/cek <KODE|URL>`: Mengirim kartu PNG Fase 3 (`render_share_card_png`) sebagai foto + caption angka dari `canonical_facts` beserta `Tanggal Laporan`, atau menganalisis tautan berita bila argumen berupa URL.
   - **Forward-to-Check:** Meneruskan pesan/tautan berita atau membalas pesan di grup dengan `/cek` untuk langsung memeriksa ticker/URL terkait tanpa label sentimen.
   - **Mode Inline (`@namabot TLKM`) & Mode Grup:** Mengirim kartu fakta langsung ke grup dengan **cooldown anti-spam** (`GROUP_COOLDOWN_SECONDS=60`) per `(group_id, ticker)`.
   - `/watch <KODE>`, `/unwatch <KODE>`, `/watchlist`, `/jadwal <HH:MM>` (atur jam briefing pagi per pengguna, default `08:30 WIB`).
   - `/stop`: Menghapus seluruh data pengguna (`user_watchlists`, `user_schedules`, `alert_logs`, `bot_users`) sesuai UU PDP ([docs/privacy.md](docs/privacy.md)).
   - Ticker di luar universe: membalas *"belum ada di data kami"* dan mencatat event `ticker_tidak_ditemukan`.
   - **4 Metrik Inti (`get_north_star_metrics`):** `/start` (`bot_start`), aktivasi `>= 1` ticker, retensi hari ke-7 (`bot_users`), dan kartu dibagikan ke grup (`kartu_dibagikan`).
   - **Alert Perubahan Laporan (`detect_filing_change_for_ticker`):** Notifikasi faktual saat `filing_id` baru masuk dibandingkan periode sebelumnya (perubahan CFO TTM & Cash Coverage, tanpa kata evaluatif).

3. **Briefing Watchlist Pagi, Rekap Sore, Kalender Libur BEI & Arsip Bukti:**
   - [src/bot/idx_calendar.py](src/bot/idx_calendar.py): Kalender libur nasional & bursa BEI (2025–2026) zona waktu `Asia/Jakarta`; bot tidak mengirim briefing/alert saat akhir pekan atau hari libur BEI.
   - [src/bot/briefing.py](src/bot/briefing.py): Seluruh angka akuntansi diambil langsung dari `canonical_facts` / `computed_metrics` + menampilkan `Tanggal Laporan`.
   - **Arsip `daily_snapshot`:** Setiap hari bursa pukul `18:00 WIB`, worker mengarsipkan seluruh universe emiten (`cash_status`, `flags_json`, `close_price`, `volume`, `news_items_json`, `idx_announcements_json`).

4. **Kepatuhan Bahasa (`tests/test_language_compliance.py`):**
   - Menambahkan `"rawan kejar"`, `"momentum sehat"`, `"kas prima"`, `"layak"`, `"skor kelayakan"`, `"hindari"`, dan `"peluang"` ke `BLACKLISTED_WORDS`.

---

## 2. Apa yang Sengaja TIDAK Dibangun dari Brief & Alasannya

| Item di Brief Awal | Keputusan | Alasan |
| :--- | :--- | :--- |
| **"Morning Confluence" (daftar saham pilihan/peringkat untuk semua pengguna)** | **Dihapus** | Menghindari kesan kurasi/rekomendasi saham terpusat. Diganti **Briefing Watchlist Pagi** yang hanya berisi ticker pilihan pengguna via `/watch`. |
| **Label evaluatif & kesimpulan RSI / MA20 / MA50** | **Dihapus** | Kata seperti *"Rawan Kejar"*, *"momentum sehat"*, *"kas prima"*, *"layak"*, *"hindari"*, *"peluang"* berisiko menyalahi prinsip non-rekomendasi. Diganti fakta numerik murni (`Harga Tutup`, `Perubahan 1H`, `Volume Xx rata-rata 20 hari, data tertunda ±5-15 menit`). |
| **Label sentimen berita (`POSITIF` / `NETRAL` / `PERHATIAN`) & ringkasan salinan** | **Dihapus sementara** | Akurasi klasifikasi sentimen belum diukur secara empiris; berita hanya dikirim berupa **judul singkat + nama media + tautan**. |
| **Laporan publik "return alert"** | **Tidak dibangun** | Pesan alert adalah alat bantu informasi faktual, bukan bahan klaim kinerja/return investasi. |
| **SQLite untuk produksi** | **Ditolak** | State user & arsip `daily_snapshot` wajib persisten dan aman untuk konkurensi worker di PostgreSQL/Supabase. |

---

## 3. Sumber Data yang Gagal / Terbatas

- **Yahoo Finance (`.JK`):** Data harga & volume memiliki keterlambatan ±5–15 menit dan dapat mengalami *rate-limit* atau timeout sementara; jika gagal diakses, kegagalan dicatat di `source_fetch_logs` dan bot **tidak mengirim tebakan harga/volume**.
- **Google News RSS (`when:30d`):** Bergantung pada ketersediaan indeks Google News; bila gagal diakses, dicatat di `source_fetch_logs` dan alert peristiwa (`UMA/FCA/suspensi/rebalancing`) tidak dikirim tanpa sumber terverifikasi.
- **Feed Pengumuman Resmi BEI (`idx.co.id` langsung):** Portal BEI sering menerapkan proteksi anti-bot/Cloudflare pada request server non-browser; oleh karena itu deteksi peristiwa saat ini menggunakan RSS media terverifikasi yang mencantumkan media sumber & waktu terbit.

---

## 4. Cara Menjalankan Ulang & Menguji

### Menjalankan Seluruh Tes (`pytest`)
```bash
python -m pytest -q
```

### Menjalankan Worker Bot (Produksi Docker + PostgreSQL/Supabase)
1. Siapkan `.env` berisi `TELEGRAM_BOT_TOKEN` dan `DATABASE_URL=postgresql://...`.
2. Jalankan:
   ```bash
   docker compose -f docker-compose.bot.yml up -d --build
   ```
   (Atau jalankan langsung secara lokal dengan `DATABASE_URL` PostgreSQL: `python -m src.bot.worker`).
