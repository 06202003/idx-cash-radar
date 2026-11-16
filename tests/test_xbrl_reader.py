"""
Tests for pure lxml XBRL Reader module.
Verifies zero-dimension context extraction, hash calculation, and period detection.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.parser.xbrl_reader import read_xbrl_document
from tests.fixtures.synthetic_xbrl.generator import generate_mock_xbrl


def test_xbrl_reader_parses_document_and_computes_hash() -> None:
    """Verifies that read_xbrl_document computes SHA-256 and extracts zero-dim facts."""
    mock_xml = generate_mock_xbrl(
        ticker="WIKA",
        instant_date="2023-12-31",
        include_dimensional_contexts=True,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".xbrl", delete=False, encoding="utf-8") as f:
        f.write(mock_xml)
        temp_path = Path(f.name)

    try:
        doc = read_xbrl_document(temp_path)
        assert doc.ticker == "WIKA"
        assert doc.fiscal_year == 2023
        assert doc.period_code == "FY"
        assert doc.primary_instant_date == "2023-12-31"
        assert len(doc.source_hash) == 64  # SHA-256 hex string

        # Facts count should only contain zero-dim facts
        dim_context_ids = {
            cid for cid, ctx in doc.contexts.items() if not ctx.is_zero_dimension
        }
        for f_item in doc.facts:
            assert f_item.context_ref not in dim_context_ids
    finally:
        temp_path.unlink(missing_ok=True)
