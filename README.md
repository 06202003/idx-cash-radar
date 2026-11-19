# 📡 IDX Alert & Direction Sentiment Bot

Bot Telegram terpisah (`aiogram 3.x`) untuk:
1. **Forecast Sentimen Arah Harga 5 Hari (Naik / Netral / Turun):** Model klasifikasi *walk-forward* (`LogisticRegression`) berbasis fitur momentum, jarak MA20/MA50, RSI(14), rasio volume, dan volatilitas — dengan target mengalahkan biaya transaksi pulang-pergi (`0.4%`).
2. **Backtest Out-of-Sample Otomatis:** Menampilkan akurasi OOS, *win-rate* sinyal Naik, dan rata-rata return bersih setelah fee (`0.4%`) langsung di pesan Telegram.
3. **Berita RSS Terbaru (`when:30d`) + Cross-Check Kas XBRL:** Mengambil berita 30 hari terakhir (diurutkan terbaru dulu) dan mengecek kesehatan kas dari API `idx-cash-radar`.
4. **Jadwal Alert Otomatis:**
   - **08:45 WIB (Pre-Market):** Morning Confluence & Direction Radar
   - **18:00 WIB (Post-Market):** Rekap Sore Watchlist
   - **Audit Log SQLite (`alert_logs`):** Menyimpan setiap alert untuk evaluasi performa historis.

## Cara Menjalankan
```bash
cd idx-alert-bot
cp .env.example .env
# Isi TELEGRAM_BOT_TOKEN dari @BotFather
python -m pytest
python -m src.bot.main
```
