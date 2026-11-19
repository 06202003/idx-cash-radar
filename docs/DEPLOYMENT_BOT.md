# Panduan Deployment Bot Telegram Worker (Docker + PostgreSQL / Supabase)

Worker bot Telegram (`src/bot/worker.py`) dan scheduler harian (`08:30 WIB` / `/jadwal` & `18:00 WIB` + `daily_snapshot`) berjalan **terpisah dari Vercel** menggunakan container Docker 24/7 dan database **PostgreSQL / Supabase**.

## 1. Prasyarat
- Server Cloud VPS (Ubuntu/Debian) dengan Docker & Docker Compose terpasang.
- Database **PostgreSQL** atau **Supabase** (dapatkan *Connection String* `postgresql://...`).
- Token Bot Telegram dari `@BotFather`.

## 2. Inisialisasi Skema PostgreSQL
Jalankan DDL [src/bot/schema_pg.sql](../src/bot/schema_pg.sql) pada database Supabase/PostgreSQL Anda (atau biarkan `BotStateStore` membuatnya otomatis saat startup pertama).

## 3. Konfigurasi `.env` di Server
```ini
TELEGRAM_BOT_TOKEN=123456789:ABC_your_token
DATABASE_URL=postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres
PUBLIC_BASE_URL=https://idx-cash-radar.vercel.app
VOLUME_ALERT_THRESHOLD=3.0
```
> **Penting:** Worker akan menolak menyala jika `DATABASE_URL` kosong atau mengarah ke SQLite.

## 4. Menjalankan Worker 24/7
```bash
docker compose -f docker-compose.bot.yml up -d --build
docker compose -f docker-compose.bot.yml logs -f
```
