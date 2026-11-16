-- IDX Cash & Accrual Radar — Relational Schema Specification
-- Locked in AGENTS.md Section 7

CREATE TABLE IF NOT EXISTS issuers (
    ticker TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    idx_sub_industry TEXT NOT NULL,
    listing_status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, SUSPENDED, DELISTED
    delisted_date TEXT
);

CREATE TABLE IF NOT EXISTS filings (
    filing_id TEXT PRIMARY KEY, -- Format: TICKER_YYYY_Q#_[FIRST|RESTATED]
    ticker TEXT NOT NULL REFERENCES issuers(ticker),
    fiscal_year INTEGER NOT NULL,
    period_code TEXT NOT NULL,  -- Q1, Q2, Q3, FY
    period_end_date TEXT NOT NULL,
    filing_date TEXT,
    is_audited INTEGER NOT NULL, -- 0 for Q1-Q3, 1 for FY
    is_restatement INTEGER NOT NULL DEFAULT 0,
    reporting_currency TEXT NOT NULL DEFAULT 'IDR',
    fx_rate_to_idr TEXT NOT NULL DEFAULT '1',
    sanity_check_passed INTEGER NOT NULL,
    source_xbrl_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id TEXT NOT NULL REFERENCES filings(filing_id),
    canonical_key TEXT NOT NULL, -- e.g., 'cash_and_equivalents', 'contract_assets_current'
    value_idr TEXT NOT NULL,     -- Stored as exact integer/Decimal string
    raw_xbrl_tag TEXT NOT NULL,
    raw_context_ref TEXT NOT NULL,
    raw_unit_ref TEXT,
    raw_decimals TEXT,
    raw_lexical_value TEXT NOT NULL,
    UNIQUE(filing_id, canonical_key)
);

CREATE TABLE IF NOT EXISTS computed_metrics (
    filing_id TEXT PRIMARY KEY REFERENCES filings(filing_id),
    ticker TEXT NOT NULL,
    period_end_date TEXT NOT NULL,
    is_audit_derived_q4 INTEGER NOT NULL DEFAULT 0,
    cfo_single_q_idr TEXT,
    cfo_ttm_idr TEXT,
    net_income_ttm_idr TEXT,
    revenue_ttm_idr TEXT,
    gross_contract_exposure_ratio TEXT,
    net_contract_exposure_ratio TEXT,
    gross_divergence_yoy_bps TEXT,
    sloan_ratio_ttm TEXT,
    cash_coverage_ratio TEXT,
    revenue_contraction_guard INTEGER NOT NULL DEFAULT 0,
    debt_free_short_term INTEGER NOT NULL DEFAULT 0,
    flag_accrual_divergence INTEGER NOT NULL DEFAULT 0,
    flag_acute_liquidity INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS demand_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    requested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_filings_ticker_period ON filings(ticker, fiscal_year, period_code);
CREATE INDEX IF NOT EXISTS idx_canonical_facts_lookup ON canonical_facts(filing_id, canonical_key);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON user_watchlist(ticker);

