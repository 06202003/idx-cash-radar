# Kebijakan Privasi, Analitik & Kepatuhan UU PDP — IDX Cash & Accrual Radar (`docs/privacy.md`)

## 1. Pilihan Platform Analitik: Plausible + Counter Anonim Lokal
- **Pilihan:** **Plausible Analytics** (dapat di-*self-host* lewat Docker Community Edition, ringan `< 1 KB`, tanpa cookie) dipadukan dengan pencatat event agregat anonim lokal (`analytics_events` / `bot_analytics_events`).
- **Alasan Pemilihan:** Plausible tidak mengumpulkan data pribadi, tidak melacak lintas situs, dan tetap memungkinkan agregasi metrik produk tanpa konfigurasi kompleks.

## 2. Daftar Event Minimum yang Dicatat
| Nama Event | Pemicu | Metadata Anonim yang Diizinkan |
| :--- | :--- | :--- |
| `ticker_dicek` *(Prioritas)* | Pengguna memilih/memeriksa emiten | `ticker` (mis. `WIKA`) |
| `ticker_tidak_ditemukan` | Pengguna menanyakan ticker di luar universe | `ticker` (kode saham saja) |
| `kartu_dibagikan` *(Prioritas)* | Pengguna menyalin/membagikan kartu fakta | `ticker`, `method` |
| `link_berita_ditempel` | Pengguna menganalisis URL/teks berita | `has_url` (boolean, **bukan** isi teks) |
| `kartu_dibuat` | Pengguna mengunduh PNG 1:1 atau 9:16 | `ticker`, `ratio` |
| `mode_expert_dibuka` | Pengguna beralih ke Expert Mode | `mode` |
| `fitur_pro_dibuka` | Pengguna membuka bagian Pro / Lanjutan | `section` |

## 3. Penyimpanan Minimal & Kepatuhan UU PDP (Bot Telegram Fase 8)
Sesuai prinsip **minimisasi data** Undang-Undang Perlindungan Data Pribadi (UU No. 27 Tahun 2022 / UU PDP):
- **Data yang disimpan:** Bot Telegram **hanya** menyimpan `chat_id` (angka pengenal sesi Telegram), daftar ticker watchlist (maksimal 20 ticker), preferensi jam briefing (`/jadwal`), dan `alert_logs` (untuk idempotensi pengiriman serta jejak audit operasional, bukan untuk klaim kinerja).
- **Data yang dilarang disimpan:** Sistem **tidak** menyimpan nama lengkap, username Telegram, nomor telepon, alamat IP, *User-Agent*, cookie identitas, email, ataupun isi percakapan bebas di tabel analitik.
- **Hak Penghapusan Data (`/stop`):** Pengguna dapat menghapus seluruh data pribadinya kapan saja dengan mengirim perintah **`/stop`** di bot Telegram. Perintah ini langsung menghapus seluruh baris milik `chat_id` pengguna dari tabel `user_watchlists`, `user_schedules`, dan `alert_logs`.
- **Pengguna yang Memblokir Bot:** Jika Telegram mengembalikan `TelegramForbiddenError`, worker otomatis menghentikan pengiriman dan menghapus data `chat_id` tersebut.
