"""
Tests for Gate 0: XBRL Taxonomy Spike audit script.
Uses synthetic XBRL XML fixtures (zero real BEI filings).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml
from lxml import etree

from scripts.spike_xbrl_audit import (
    SANITY_TOLERANCE_IDR,
    audit_xbrl_file,
    evaluate_4way_sanity_check,
    extract_xbrl_facts,
    get_elem_localname,
    get_latest_periods,
    parse_context,
    run_spike_audit,
)
from tests.fixtures.synthetic_xbrl.generator import generate_mock_xbrl


def test_zero_dimension_context_filter() -> None:
    """Verifies that dimensional contexts (segment, scenario) are strictly filtered out."""
    mock_xml = generate_mock_xbrl(include_dimensional_contexts=True)
    tree = etree.fromstring(mock_xml.encode("utf-8"))

    contexts = {}
    for elem in tree.iter():
        if get_elem_localname(elem).lower() == "context":
            ctx = parse_context(elem)
            contexts[ctx.context_id] = ctx

    # Check zero-dim contexts
    assert "C_Current_Instant" in contexts
    assert contexts["C_Current_Instant"].is_zero_dimension is True

    assert "C_Current_Duration" in contexts
    assert contexts["C_Current_Duration"].is_zero_dimension is True

    # Check dimensional contexts are flagged False
    assert "C_Segment_Precast" in contexts
    assert contexts["C_Segment_Precast"].is_zero_dimension is False
    assert any(
        tag.lower() in ("segment", "explicitmember")
        for tag in contexts["C_Segment_Precast"].dimension_tags_found
    )

    assert "C_Scenario_Restatement" in contexts
    assert contexts["C_Scenario_Restatement"].is_zero_dimension is False
    assert any(
        tag.lower() in ("scenario", "typedmember")
        for tag in contexts["C_Scenario_Restatement"].dimension_tags_found
    )

    # Check that extract_xbrl_facts completely ignores facts referencing dimensional contexts
    xml_tree = etree.ElementTree(tree)
    ctx_map, facts, currencies = extract_xbrl_facts(xml_tree)

    fact_context_refs = {f.context_ref for f in facts}
    assert "C_Current_Instant" in fact_context_refs
    assert "C_Current_Duration" in fact_context_refs
    assert "C_Segment_Precast" not in fact_context_refs
    assert "C_Scenario_Restatement" not in fact_context_refs


def test_4way_sanity_check_balanced() -> None:
    """Verifies that 4-Way Sanity Check passes when all accounting identities hold exactly."""
    mock_xml = generate_mock_xbrl(
        assets=100_000_000_000,
        current_assets=40_000_000_000,
        non_current_assets=60_000_000_000,
        liabilities=70_000_000_000,
        current_liabilities=30_000_000_000,
        non_current_liabilities=40_000_000_000,
        equity=30_000_000_000,
        cash_bs=5_000_000_000,
        cash_cf=5_000_000_000,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".xbrl", delete=False, encoding="utf-8") as f:
        f.write(mock_xml)
        temp_path = Path(f.name)

    try:
        report = audit_xbrl_file(temp_path)
        assert report.sanity_check.all_passed is True
        for check in report.sanity_check.checks:
            assert check.passed is True, f"Check failed unexpectedly: {check.name}"
    finally:
        temp_path.unlink(missing_ok=True)


def test_4way_sanity_check_detects_unbalanced_balance_sheet() -> None:
    """Verifies that 4-Way Sanity Check fails when Assets != Liabilities + Equity."""
    # Assets = 100B, Liab + Equity = 70B + 20B = 90B (diff = 10B >> 1,000,000)
    mock_xml = generate_mock_xbrl(
        assets=100_000_000_000,
        liabilities=70_000_000_000,
        equity=20_000_000_000,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".xbrl", delete=False, encoding="utf-8") as f:
        f.write(mock_xml)
        temp_path = Path(f.name)

    try:
        report = audit_xbrl_file(temp_path)
        assert report.sanity_check.all_passed is False
        check1 = report.sanity_check.checks[0]
        assert check1.name == "1. Assets == Liabilities + Equity"
        assert check1.passed is False
        assert check1.difference == "10000000000"
    finally:
        temp_path.unlink(missing_ok=True)


def test_4way_sanity_check_detects_unbalanced_current_noncurrent_assets() -> None:
    """Verifies that check fails when Assets != Current Assets + NonCurrent Assets."""
    # Assets = 100B, CA + NCA = 40B + 50B = 90B
    mock_xml = generate_mock_xbrl(
        assets=100_000_000_000,
        current_assets=40_000_000_000,
        non_current_assets=50_000_000_000,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".xbrl", delete=False, encoding="utf-8") as f:
        f.write(mock_xml)
        temp_path = Path(f.name)

    try:
        report = audit_xbrl_file(temp_path)
        assert report.sanity_check.all_passed is False
        check2 = next(
            c for c in report.sanity_check.checks
            if "Current + Non-Current Assets" in c.name
        )
        assert check2.passed is False
        assert check2.difference == "10000000000"
    finally:
        temp_path.unlink(missing_ok=True)


def test_4way_sanity_check_detects_cash_mismatch() -> None:
    """Verifies that check fails when CF ending cash does not match Balance Sheet cash."""
    # Cash BS = 5B, Cash CF = 4B (diff 1B >> 1,000,000)
    mock_xml = generate_mock_xbrl(
        cash_bs=5_000_000_000,
        cash_cf=4_000_000_000,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".xbrl", delete=False, encoding="utf-8") as f:
        f.write(mock_xml)
        temp_path = Path(f.name)

    try:
        report = audit_xbrl_file(temp_path)
        assert report.sanity_check.all_passed is False
        check4 = next(c for c in report.sanity_check.checks if "Cash CF Ending" in c.name)
        assert check4.passed is False
        assert check4.difference == "1000000000"
    finally:
        temp_path.unlink(missing_ok=True)


def test_4way_sanity_check_passes_within_1m_rounding_tolerance() -> None:
    """Verifies that rounding discrepancies <= Rp 1.000.000 are tolerated as per AGENTS.md."""
    # Discrepancy of 500,000 IDR (less than 1,000,000 tolerance)
    small_diff = 500_000
    mock_xml = generate_mock_xbrl(
        assets=100_000_000_000,
        liabilities=70_000_000_000,
        equity=30_000_000_000 - small_diff,
        cash_bs=5_000_000_000,
        cash_cf=5_000_000_000 - small_diff,
    )
    tree = etree.fromstring(mock_xml.encode("utf-8"))
    xml_tree = etree.ElementTree(tree)
    contexts, facts, _ = extract_xbrl_facts(xml_tree)
    instant_date, dur_id = get_latest_periods(contexts)

    report = evaluate_4way_sanity_check(facts, contexts, instant_date, dur_id)
    assert report.all_passed is True
    check1 = report.checks[0]
    assert check1.passed is True
    assert check1.difference == str(small_diff)
    assert int(check1.difference) <= SANITY_TOLERANCE_IDR


def test_detect_key_items_and_run_spike_audit() -> None:
    """Verifies tag detection for key items and full run_spike_audit output generation."""
    mock_xml = generate_mock_xbrl(ticker="WIKA")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        sample_file = tmp_path / "WIKA_2023_FY.xbrl"
        sample_file.write_text(mock_xml, encoding="utf-8")

        output_json = tmp_path / "spike_results.json"
        audit_output = run_spike_audit(samples_dir=tmp_path, output_json=output_json)

        assert output_json.exists()
        assert audit_output["summary"]["total_files_audited"] == 1
        assert audit_output["summary"]["files_passed_sanity"] == 1
        assert audit_output["summary"]["files_failed_sanity"] == 0

        detected = audit_output["taxonomy_variations_detected"]
        assert "cash_and_equivalents" in detected
        assert len(detected["cash_and_equivalents"]) > 0
        assert "trade_receivables_third_parties" in detected
        assert "contract_assets_current" in detected
        assert "st_debt_bank_loans" in detected
        assert "revenue" in detected
        assert "net_income" in detected
        assert "cfo" in detected


def test_taxonomy_mapping_yaml_validity() -> None:
    """Verifies that config/taxonomy_mapping.yaml exists and contains all required pos keys."""
    config_path = Path("config/taxonomy_mapping.yaml")
    assert config_path.exists(), "config/taxonomy_mapping.yaml must exist after Spike"

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "canonical_tags" in data
    tags = data["canonical_tags"]
    required_keys = [
        "cash_and_equivalents",
        "trade_receivables",
        "contract_assets",
        "contract_liabilities",
        "short_term_interest_bearing_debt",
        "revenue",
        "net_income",
        "cfo",
    ]
    for key in required_keys:
        assert key in tags, f"Missing required canonical key: {key}"
