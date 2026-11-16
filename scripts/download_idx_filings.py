"""
Automated IDX Filing Downloader & XBRL Pipeline Ingestion Tool.
Gate 5 Implementation according to AGENTS.md v2.0 Section 8.
Supports idempotent downloads, SHA-256 integrity checks, zip extraction,
and batch directory imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from lxml import etree

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Core Construction Tickers mandated in Gate 5
CORE_CONSTRUCTION_TICKERS = [
    "ADHI",
    "PTPP",
    "WIKA",
    "WSKT",
    "TOTL",
    "NRCA",
    "JKON",
    "ACST",
    "WEGE",
    "PPRE",
    "DGIK",
    "PBSA",
]

DEFAULT_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
DEFAULT_PERIODS = ["FY", "TW3", "TW2", "TW1"]

DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_RAW_DIR = DEFAULT_DATA_DIR / "raw_xbrl"
DEFAULT_MANIFEST_PATH = DEFAULT_DATA_DIR / "download_manifest.json"


def compute_file_hash(filepath: Path) -> str:
    """Calculates SHA-256 hash of a file for integrity verification."""
    sha = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def load_manifest(manifest_path: Path) -> dict[str, dict]:
    """Loads download manifest from JSON file."""
    if not manifest_path.exists():
        return {}
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"⚠️ Warning: Gagal membaca manifest {manifest_path}: {exc}. Menginisialisasi ulang.")
        return {}


def save_manifest(manifest_path: Path, manifest: dict[str, dict]) -> None:
    """Persists download manifest to JSON file."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def extract_xbrl_from_zip(zip_path: Path, dest_dir: Path, file_stem: str) -> Path | None:
    """
    Extracts .xbrl file from zip package into dest_dir.
    Guards against corrupt zip archives.
    Returns path to extracted .xbrl or None if invalid/corrupt.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not zipfile.is_zipfile(zip_path):
        print(f"❌ Corrupt/Invalid zip: {zip_path.name}")
        return None

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                print(f"❌ Corrupt zip archive member detected ({bad_file}) in {zip_path.name}")
                return None

            # Look for .xbrl file in archive
            xbrl_candidates = [
                name for name in zf.namelist()
                if name.lower().endswith(".xbrl") or name.lower().endswith(".xml")
            ]
            if not xbrl_candidates:
                print(f"⚠️ No XBRL/XML instance file found in zip: {zip_path.name}")
                return None

            # Prefer file with 'instance' in name
            target_entry = xbrl_candidates[0]
            for cand in xbrl_candidates:
                if "instance" in cand.lower():
                    target_entry = cand
                    break

            out_xbrl_path = dest_dir / f"{file_stem}.xbrl"
            with zf.open(target_entry) as source, out_xbrl_path.open("wb") as target:
                target.write(source.read())

            return out_xbrl_path
    except zipfile.BadZipFile as exc:
        print(f"❌ BadZipFile error reading {zip_path.name}: {exc}")
        return None
    except Exception as exc:
        print(f"❌ Unexpected error extracting {zip_path.name}: {exc}")
        return None


def detect_filing_metadata(item: Path) -> tuple[str | None, int | None, str]:
    """
    Detects ticker, year, and period. Checks filename first, then inspects XML content
    directly if filename is generic (e.g. 'instance (1).zip').
    """
    ticker_mapping = {
        "ADHI": "ADHI",
        "PTPP": "PTPP",
        "WIKA": "WIKA",
        "WSKT": "WSKT",
        "WEGE": "WEGE",
        "PPRE": "PPRE",
        "TOTL": "TOTL",
        "NRCA": "NRCA",
        "ACST": "ACST",
        "JKON": "JKON",
        "DGIK": "DGIK",
        "PBSA": "PBSA",
    }
    name = item.name.upper()
    matched_ticker = None
    for ticker in CORE_CONSTRUCTION_TICKERS:
        if ticker in name:
            matched_ticker = ticker
            break

    year_match = re.search(r"201\d|202\d", name)
    year = int(year_match.group(0)) if year_match else (2023 if matched_ticker else None)

    period = "FY"
    if "TW3" in name or "Q3" in name:
        period = "TW3"
    elif "TW2" in name or "Q2" in name:
        period = "TW2"
    elif "TW1" in name or "Q1" in name:
        period = "TW1"

    if matched_ticker and year:
        return matched_ticker, year, period

    # Inspect XML inside file or zip
    try:
        raw_xml = None
        if item.suffix.lower() == ".zip":
            with zipfile.ZipFile(item, "r") as zf:
                xbrl_names = [n for n in zf.namelist() if n.lower().endswith((".xbrl", ".xml"))]
                if xbrl_names:
                    raw_xml = zf.read(xbrl_names[0])
        elif item.suffix.lower() in (".xbrl", ".xml"):
            raw_xml = item.read_bytes()

        if raw_xml:
            root = etree.fromstring(raw_xml)
            ns = {"xbrli": "http://www.xbrl.org/2003/instance"}
            ids = root.xpath("//xbrli:identifier/text()", namespaces=ns)
            if ids:
                raw_id = ids[0].strip().upper()
                for k, v in ticker_mapping.items():
                    if k in raw_id:
                        matched_ticker = v
                        break
                if not matched_ticker:
                    matched_ticker = raw_id[:4]

            dates = root.xpath("//xbrli:endDate/text() | //xbrli:instant/text()", namespaces=ns)
            if dates:
                m = max(dates)
                year = int(m[:4])
                mon = m[5:7] if len(m) >= 7 else "12"
                period = "FY" if mon == "12" else f"TW{int(mon)//3}"
    except Exception:
        pass

    return matched_ticker, year, period


def import_local_zips(
    source_dir: Path,
    raw_dir: Path = DEFAULT_RAW_DIR,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> int:
    """
    Batch imports local .zip or .xbrl files (e.g. from spikes/ or manual downloads)
    into standard data/raw_xbrl/{TICKER}/{YEAR}/ directory structure, updating manifest.
    """
    if not source_dir.exists():
        print(f"⚠️ Source directory does not exist: {source_dir}")
        return 0

    manifest = load_manifest(manifest_path)
    imported_count = 0

    for item in sorted(source_dir.glob("*")):
        if not item.is_file():
            continue

        matched_ticker, year, period = detect_filing_metadata(item)
        if not matched_ticker or not year:
            continue

        year_str = str(year)
        manifest_key = f"{matched_ticker}_{year_str}_{period}"
        target_dir = raw_dir / matched_ticker / year_str
        stem = f"instance_{matched_ticker}_{year_str}_{period}"

        if item.suffix.lower() == ".zip":
            extracted = extract_xbrl_from_zip(item, target_dir, stem)
            if extracted and extracted.exists():
                file_hash = compute_file_hash(extracted)
                manifest[manifest_key] = {
                    "ticker": matched_ticker,
                    "year": int(year_str),
                    "period": period,
                    "xbrl_path": str(extracted.relative_to(ROOT_DIR)),
                    "sha256": file_hash,
                    "status": "COMPLETED",
                    "source": "local_import",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                imported_count += 1
                print(f"✅ Imported {matched_ticker} {year_str} {period} -> {extracted.name}")
        elif item.suffix.lower() in (".xbrl", ".xml"):
            target_dir.mkdir(parents=True, exist_ok=True)
            out_path = target_dir / f"{stem}.xbrl"
            if item.resolve() != out_path.resolve():
                out_path.write_bytes(item.read_bytes())
            file_hash = compute_file_hash(out_path)
            manifest[manifest_key] = {
                "ticker": matched_ticker,
                "year": int(year_str),
                "period": period,
                "xbrl_path": str(out_path.relative_to(ROOT_DIR)),
                "sha256": file_hash,
                "status": "COMPLETED",
                "source": "local_import",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            imported_count += 1
            print(f"✅ Imported raw XBRL: {matched_ticker} {year_str} {period}")

    save_manifest(manifest_path, manifest)
    print(f"📁 Total files successfully imported to manifest: {imported_count}")
    return imported_count


def query_idx_report_api(
    ticker: str,
    year: int,
    period: str,
    session_cookie: str | None = None,
) -> list[dict]:
    """
    Queries official BEI / IDX JSON endpoint for published financial reports.
    Uses proper headers and rate limiting.
    """
    base_url = "https://www.idx.co.id/primary/FinancialReport/GetFinancialReport"
    # Mapping period to IDX period code
    period_map = {"FY": "Audit", "TW3": "tw3", "TW2": "tw2", "TW1": "tw1"}
    idx_period = period_map.get(period, "Audit")

    params = {
        "indexFrom": 1,
        "pageSize": 20,
        "year": year,
        "reportType": "rdf",
        "period": idx_period,
        "kodeEmiten": ticker,
    }
    query_str = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_str}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    if session_cookie:
        headers["Cookie"] = session_cookie

    req = urllib.request.Request(full_url, headers=headers)
    req_opener = urllib.request.build_opener()

    try:
        with req_opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "Results" in data:
                return data["Results"]
            return []
    except urllib.error.HTTPError as exc:
        print(f"⚠️ HTTP {exc.code} for {ticker} {year} {period}: {exc.reason}")
        return []
    except Exception as exc:
        print(f"⚠️ Network error querying IDX API for {ticker} {year}: {exc}")
        return []


def download_filing(
    ticker: str,
    year: int,
    period: str,
    raw_dir: Path = DEFAULT_RAW_DIR,
    manifest: dict[str, dict] | None = None,
    session_cookie: str | None = None,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> bool:
    """
    Downloads an XBRL filing package for a specific ticker, year, and period.
    Enforces idempotency: skips if already in manifest and file hash matches.
    """
    if manifest is None:
        manifest = {}

    manifest_key = f"{ticker}_{year}_{period}"

    # Idempotent check
    if manifest_key in manifest and manifest[manifest_key].get("status") == "COMPLETED":
        rel_path = manifest[manifest_key].get("xbrl_path")
        if rel_path:
            existing_path = ROOT_DIR / rel_path
            if existing_path.exists():
                curr_hash = compute_file_hash(existing_path)
                if curr_hash == manifest[manifest_key].get("sha256"):
                    print(f"⏩ [IDEMPOTENT SKIP] {manifest_key} already downloaded and verified.")
                    return True

    # Rate limiting delay
    sleep_s = random.uniform(*delay_range)
    time.sleep(sleep_s)

    # 1. Query API for file metadata
    results = query_idx_report_api(ticker, year, period, session_cookie=session_cookie)
    if not results:
        print(f"ℹ️ No report metadata found on IDX for {ticker} {year} {period}.")
        return False

    # Look for zip or instance attachments
    target_attachment = None
    for item in results:
        attachments = item.get("Attachments", [])
        for att in attachments:
            fname = att.get("File_Name", "").lower()
            if "instance" in fname or fname.endswith(".zip") or fname.endswith(".xbrl"):
                target_attachment = att
                break
        if target_attachment:
            break

    if not target_attachment:
        print(f"ℹ️ No XBRL zip attachment found in results for {ticker} {year} {period}.")
        return False

    file_path_url = target_attachment.get("File_Path")
    if not file_path_url:
        return False

    download_url = f"https://www.idx.co.id/{file_path_url.lstrip('/')}"
    target_dir = raw_dir / ticker / str(year)
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_zip_path = target_dir / f"download_{ticker}_{year}_{period}.zip"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/",
    }
    if session_cookie:
        headers["Cookie"] = session_cookie

    try:
        req = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, tmp_zip_path.open("wb") as out_f:
            out_f.write(resp.read())

        # Extract
        stem = f"instance_{ticker}_{year}_{period}"
        extracted = extract_xbrl_from_zip(tmp_zip_path, target_dir, stem)
        if tmp_zip_path.exists():
            tmp_zip_path.unlink()  # Remove zip after extraction

        if extracted and extracted.exists():
            file_hash = compute_file_hash(extracted)
            manifest[manifest_key] = {
                "ticker": ticker,
                "year": year,
                "period": period,
                "xbrl_path": str(extracted.relative_to(ROOT_DIR)),
                "sha256": file_hash,
                "status": "COMPLETED",
                "source": "idx_api",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            print(f"🎉 Successfully downloaded and extracted: {manifest_key}")
            return True
        else:
            manifest[manifest_key] = {
                "ticker": ticker,
                "year": year,
                "period": period,
                "status": "FAILED_CORRUPT",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            return False

    except Exception as exc:
        print(f"❌ Download failed for {ticker} {year}: {exc}")
        if tmp_zip_path.exists():
            tmp_zip_path.unlink()
        manifest[manifest_key] = {
            "ticker": ticker,
            "year": year,
            "period": period,
            "status": "FAILED_NETWORK",
            "error": str(exc),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gate 5 Automated IDX XBRL Filing Downloader & Importer"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=CORE_CONSTRUCTION_TICKERS,
        help="Target stock ticker symbols",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=[2023, 2022, 2021, 2020, 2019],
        help="Target reporting years",
    )
    parser.add_argument(
        "--periods",
        nargs="+",
        default=["FY"],
        help="Reporting periods (FY, TW3, TW2, TW1)",
    )
    parser.add_argument(
        "--import-dir",
        type=Path,
        default=None,
        help="Batch import local directory containing .zip or .xbrl files",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help="Destination directory for raw extracted .xbrl files",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to download manifest JSON file",
    )
    parser.add_argument(
        "--cookie",
        type=str,
        default=None,
        help="Optional session cookie string for BEI portal",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 IDX Cash Radar — Gate 5 Automated Filing Pipeline")
    print("=" * 60)

    # 1. Handle local batch import if requested
    if args.import_dir:
        print(f"📥 Processing batch local import from: {args.import_dir}")
        count = import_local_zips(args.import_dir, args.raw_dir, args.manifest)
        print(f"🏁 Batch import complete. {count} filing(s) processed.")
        return

    # 2. Automated download loop
    manifest = load_manifest(args.manifest)
    total_requested = len(args.tickers) * len(args.years) * len(args.periods)
    success_count = 0

    print(
        f"📋 Target: {len(args.tickers)} tickers across {len(args.years)} years "
        f"({total_requested} filings)"
    )
    print(f"Emiten: {', '.join(args.tickers)}")

    for ticker in args.tickers:
        for year in args.years:
            for period in args.periods:
                ok = download_filing(
                    ticker=ticker,
                    year=year,
                    period=period,
                    raw_dir=args.raw_dir,
                    manifest=manifest,
                    session_cookie=args.cookie,
                )
                save_manifest(args.manifest, manifest)
                if ok:
                    success_count += 1

    print("=" * 60)
    print(f"🏁 Download pipeline run complete: {success_count}/{total_requested} successful.")
    print(f"📁 Manifest saved to: {args.manifest}")


if __name__ == "__main__":
    main()
