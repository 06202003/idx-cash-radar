# Kebijakan Privasi & Analitik — IDX Cash & Accrual Radar (`docs/privacy.md`)

## 1. Pilihan Platform Analitik: Plausible + Counter Anonim Lokal
- **Pilihan:** **Plausible Analytics** (dapat di-*self-host* lewat Docker Community Edition, ringan `< 1 KB`, tanpa cookie) dipadukan dengan pencatat event agregat anonim lokal di SQLite (`analytics_events`).
- **Alasan Pemilihan:** Dibandingkan solusi yang berat atau bergantung pada *tracking cookie*, Plausible tidak mengumpulkan data pribadi, tidak melacak lintas situs, dan tetap memungkinkan agregasi metrik produk tanpa konfigurasi kompleks.

## 2. Daftar Event Minimum yang Dicatat
| Nama Event | Pemicu | Metadata Anonim yang Diizinkan |
| :--- | :--- | :--- |
| `ticker_dicek` *(Prioritas)* | Pengguna memilih/memeriksa emiten | `ticker` (mis. `WIKA`) |
| `kartu_dibagikan` *(Prioritas)* | Pengguna menyalin/membagikan kartu fakta | `ticker`, `method` |
| `link_berita_ditempel` | Pengguna menganalisis URL/teks berita | `has_url` (boolean, **bukan** isi teks) |
| `kartu_dibuat` | Pengguna mengunduh PNG 1:1 atau 9:16 | `ticker`, `ratio` |
| `mode_expert_dibuka` | Pengguna beralih ke Expert Mode | `mode` |
| `fitur_pro_dibuka` | Pengguna membuka bagian Pro / Lanjutan | `section` |

## 3. Larangan Penyimpanan Data Pribadi & API Key
- Sistem **tidak** menyimpan alamat IP, *User-Agent*, cookie identitas, nama, email, ataupun teks berita mentah di tabel analitik.
- Endpoint `POST /api/analytics/event` memiliki filter *allowlist* ketat: hanya menerima nama event pada daftar resmi dan hanya menyimpan kolom `event_name`, `ticker` (opsional, maks 10 karakter huruf/angka), dan `created_at_utc`. Semua field lain (termasuk `api_key`, `x_gemini_api_key`, `url`, `email`, `ip`) dibuang sebelum penulisan.
