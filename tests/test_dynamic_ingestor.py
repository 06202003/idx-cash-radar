"""
Tests for Dynamic Automated XBRL Ingestion Pipeline and Telegram Upload Handler.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.main import handle_document_upload
from src.db.repository import FinancialRepository
from src.parser.dynamic_ingestor import DynamicXBRLIngestor


def test_dynamic_ingestion_from_zip(tmp_path):
    # Use real spike file if available
    spike_path = Path("fcmg_bank_spikes/instance (12).zip")
    if not spike_path.exists():
        pytest.skip("Spike file not found")

    test_db = tmp_path / "dynamic_test.db"
    repo = FinancialRepository(db_path=test_db)
    ingestor = DynamicXBRLIngestor(repo=repo)

    result = ingestor.process_file(spike_path, "instance (12).zip")

    assert result["status"] == "success"
    assert result["ticker"] == "ICBP"
    assert "Indofood CBP" in result["company_name"]
    assert result["facts_count"] > 0
    assert "DIAGNOSTIK KAS" in result["card_text"]

    # Verify persisted in database
    with repo.get_connection() as conn:
        issuer = conn.execute("SELECT * FROM issuers WHERE ticker = 'ICBP'").fetchone()
        assert issuer is not None
        facts = conn.execute(
            "SELECT COUNT(*) as cnt FROM canonical_facts WHERE filing_id LIKE 'ICBP%'"
        ).fetchone()
        assert facts["cnt"] > 0


def test_dynamic_ingestion_invalid_file(tmp_path):
    test_db = tmp_path / "dynamic_test2.db"
    repo = FinancialRepository(db_path=test_db)
    ingestor = DynamicXBRLIngestor(repo=repo)

    result = ingestor.process_file(b"bukan data xml", "invalid.zip")
    assert result["status"] == "error"
    assert "Gagal membaca" in result["message"] or "rusak" in result["message"]


def test_bot_document_upload_handler():
    spike_path = Path("fcmg_bank_spikes/instance (12).zip")
    if not spike_path.exists():
        pytest.skip("Spike file not found")

    file_bytes = spike_path.read_bytes()

    message = MagicMock()
    doc = MagicMock()
    doc.file_name = "instance.zip"
    doc.file_size = len(file_bytes)
    message.document = doc
    message.answer = AsyncMock()
    bot_mock = AsyncMock()

    async def mock_download(file, destination):
        destination.write(file_bytes)

    bot_mock.download = mock_download
    message.bot = bot_mock

    asyncio.run(handle_document_upload(message))

    assert message.answer.call_count >= 2
    last_call = message.answer.call_args[0][0]
    assert "BERKAS RESMI BEI BERHASIL DIEKSTRAK" in last_call
    assert "ICBP" in last_call
