# OPEN_QUESTIONS.md

## Keputusan yang Sudah Ditetapkan (18 Nov 2026)

1. **Q1 — Nasib Model Solvabilitas (L2 & MLP):**
   - **Keputusan:** Hapus semua skor/probabilitas L2 dan MLP dari tampilan utama dan seluruh teks publik. Skor utama menggunakan aturan deterministik (`cash_coverage` dan *safeguard flags*), dengan ambang dan definisi ditampilkan terbuka di `/metodologi`.
   - MLP tetap ada **hanya** sebagai simulator stres *what-if* di bagian Pro/Lanjutan dengan label eksplisit *"Simulasi, bukan prediksi"*. Tidak dilakukan pelatihan ulang model pada sesi ini.
   - **Pekerjaan Masa Depan:** Pelatihan ulang model solvabilitas menggunakan label eksternal independen (misalnya tanggal suspensi BEI, PKPU, atau gagal bayar obligasi) dengan *time-split* ketat tanpa *label leakage*.

2. **Q2 — Sumber Data Historis Harga & Berita (Fase 5):**
   - **Keputusan:** Harga menggunakan Yahoo Finance (`.JK` dan `^JKSE`, *adjusted close*). Berita memprioritaskan arsip Keterbukaan Informasi BEI; sumber lain hanya jika tanggal publikasinya dapat diverifikasi. Jika data berita historis tidak memadai, laporkan `"BUKTI TIDAK CUKUP"` tanpa membuat data sintetis, serta catat batasan *survivorship bias*.
