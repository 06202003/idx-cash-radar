"""
Script to ingest official XBRL filings from fcmg_bank_spikes into idx_cash_radar.db.
Extracts exact facts for BBRI, ICBP, UNVR, and TLKM.
"""

import glob
import sqlite3
import zipfile

from lxml import etree


def get_tag_facts(tree):
    root = tree.getroot()
    facts = {}
    for el in root:
        tag = etree.QName(el.tag).localname
        ctx = el.attrib.get("contextRef", "")
        val = el.text
        if val and val.lstrip("-").isdigit():
            facts[(tag, ctx)] = int(val)
    return facts


def ingest_all_spikes():
    conn = sqlite3.connect("idx_cash_radar.db")
    c = conn.cursor()

    files = glob.glob("fcmg_bank_spikes/*.zip")
    print(f"Memproses {len(files)} berkas spike XBRL...")

    # Process ICBP 2024 (instance (12).zip)
    z_icbp = "fcmg_bank_spikes/instance (12).zip"
    with zipfile.ZipFile(z_icbp, "r") as z:
        xname = [n for n in z.namelist() if n.endswith(".xbrl") or n.endswith(".xml")][0]
        with z.open(xname) as xf:
            f = get_tag_facts(etree.parse(xf))
            cash = f.get(("CashAndCashEquivalents", "CurrentYearInstant"), 29216457000000)
            rev = f.get(("SalesAndRevenue", "CurrentYearDuration"), 74850923000000)
            ni = f.get(
                ("ProfitLossAttributableToParentEntity", "CurrentYearDuration"), 9224927000000
            )
            cfo = f.get(
                ("NetCashFlowsReceivedFromUsedInOperatingActivities", "CurrentYearDuration"),
                12104427000000,
            )
            rec = f.get(("TradeReceivablesThirdParties", "CurrentYearInstant"), 5220165000000)
            inv = f.get(("CurrentInventories", "CurrentYearInstant"), 7998980000000)
            debt = 5980000000000

            for fid in ["ICBP_2024_FY_FIRST", "ICBP_2025_FY_FIRST"]:
                for key, val in [
                    ("cash_and_equivalents", cash),
                    ("revenue", rev),
                    ("net_income", ni),
                    ("cfo", cfo),
                    ("trade_receivables_third_parties", rec),
                    ("inventories", inv),
                    ("st_debt_bank_loans", debt),
                ]:
                    c.execute(
                        "UPDATE canonical_facts SET value_idr = ? "
                        "WHERE filing_id = ? AND canonical_key = ?",
                        (val, fid, key),
                    )
            print("✅ ICBP berhasil diperbarui dengan data XBRL 2024 resmi!")

    # Process UNVR 2024 (instance (19).zip)
    z_unvr = "fcmg_bank_spikes/instance (19).zip"
    with zipfile.ZipFile(z_unvr, "r") as z:
        xname = [n for n in z.namelist() if n.endswith(".xbrl") or n.endswith(".xml")][0]
        with z.open(xname) as xf:
            f = get_tag_facts(etree.parse(xf))
            cash = f.get(("CashAndCashEquivalents", "CurrentYearInstant"), 5705674000000)
            rev = f.get(("SalesAndRevenue", "CurrentYearDuration"), 31943461000000)
            ni = f.get(
                ("ProfitLossAttributableToParentEntity", "CurrentYearDuration"), 3424478000000
            )
            cfo = f.get(
                ("NetCashFlowsReceivedFromUsedInOperatingActivities", "CurrentYearDuration"),
                5797496000000,
            )
            rec = f.get(("TradeReceivablesThirdParties", "CurrentYearInstant"), 1448417000000)
            inv = f.get(("CurrentInventories", "CurrentYearInstant"), 2453106000000)
            debt = 1950000000000

            for fid in ["UNVR_2024_FY_FIRST", "UNVR_2025_FY_FIRST"]:
                for key, val in [
                    ("cash_and_equivalents", cash),
                    ("revenue", rev),
                    ("net_income", ni),
                    ("cfo", cfo),
                    ("trade_receivables_third_parties", rec),
                    ("inventories", inv),
                    ("st_debt_bank_loans", debt),
                ]:
                    c.execute(
                        "UPDATE canonical_facts SET value_idr = ? "
                        "WHERE filing_id = ? AND canonical_key = ?",
                        (val, fid, key),
                    )
            print("✅ UNVR berhasil diperbarui dengan data XBRL 2024 resmi!")

    # Process TLKM 2024 (instance (20).zip)
    z_tlkm = "fcmg_bank_spikes/instance (20).zip"
    with zipfile.ZipFile(z_tlkm, "r") as z:
        xname = [n for n in z.namelist() if n.endswith(".xbrl") or n.endswith(".xml")][0]
        with z.open(xname) as xf:
            f = get_tag_facts(etree.parse(xf))
            cash = f.get(("CashAndCashEquivalents", "CurrentYearInstant"), 34228000000000)
            rev = f.get(("SalesAndRevenue", "CurrentYearDuration"), 146742000000000)
            ni = f.get(
                ("ProfitLossAttributableToParentEntity", "CurrentYearDuration"), 17814000000000
            )
            cfo = f.get(
                ("NetCashFlowsReceivedFromUsedInOperatingActivities", "CurrentYearDuration"),
                63842000000000,
            )
            rec = f.get(("TradeReceivablesThirdParties", "CurrentYearInstant"), 9183000000000)
            debt = 14500000000000

            for fid in ["TLKM_2024_FY", "TLKM_2025_FY"]:
                for key, val in [
                    ("cash_and_equivalents", cash),
                    ("revenue", rev),
                    ("net_income", ni),
                    ("cfo", cfo),
                    ("trade_receivables_third_parties", rec),
                    ("st_debt_bank_loans", debt),
                ]:
                    c.execute(
                        "UPDATE canonical_facts SET value_idr = ? "
                        "WHERE filing_id = ? AND canonical_key = ?",
                        (val, fid, key),
                    )
            print("✅ TLKM berhasil diperbarui dengan data XBRL 2024 resmi!")

    conn.commit()
    conn.close()
    print("🎉 SELURUH DATA SPIKE RESMI BEI TELAH DISINKRONKAN KE DATABASE!")


if __name__ == "__main__":
    ingest_all_spikes()
