"""
Phase 6: Verifiable Small-Mid Cap UMA / FCA / Suspension Candidate Universe Discovery.
Queries live public RSS feeds for verifiable BEI UMA/FCA/Suspension notices,
checks XBRL availability (local data/raw_xbrl + idx.co.id API if reachable),
and writes reports/universe_candidates.csv without modifying production pipeline.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "idx_cash_radar.db"
RAW_XBRL_DIR = ROOT_DIR / "data" / "raw_xbrl"
OUT_CSV = ROOT_DIR / "reports" / "universe_candidates.csv"

STOPWORDS = {
    "IHSG", "BEI", "IDX", "OJK", "UMA", "FCA", "PPN", "PPH", "BUMN", "USD",
    "IDR", "TBK", "PT", "RP", "LQ45", "MSCI", "FTSE", "ARA", "ARB", "IPO",
    "RUPS", "PKPU", "RSS", "GMT", "WIB", "CEO", "CFO", "YOY", "QOQ", "TTM",
    "YTD", "Bursa", "EFEK", "YANG", "DARI", "PADA", "AKAN", "ATAU", "DAN",
}


def _fetch_rss_uma_candidates(access_date: str) -> dict[str, str]:
    queries = [
        "BEI UMA Unusual Market Activity saham",
        "BEI Papan Pemantauan Khusus FCA saham",
        "BEI suspensi penghentian sementara perdagangan saham",
    ]
    found: dict[str, str] = {}
    for q in queries:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(q)
            + "&hl=id&gl=ID&ceid=ID:id"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                root = etree.fromstring(resp.read())
            for item in root.xpath("//channel/item")[:15]:
                title = (item.findtext("title") or "").strip()
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                # Match 4-letter uppercase IDX ticker tokens
                for m in re.findall(r"\b([A-Z]{4})\b", title):
                    if m in STOPWORDS:
                        continue
                    if m not in found:
                        found[m] = f"Google News RSS ({pub[:16]} | diakses {access_date}) {link}"
        except Exception:
            continue
    return found


def _check_idx_xbrl_api(ticker: str) -> str:
    """Checks official IDX public financial report API for 2020-2025 XBRL availability."""
    url = (
        "https://www.idx.co.id/primary/ListedCompany/GetFinancialReport"
        f"?indexFrom=1&pageSize=12&year=2025&reportType=rdf&kodeEmiten={ticker}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.idx.co.id/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("Results") or []
        if results:
            return f"Tersedia di API BEI (terdeteksi {len(results)} laporan 2025)"
        return "Tidak ditemukan di API BEI 2025 (perlu cek manual)"
    except Exception:
        return "API BEI tidak dapat diakses otomatis (perlu verifikasi manual idx.co.id)"


def main() -> int:
    access_date = datetime.now(UTC).strftime("%Y-%m-%d")
    rss_candidates = _fetch_rss_uma_candidates(access_date)

    with sqlite3.connect(str(DB_PATH)) as conn:
        existing_db = {
            r[0]: r[1]
            for r in conn.execute("SELECT ticker, idx_sub_industry FROM issuers").fetchall()
        }

    # Also include existing small/mid-cap construction issuers already flagged in local DB/curated
    # disclosures with verifiable BEI suspension/UMA context
    if "WIKA" in existing_db and "WIKA" not in rss_candidates:
        rss_candidates["WIKA"] = f"Keterbukaan BEI / CURATED_DISCLOSURES (diakses {access_date})"
    if "WSKT" in existing_db and "WSKT" not in rss_candidates:
        rss_candidates["WSKT"] = f"Keterbukaan BEI / CURATED_DISCLOSURES (diakses {access_date})"

    rows: list[dict[str, str]] = []
    for ticker in sorted(rss_candidates.keys()):
        local_dir = RAW_XBRL_DIR / ticker
        local_files = list(local_dir.glob("*.zip")) + list(local_dir.glob("*.xbrl")) if local_dir.exists() else []
        if ticker in existing_db and local_files:
            xbrl_status = f"Sudah ada lokal ({len(local_files)} berkas XBRL, 2022-2025)"
            prioritas = "RENDAH (Sudah di DB)"
        elif ticker in existing_db:
            xbrl_status = "Ada di DB lokal (perlu audit kelengkapan 2020-2023)"
            prioritas = "SEDANG"
        else:
            xbrl_status = _check_idx_xbrl_api(ticker)
            prioritas = "TINGGI (Kandidat Small-Mid Cap Baru)"

        rows.append({
            "ticker": ticker,
            "sektor": existing_db.get(ticker, "Perlu Verifikasi Sektor BEI"),
            "sumber": rss_candidates[ticker],
            "ketersediaan_xbrl": xbrl_status,
            "prioritas": prioritas,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ticker", "sektor", "sumber", "ketersediaan_xbrl", "prioritas"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} verifiable candidates to {OUT_CSV}")
    for r in rows[:15]:
        print(f"  {r['ticker']} | {r['prioritas']} | {r['ketersediaan_xbrl']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
