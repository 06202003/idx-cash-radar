# Panduan Deployment Produksi 24/7 (Gate 8)
**Project:** IDX Cash & Accrual Radar (v2.0)

Dokumen ini menjelaskan langkah-langkah deployment aplikasi ke server cloud/VPS agar bot aktif melayani permintaan 24/7.

---

## 1. Persyaratan Server / VPS
- **OS:** Linux (Ubuntu 22.04 LTS / Debian 12 direkomendasikan) atau Windows Server.
- **Spesifikasi Minimal:** 1 vCPU, 1 GB RAM, 10 GB SSD.
- **Software:** Docker & Docker Compose v2, atau Python 3.11+.

---

## 2. Deployment Cepat Berbasis Docker (Direkomendasikan)

### Langkah 1: Kloning Repositori & Konfigurasi .env
```bash
git clone <URL_REPOSITORY>
cd idx-cash-radar
cp .env.example .env
nano .env
```
Isi variabel lingkungan:
```env
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
GEMINI_API_KEY="your_gemini_api_key"
```

### Langkah 2: Build & Jalankan Kontainer (Background Daemon)
```bash
docker compose up -d --build
```

### Langkah 3: Periksa Status & Log Bot
```bash
# Cek kontainer berjalan
docker compose ps

# Cek streaming log
docker compose logs -f idx-radar-bot
```

### Langkah 4: Hentikan / Restart Bot
```bash
# Restart
docker compose restart idx-radar-bot

# Hentikan
docker compose down
```

---

## 3. Deployment Berbasis Systemd (Alternatif Native Linux VPS)

Jika tidak menggunakan Docker, Anda dapat memanfaatkan `systemd` supervisor:

1. Buat unit file di `/etc/systemd/system/idx-radar.service`:
```ini
[Unit]
Description=IDX Cash & Accrual Radar Telegram Bot Daemon
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/idx-cash-radar
ExecStart=/home/ubuntu/idx-cash-radar/venv/bin/python src/bot/main.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/idx-cash-radar/.env

[Install]
WantedBy=multi-user.target
```

2. Aktifkan service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable idx-radar
sudo systemctl start idx-radar
sudo systemctl status idx-radar
```

---

## 4. Ingestion Data Berkala (Cronjob)
Untuk menjalankan ingestion batch data laporan keuangan baru secara otomatis di server:
```bash
crontab -e
```
Tambahkan baris berikut untuk memeriksa dan memproses filing baru setiap hari pukul 02:00 WIB:
```cron
0 19 * * * cd /home/ubuntu/idx-cash-radar && ./venv/bin/python scripts/ingest_filings.py --batch >> /var/log/idx_ingest.log 2>&1
```

