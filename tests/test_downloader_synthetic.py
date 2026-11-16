"""
Unit tests for Gate 5 Automated Downloader & XBRL Pipeline.
Tests zip extraction, corrupt file guards, idempotency, and manifest logging.
"""

import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.download_idx_filings import (
    compute_file_hash,
    download_filing,
    extract_xbrl_from_zip,
    import_local_zips,
    load_manifest,
    save_manifest,
)


def create_dummy_xbrl_zip(filename: str = "instance.xbrl", content: str = "<xbrl></xbrl>") -> bytes:
    """Helper creating an in-memory valid zip containing an xbrl file."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


def test_extract_xbrl_from_valid_zip(tmp_path: Path):
    dest_dir = tmp_path / "extracted"
    zip_path = tmp_path / "valid.zip"
    zip_bytes = create_dummy_xbrl_zip("instance_sample.xbrl", "<xbrl><fact>100</fact></xbrl>")
    zip_path.write_bytes(zip_bytes)

    result = extract_xbrl_from_zip(zip_path, dest_dir, "instance_TEST_2023_FY")
    assert result is not None
    assert result.exists()
    assert result.suffix == ".xbrl"
    assert "<xbrl><fact>100</fact></xbrl>" in result.read_text(encoding="utf-8")


def test_extract_xbrl_from_corrupt_zip(tmp_path: Path):
    dest_dir = tmp_path / "extracted"
    corrupt_zip = tmp_path / "corrupt.zip"
    # Write arbitrary non-zip corrupted bytes
    corrupt_zip.write_bytes(b"PK\x03\x04CORRUPTED_ZIP_STREAM_RANDOM_DATA_GARBAGE")

    result = extract_xbrl_from_zip(corrupt_zip, dest_dir, "instance_TEST_2023_FY")
    assert result is None
    # Ensure no partial corrupted xbrl was generated
    assert not list(dest_dir.glob("*.xbrl"))


def test_download_filing_idempotent_skip(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    target_dir = raw_dir / "ADHI" / "2023"
    target_dir.mkdir(parents=True, exist_ok=True)

    dummy_file = target_dir / "instance_ADHI_2023_FY.xbrl"
    dummy_file.write_text("<xbrl>TEST_CONTENT</xbrl>", encoding="utf-8")
    file_hash = compute_file_hash(dummy_file)

    manifest = {
        "ADHI_2023_FY": {
            "ticker": "ADHI",
            "year": 2023,
            "period": "FY",
            "xbrl_path": str(dummy_file.relative_to(tmp_path.parent.parent)),
            "sha256": file_hash,
            "status": "COMPLETED",
        }
    }

    # Patch ROOT_DIR in scripts.download_idx_filings to tmp_path's grand-parent
    with patch("scripts.download_idx_filings.ROOT_DIR", tmp_path.parent.parent):
        with patch("scripts.download_idx_filings.query_idx_report_api") as mock_api:
            # Should skip because hash and manifest match
            ok = download_filing(
                ticker="ADHI",
                year=2023,
                period="FY",
                raw_dir=raw_dir,
                manifest=manifest,
                delay_range=(0.0, 0.0),
            )
            assert ok is True
            # API should not be called because it was skipped idempotently
            mock_api.assert_not_called()


def test_download_filing_corrupt_zip_handling(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    manifest: dict = {}

    # Mock API returning an attachment
    mock_results = [
        {
            "Attachments": [
                {
                    "File_Name": "FinancialReport_instance.zip",
                    "File_Path": "/files/attachment.zip",
                }
            ]
        }
    ]

    # Mock urlopen returning corrupted bytes
    mock_response = MagicMock()
    mock_response.read.return_value = b"NOT_A_VALID_ZIP_FILE_RANDOM_BYTES"
    mock_response.__enter__.return_value = mock_response

    with patch("scripts.download_idx_filings.query_idx_report_api", return_value=mock_results):
        with patch("urllib.request.urlopen", return_value=mock_response):
            ok = download_filing(
                ticker="PTPP",
                year=2023,
                period="FY",
                raw_dir=raw_dir,
                manifest=manifest,
                delay_range=(0.0, 0.0),
            )
            assert ok is False
            assert "PTPP_2023_FY" in manifest
            assert manifest["PTPP_2023_FY"]["status"] == "FAILED_CORRUPT"


def test_import_local_zips_batch(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = tmp_path / "raw"
    manifest_path = tmp_path / "manifest.json"

    # Create 2 valid dummy zips
    (source_dir / "instance_WIKA.zip").write_bytes(
        create_dummy_xbrl_zip("instance_wika.xbrl", "<xbrl>WIKA_DATA</xbrl>")
    )
    (source_dir / "instance_TOTL_2023_TW3.zip").write_bytes(
        create_dummy_xbrl_zip("instance_totl.xbrl", "<xbrl>TOTL_DATA</xbrl>")
    )

    with patch("scripts.download_idx_filings.ROOT_DIR", tmp_path):
        count = import_local_zips(
            source_dir=source_dir,
            raw_dir=raw_dir,
            manifest_path=manifest_path,
        )
        assert count == 2

        manifest = load_manifest(manifest_path)
        assert "WIKA_2023_FY" in manifest
        assert "TOTL_2023_TW3" in manifest
        assert manifest["WIKA_2023_FY"]["status"] == "COMPLETED"
        assert manifest["TOTL_2023_TW3"]["status"] == "COMPLETED"


def test_manifest_save_and_load(tmp_path: Path):
    manifest_file = tmp_path / "test_manifest.json"
    data = {"KEY": {"status": "TEST"}}
    save_manifest(manifest_file, data)

    loaded = load_manifest(manifest_file)
    assert loaded == data
