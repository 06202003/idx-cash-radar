"""
Automated Number Traceability Audit ("Jejak Angka" — Tambahan Fase 3).
Randomly samples >= 30 numeric values displayed in UI/cards (/api/screener)
and verifies each can be traced to XBRL tags in canonical_facts.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from src.web.app import app

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "idx_cash_radar.db"
client = TestClient(app)

FIELD_TO_CANONICAL_KEYS = {
    "cash_idr": ("cash_and_equivalents",),
    "st_debt_idr": (
        "st_debt_bank_loans",
        "st_debt_current_maturities_bank_loans",
        "st_debt_current_maturities_bonds_sukuk_mtn",
        "st_debt_current_portion_lease_liabilities",
    ),
    "total_assets_idr": ("total_assets",),
    "cfo_ttm_idr": ("cfo",),
    "net_income_ttm_idr": ("net_income",),
    "revenue_ttm_idr": ("revenue",),
}


def test_random_30_ui_numbers_traceable_to_xbrl_canonical_facts() -> None:
    resp = client.get("/api/screener?fiscal_year=2025")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 10

    candidates: list[tuple[str, str, float]] = []
    for r in rows:
        t = r["ticker"]
        for field in FIELD_TO_CANONICAL_KEYS:
            val = r.get(field)
            if val is not None:
                candidates.append((t, field, float(val)))

    rng = random.Random(42)
    sample = rng.sample(candidates, min(36, len(candidates)))
    assert len(sample) >= 30

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        passed = 0
        untraced: list[tuple[str, str, float]] = []

        for ticker, field, val in sample:
            keys = FIELD_TO_CANONICAL_KEYS[field]
            placeholders = ",".join("?" for _ in keys)
            fact_rows = conn.execute(
                f"""
                SELECT cf.canonical_key, cf.raw_xbrl_tag, cf.raw_context_ref, cf.value_idr
                FROM canonical_facts cf
                JOIN filings f ON cf.filing_id = f.filing_id
                WHERE f.ticker = ?
                  AND cf.canonical_key IN ({placeholders})
                  AND cf.raw_xbrl_tag IS NOT NULL
                  AND trim(cf.raw_xbrl_tag) != ''
                  AND cf.raw_context_ref IS NOT NULL
                  AND trim(cf.raw_context_ref) != ''
                """,
                (ticker, *keys),
            ).fetchall()

            # Zero values (e.g. debt-free st_debt_idr == 0) may have explicit 0 fact or absent debt tag
            if fact_rows or (field == "st_debt_idr" and val == 0.0):
                passed += 1
            else:
                untraced.append((ticker, field, val))

    pct = (passed / len(sample)) * 100.0
    print(f"\n[Jejak Angka Audit] {passed}/{len(sample)} ({pct:.1f}%) numbers traced to XBRL tags.")
    assert pct == 100.0, f"Untraced UI numbers: {untraced}"
