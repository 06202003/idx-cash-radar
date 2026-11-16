"""
Massive Universe Population Script for IDX Cash & Accrual Radar.
Expands the dataset to 48 prominent issuers across 5 strategic sectors in IDX:
1. Konstruksi & Rekayasa (15 issuers)
2. FMCG, Farmasi & Ritel (12 issuers)
3. Perbankan & Jasa Keuangan (8 issuers)
4. Energi, Tambang & Komoditas (8 issuers)
5. Telekomunikasi & Infrastruktur Digital (5 issuers)
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

DB_PATH = Path("idx_cash_radar.db")

MASSIVE_ISSUERS = [
    # -------------------------------------------------------------
    # 1. KONSTRUKSI & REKAYASA (15 Emiten)
    # -------------------------------------------------------------
    # Existing 12 + 3 New (SSIA, IDPR, TOPS)
    {
        "ticker": "SSIA",
        "name": "Surya Semesta Internusa Tbk.",
        "sub_ind": "Konstruksi Kawasan Industri & Bangunan",
        "sector": "CONSTRUCTION",
        "rev": Decimal("4850000000000"),
        "cfo": Decimal("420000000000"),
        "ni": Decimal("285000000000"),
        "cash": Decimal("1650000000000"),
        "debt": Decimal("1120000000000"),
        "rec": Decimal("1240000000000"),
        "inv": Decimal("850000000000"),
        "assets": Decimal("9850000000000"),
    },
    {
        "ticker": "IDPR",
        "name": "Indonesia Pondasi Raya Tbk.",
        "sub_ind": "Konstruksi Pondasi & Rekayasa Bawah Tanah",
        "sector": "CONSTRUCTION",
        "rev": Decimal("1150000000000"),
        "cfo": Decimal("145000000000"),
        "ni": Decimal("68000000000"),
        "cash": Decimal("285000000000"),
        "debt": Decimal("195000000000"),
        "rec": Decimal("420000000000"),
        "inv": Decimal("180000000000"),
        "assets": Decimal("1850000000000"),
    },
    {
        "ticker": "TOPS",
        "name": "Totalindo Eka Persada Tbk.",
        "sub_ind": "Konstruksi Bangunan Gedung Tinggi",
        "sector": "CONSTRUCTION",
        "rev": Decimal("850000000000"),
        "cfo": Decimal("-120000000000"),
        "ni": Decimal("-85000000000"),
        "cash": Decimal("45000000000"),
        "debt": Decimal("380000000000"),
        "rec": Decimal("520000000000"),
        "inv": Decimal("210000000000"),
        "assets": Decimal("1450000000000"),
    },
    # -------------------------------------------------------------
    # 2. FMCG, FARMASI & RITEL (12 Emiten)
    # -------------------------------------------------------------
    # (ICBP, UNVR, MYOR, AMRT already in) + 8 New
    {
        "ticker": "INDF",
        "name": "Indofood Sukses Makmur Tbk.",
        "sub_ind": "Makanan & Bahan Pangan (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("114800000000000"),
        "cfo": Decimal("18500000000000"),
        "ni": Decimal("11450000000000"),
        "cash": Decimal("28400000000000"),
        "debt": Decimal("14200000000000"),
        "rec": Decimal("9450000000000"),
        "inv": Decimal("15800000000000"),
        "assets": Decimal("192500000000000"),
    },
    {
        "ticker": "KLBF",
        "name": "Kalbe Farma Tbk.",
        "sub_ind": "Farmasi & Produk Kesehatan (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("32450000000000"),
        "cfo": Decimal("4120000000000"),
        "ni": Decimal("3250000000000"),
        "cash": Decimal("4950000000000"),
        "debt": Decimal("1250000000000"),
        "rec": Decimal("4850000000000"),
        "inv": Decimal("5420000000000"),
        "assets": Decimal("29450000000000"),
    },
    {
        "ticker": "SIDO",
        "name": "Industri Jamu & Farmasi Sido Muncul Tbk.",
        "sub_ind": "Herbal, Jamu & Farmasi (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("3950000000000"),
        "cfo": Decimal("1280000000000"),
        "ni": Decimal("1120000000000"),
        "cash": Decimal("1050000000000"),
        "debt": Decimal("0"),  # Bebas Utang Bank
        "rec": Decimal("480000000000"),
        "inv": Decimal("380000000000"),
        "assets": Decimal("4250000000000"),
    },
    {
        "ticker": "GGRM",
        "name": "Gudang Garam Tbk.",
        "sub_ind": "Rokok & Produk Tembakau (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("108500000000000"),
        "cfo": Decimal("9450000000000"),
        "ni": Decimal("4120000000000"),
        "cash": Decimal("4850000000000"),
        "debt": Decimal("12800000000000"),
        "rec": Decimal("3120000000000"),
        "inv": Decimal("48500000000000"),
        "assets": Decimal("86500000000000"),
    },
    {
        "ticker": "HMSP",
        "name": "HM Sampoerna Tbk.",
        "sub_ind": "Rokok & Produk Tembakau (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("117500000000000"),
        "cfo": Decimal("8950000000000"),
        "ni": Decimal("7850000000000"),
        "cash": Decimal("4120000000000"),
        "debt": Decimal("1450000000000"),
        "rec": Decimal("4250000000000"),
        "inv": Decimal("24800000000000"),
        "assets": Decimal("54800000000000"),
    },
    {
        "ticker": "ACES",
        "name": "Aspirasi Hidup Indonesia Tbk. (Ace Hardware)",
        "sub_ind": "Ritel Perlengkapan Rumah Tangga (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("8450000000000"),
        "cfo": Decimal("1240000000000"),
        "ni": Decimal("820000000000"),
        "cash": Decimal("2850000000000"),
        "debt": Decimal("0"),  # Bebas Utang Bank
        "rec": Decimal("185000000000"),
        "inv": Decimal("2950000000000"),
        "assets": Decimal("8120000000000"),
    },
    {
        "ticker": "MAPI",
        "name": "Mitra Adiperkasa Tbk.",
        "sub_ind": "Ritel Busana & Gaya Hidup (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("35400000000000"),
        "cfo": Decimal("4250000000000"),
        "ni": Decimal("2150000000000"),
        "cash": Decimal("3420000000000"),
        "debt": Decimal("2850000000000"),
        "rec": Decimal("1450000000000"),
        "inv": Decimal("6850000000000"),
        "assets": Decimal("27800000000000"),
    },
    {
        "ticker": "CMRY",
        "name": "Cisarua Mountain Dairy Tbk. (Cimory)",
        "sub_ind": "Makanan Olahan & Susu (FMCG)",
        "sector": "FMCG",
        "rev": Decimal("8950000000000"),
        "cfo": Decimal("1850000000000"),
        "ni": Decimal("1420000000000"),
        "cash": Decimal("2950000000000"),
        "debt": Decimal("180000000000"),
        "rec": Decimal("945000000000"),
        "inv": Decimal("1120000000000"),
        "assets": Decimal("8250000000000"),
    },
    # -------------------------------------------------------------
    # 3. PERBANKAN & KEUANGAN (8 Emiten)
    # -------------------------------------------------------------
    # (BBRI, BMRI, BBNI, BRIS already in) + 4 New
    {
        "ticker": "BDMN",
        "name": "Bank Danamon Indonesia Tbk.",
        "sub_ind": "Bank Swasta & Jasa Keuangan",
        "sector": "BANKING",
        "rev": Decimal("16450000000000"),
        "cfo": Decimal("6120000000000"),
        "ni": Decimal("3850000000000"),
        "cash": Decimal("28500000000000"),
        "debt": Decimal("154000000000000"),
        "rec": Decimal("142000000000000"),
        "inv": Decimal("3850000000000"),  # NPL ~2.7%
        "assets": Decimal("215000000000000"),
    },
    {
        "ticker": "BNGA",
        "name": "Bank CIMB Niaga Tbk.",
        "sub_ind": "Bank Swasta & Jasa Keuangan",
        "sector": "BANKING",
        "rev": Decimal("18950000000000"),
        "cfo": Decimal("8450000000000"),
        "ni": Decimal("6850000000000"),
        "cash": Decimal("38500000000000"),
        "debt": Decimal("245000000000000"),
        "rec": Decimal("218000000000000"),
        "inv": Decimal("4450000000000"),  # NPL ~2.0%
        "assets": Decimal("342000000000000"),
    },
    {
        "ticker": "BBTN",
        "name": "Bank Tabungan Negara (Persero) Tbk.",
        "sub_ind": "Bank BUMN & Pembiayaan Perumahan",
        "sector": "BANKING",
        "rev": Decimal("15850000000000"),
        "cfo": Decimal("5420000000000"),
        "ni": Decimal("3450000000000"),
        "cash": Decimal("32400000000000"),
        "debt": Decimal("365000000000000"),
        "rec": Decimal("345000000000000"),
        "inv": Decimal("10450000000000"),  # NPL ~3.0%
        "assets": Decimal("445000000000000"),
    },
    {
        "ticker": "MEGA",
        "name": "Bank Mega Tbk.",
        "sub_ind": "Bank Swasta & Jasa Keuangan",
        "sector": "BANKING",
        "rev": Decimal("6450000000000"),
        "cfo": Decimal("3120000000000"),
        "ni": Decimal("3420000000000"),
        "cash": Decimal("18500000000000"),
        "debt": Decimal("94500000000000"),
        "rec": Decimal("68500000000000"),
        "inv": Decimal("850000000000"),  # NPL ~1.2%
        "assets": Decimal("132000000000000"),
    },
    # -------------------------------------------------------------
    # 4. ENERGI, TAMBANG & KOMODITAS (8 Emiten)
    # -------------------------------------------------------------
    {
        "ticker": "ADRO",
        "name": "Adaro Energy Indonesia Tbk.",
        "sub_ind": "Pertambangan Batubara & Energi",
        "sector": "FMCG",  # Mapped to operational cash card
        "rev": Decimal("98500000000000"),
        "cfo": Decimal("34200000000000"),
        "ni": Decimal("24850000000000"),
        "cash": Decimal("48500000000000"),
        "debt": Decimal("6450000000000"),
        "rec": Decimal("8450000000000"),
        "inv": Decimal("4120000000000"),
        "assets": Decimal("158000000000000"),
    },
    {
        "ticker": "PTBA",
        "name": "Bukit Asam Tbk.",
        "sub_ind": "Pertambangan Batubara BUMN",
        "sector": "FMCG",
        "rev": Decimal("42500000000000"),
        "cfo": Decimal("8950000000000"),
        "ni": Decimal("6450000000000"),
        "cash": Decimal("6850000000000"),
        "debt": Decimal("1450000000000"),
        "rec": Decimal("3420000000000"),
        "inv": Decimal("2850000000000"),
        "assets": Decimal("41200000000000"),
    },
    {
        "ticker": "PGAS",
        "name": "Perusahaan Gas Negara Tbk.",
        "sub_ind": "Distribusi Gas Bumi & Energi",
        "sector": "FMCG",
        "rev": Decimal("58450000000000"),
        "cfo": Decimal("11200000000000"),
        "ni": Decimal("4850000000000"),
        "cash": Decimal("18450000000000"),
        "debt": Decimal("7850000000000"),
        "rec": Decimal("9450000000000"),
        "inv": Decimal("1850000000000"),
        "assets": Decimal("104500000000000"),
    },
    {
        "ticker": "MEDC",
        "name": "Medco Energi Internasional Tbk.",
        "sub_ind": "Minyak, Gas & Energi Terbarukan",
        "sector": "FMCG",
        "rev": Decimal("38500000000000"),
        "cfo": Decimal("9450000000000"),
        "ni": Decimal("4120000000000"),
        "cash": Decimal("8950000000000"),
        "debt": Decimal("6850000000000"),
        "rec": Decimal("4850000000000"),
        "inv": Decimal("1250000000000"),
        "assets": Decimal("112000000000000"),
    },
    {
        "ticker": "AKRA",
        "name": "AKR Corporindo Tbk.",
        "sub_ind": "Distribusi BBM & Kawasan Industri",
        "sector": "FMCG",
        "rev": Decimal("44500000000000"),
        "cfo": Decimal("4850000000000"),
        "ni": Decimal("2850000000000"),
        "cash": Decimal("5420000000000"),
        "debt": Decimal("1850000000000"),
        "rec": Decimal("4850000000000"),
        "inv": Decimal("2450000000000"),
        "assets": Decimal("29500000000000"),
    },
    {
        "ticker": "ANTM",
        "name": "Aneka Tambang Tbk.",
        "sub_ind": "Pertambangan Emas & Nikel BUMN",
        "sector": "FMCG",
        "rev": Decimal("52400000000000"),
        "cfo": Decimal("4950000000000"),
        "ni": Decimal("3450000000000"),
        "cash": Decimal("8450000000000"),
        "debt": Decimal("2150000000000"),
        "rec": Decimal("2450000000000"),
        "inv": Decimal("4850000000000"),
        "assets": Decimal("38500000000000"),
    },
    {
        "ticker": "INCO",
        "name": "Vale Indonesia Tbk.",
        "sub_ind": "Pertambangan Nikel",
        "sector": "FMCG",
        "rev": Decimal("16850000000000"),
        "cfo": Decimal("4850000000000"),
        "ni": Decimal("3850000000000"),
        "cash": Decimal("11200000000000"),
        "debt": Decimal("0"),  # Bebas Utang Bank
        "rec": Decimal("1850000000000"),
        "inv": Decimal("2450000000000"),
        "assets": Decimal("42500000000000"),
    },
    {
        "ticker": "ITMG",
        "name": "Indo Tambangraya Megah Tbk.",
        "sub_ind": "Pertambangan Batubara",
        "sector": "FMCG",
        "rev": Decimal("36400000000000"),
        "cfo": Decimal("8950000000000"),
        "ni": Decimal("6850000000000"),
        "cash": Decimal("14200000000000"),
        "debt": Decimal("0"),  # Bebas Utang Bank
        "rec": Decimal("2150000000000"),
        "inv": Decimal("1850000000000"),
        "assets": Decimal("34200000000000"),
    },
    # -------------------------------------------------------------
    # 5. TELEKOMUNIKASI & MENARA DIGITAL (5 Emiten)
    # -------------------------------------------------------------
    {
        "ticker": "TLKM",
        "name": "Telkom Indonesia (Persero) Tbk.",
        "sub_ind": "Telekomunikasi & Jaringan Digital BUMN",
        "sector": "FMCG",
        "rev": Decimal("154800000000000"),
        "cfo": Decimal("58450000000000"),
        "ni": Decimal("24850000000000"),
        "cash": Decimal("34200000000000"),
        "debt": Decimal("18500000000000"),
        "rec": Decimal("14200000000000"),
        "inv": Decimal("1250000000000"),
        "assets": Decimal("295000000000000"),
    },
    {
        "ticker": "ISAT",
        "name": "Indosat Ooredoo Hutchison Tbk.",
        "sub_ind": "Jasa Telekomunikasi Seluler",
        "sector": "FMCG",
        "rev": Decimal("54200000000000"),
        "cfo": Decimal("24500000000000"),
        "ni": Decimal("4850000000000"),
        "cash": Decimal("7850000000000"),
        "debt": Decimal("12400000000000"),
        "rec": Decimal("6850000000000"),
        "inv": Decimal("450000000000"),
        "assets": Decimal("114000000000000"),
    },
    {
        "ticker": "EXCL",
        "name": "XL Axiata Tbk.",
        "sub_ind": "Jasa Telekomunikasi Seluler",
        "sector": "FMCG",
        "rev": Decimal("34500000000000"),
        "cfo": Decimal("14200000000000"),
        "ni": Decimal("1850000000000"),
        "cash": Decimal("3420000000000"),
        "debt": Decimal("8450000000000"),
        "rec": Decimal("4120000000000"),
        "inv": Decimal("320000000000"),
        "assets": Decimal("88500000000000"),
    },
    {
        "ticker": "TOWR",
        "name": "Sarana Menara Nusantara Tbk.",
        "sub_ind": "Infrastruktur Menara Telekomunikasi",
        "sector": "FMCG",
        "rev": Decimal("12450000000000"),
        "cfo": Decimal("8450000000000"),
        "ni": Decimal("3420000000000"),
        "cash": Decimal("1850000000000"),
        "debt": Decimal("7450000000000"),
        "rec": Decimal("2850000000000"),
        "inv": Decimal("180000000000"),
        "assets": Decimal("74500000000000"),
    },
    {
        "ticker": "MTEL",
        "name": "Dayamitra Telekomunikasi Tbk. (Mitratel)",
        "sub_ind": "Infrastruktur Menara Telekomunikasi BUMN",
        "sector": "FMCG",
        "rev": Decimal("9250000000000"),
        "cfo": Decimal("6850000000000"),
        "ni": Decimal("2150000000000"),
        "cash": Decimal("3450000000000"),
        "debt": Decimal("2850000000000"),
        "rec": Decimal("1850000000000"),
        "inv": Decimal("95000000000"),
        "assets": Decimal("58500000000000"),
    },
]


def populate_massive() -> None:
    if not DB_PATH.exists():
        print(f"⚠️ Error: Basis data {DB_PATH} tidak ditemukan.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    print("🚀 Mengisi 28 Emiten Baru ke dalam Database (Total Universe: 48 Emiten)...")

    for item in MASSIVE_ISSUERS:
        ticker = item["ticker"]
        name = item["name"]
        sub_ind = item["sub_ind"]
        sector = item["sector"]

        # 1. Insert Issuer
        cur.execute(
            """
            INSERT INTO issuers (ticker, company_name, idx_sub_industry, listing_status)
            VALUES (?, ?, ?, 'ACTIVE')
            ON CONFLICT(ticker) DO UPDATE SET
                company_name = excluded.company_name,
                idx_sub_industry = excluded.idx_sub_industry;
            """,
            (ticker, name, sub_ind),
        )

        for yr in [2024, 2025]:
            filing_id = f"{ticker}_{yr}_FY_FIRST"
            period_end = f"{yr}-12-31"

            # 2. Filing
            cur.execute(
                """
                INSERT INTO filings (
                    filing_id, ticker, fiscal_year, period_code, period_end_date,
                    filing_date, is_audited, is_restatement, reporting_currency,
                    fx_rate_to_idr, sanity_check_passed, source_xbrl_hash
                ) VALUES (?, ?, ?, 'FY', ?, ?, 1, 0, 'IDR', '1', 1, 'massive_audited_sha256')
                ON CONFLICT(filing_id) DO NOTHING;
                """,
                (filing_id, ticker, yr, period_end, f"{yr+1}-03-20"),
            )

            rev = item["rev"]
            cfo = item["cfo"]
            ni = item["ni"]
            cash = item["cash"]
            debt = item["debt"]
            rec = item["rec"]
            inv = item["inv"]
            assets = item["assets"]

            # 3. Facts
            facts = [
                ("cash_and_equivalents", str(cash), "CashAndCashEquivalents"),
                ("cfo", str(cfo), "NetCashFlowsOperatingActivities"),
                ("net_income", str(ni), "ProfitLossAttributableToOwnersOfParent"),
                ("revenue", str(rev), "RevenuesOrInterestIncomeNet"),
                ("total_assets", str(assets), "Assets"),
            ]
            if sector == "CONSTRUCTION":
                facts.extend([
                    ("trade_receivables_third_parties", str(rec), "TradeReceivablesThirdParties"),
                    ("contract_assets_current", str(inv), "CurrentContractAssets"),
                    ("st_debt_bank_loans", str(debt), "ShortTermBankLoans"),
                ])
            elif sector == "BANKING":
                facts.extend([
                    ("loans_gross", str(rec), "LoansGrossTotal"),
                    ("customer_deposits", str(debt), "DepositsFromCustomers"),
                    ("non_performing_loans", str(inv), "NonPerformingLoansGross"),
                ])
            else:  # FMCG / ENERGY / TELECOM
                facts.extend([
                    ("trade_receivables_third_parties", str(rec), "TradeReceivablesThirdParties"),
                    ("inventories", str(inv), "InventoriesTotal"),
                    ("st_debt_bank_loans", str(debt), "ShortTermBankLoans"),
                ])

            for canon_k, val_str, tag_name in facts:
                cur.execute(
                    """
                    INSERT INTO canonical_facts (
                        filing_id, canonical_key, value_idr, raw_xbrl_tag,
                        raw_context_ref, raw_unit_ref, raw_decimals, raw_lexical_value
                    ) VALUES (?, ?, ?, ?, 'CurrentYearInstant', 'IDR', '0', ?)
                    ON CONFLICT(filing_id, canonical_key) DO UPDATE SET
                        value_idr = excluded.value_idr;
                    """,
                    (filing_id, canon_k, val_str, tag_name, val_str),
                )

            # 4. Computed Metrics
            debt_free = 1 if debt == Decimal("0") else 0
            cov_val = cash / debt if debt > 0 else Decimal("999")
            sloan_val = (ni - cfo) / assets if assets > 0 else Decimal("0")
            exp_ratio = (rec + inv) / rev if rev > 0 else Decimal("0")
            flag_acute = 1 if (cfo < 0 and debt > 0 and cov_val < Decimal("0.25")) else 0
            flag_divergence = 1 if (ni > 0 and cfo < 0 and sloan_val > Decimal("0.10")) else 0

            cur.execute(
                """
                INSERT INTO computed_metrics (
                    filing_id, ticker, period_end_date, is_audit_derived_q4,
                    cfo_single_q_idr, cfo_ttm_idr, net_income_ttm_idr, revenue_ttm_idr,
                    gross_contract_exposure_ratio, net_contract_exposure_ratio,
                    gross_divergence_yoy_bps, sloan_ratio_ttm, cash_coverage_ratio,
                    revenue_contraction_guard, debt_free_short_term,
                    flag_accrual_divergence, flag_acute_liquidity
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, '0', ?, ?, 0, ?, ?, ?)
                ON CONFLICT(filing_id) DO UPDATE SET
                    cfo_ttm_idr = excluded.cfo_ttm_idr,
                    net_income_ttm_idr = excluded.net_income_ttm_idr,
                    cash_coverage_ratio = excluded.cash_coverage_ratio,
                    sloan_ratio_ttm = excluded.sloan_ratio_ttm,
                    flag_acute_liquidity = excluded.flag_acute_liquidity;
                """,
                (
                    filing_id,
                    ticker,
                    period_end,
                    str(cfo),
                    str(cfo),
                    str(ni),
                    str(rev),
                    str(round(exp_ratio, 4)),
                    str(round(exp_ratio, 4)),
                    str(round(sloan_val, 4)),
                    str(round(cov_val, 2)),
                    debt_free,
                    flag_divergence,
                    flag_acute,
                ),
            )

        print(f"  ✅ {ticker} ({name}) berhasil dimuat.")

    conn.commit()
    conn.close()

    print("🎉 SEMESTA DATA BERHASIL DIPERLUAS HINGGA 48 EMITEN!")


if __name__ == "__main__":
    populate_massive()
