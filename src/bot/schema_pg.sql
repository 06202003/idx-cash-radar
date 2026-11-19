-- PostgreSQL / Supabase Schema for IDX Cash & Accrual Radar Telegram Bot (Fase 8)
-- Privacy-minimal: stores only Telegram chat_id and user watchlist/schedule preferences.

CREATE TABLE IF NOT EXISTS user_watchlists (
    chat_id BIGINT NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chat_id, ticker)
);

CREATE TABLE IF NOT EXISTS user_schedules (
    chat_id BIGINT PRIMARY KEY,
    morning_time VARCHAR(5) NOT NULL DEFAULT '08:30',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_logs (
    id BIGSERIAL PRIMARY KEY,
    delivery_key VARCHAR(160) NOT NULL UNIQUE,
    chat_id BIGINT,
    alert_date DATE NOT NULL,
    alert_type VARCHAR(32) NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    message_hash VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    error_detail TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_logs_chat_date ON alert_logs (chat_id, alert_date);

CREATE TABLE IF NOT EXISTS daily_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    cash_status VARCHAR(48) NOT NULL,
    flags_json JSONB NOT NULL,
    close_price DOUBLE PRECISION,
    volume BIGINT,
    news_items_json JSONB NOT NULL,
    idx_announcements_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, ticker)
);

CREATE TABLE IF NOT EXISTS source_fetch_logs (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_name VARCHAR(64) NOT NULL,
    ticker VARCHAR(16),
    status VARCHAR(24) NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS bot_analytics_events (
    id BIGSERIAL PRIMARY KEY,
    event_name VARCHAR(64) NOT NULL,
    ticker VARCHAR(16),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_users (
    chat_id BIGINT PRIMARY KEY,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS group_cooldowns (
    group_id BIGINT NOT NULL,
    ticker VARCHAR(16) NOT NULL,
    last_sent_ts DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (group_id, ticker)
);

CREATE TABLE IF NOT EXISTS last_seen_filings (
    ticker VARCHAR(10) PRIMARY KEY,
    latest_filing_id VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
