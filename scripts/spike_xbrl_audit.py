"""
IDX Cash & Accrual Radar — Gate 0: XBRL Taxonomy Spike
Deterministic audit script for inspecting IDX XBRL instance documents.

Scope:
- Pure zero-dimension context filtering (ignores segment, scenario, explicitMember, typedMember).
- Maps currencies (unitRef), decimals, and detects real tag variations for 8 key items.
- Evaluates 4-Way Accounting Sanity Check with <= Rp 1.000.000 tolerance.
- Outputs spike_results.json and displays tag comparison table across issuers.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from lxml import etree
from pydantic import BaseModel, Field

# Constants & Tolerances locked in AGENTS.md & PRE_REGISTRATION.md
SANITY_TOLERANCE_IDR = Decimal("1000000")  # Rp 1.000.000

DIMENSIONAL_LOCAL_NAMES = {
    "segment",
    "scenario",
    "explicitmember",
    "typedmember",
}

# Tag candidate sets for the 8 key financial items (case-insensitive localname matching)
KEY_TAG_CANDIDATES: dict[str, list[str]] = {
    "cash_and_equivalents": [
        "cashandcashequivalents",
        "cashandcashequivalentsatendofperiod",
        "cashandcashequivalentscashflowstatement",
        "cashandcashequivalentscashflows",
    ],
    "trade_receivables_third_parties": [
        "tradereceivablesthirdparties",
        "tradereceivablesthirdparty",
        "tradereceivablesfromthirdparties",
    ],
    "trade_receivables_related_parties": [
        "tradereceivablesrelatedparties",
        "tradereceivablesrelatedparty",
        "tradereceivablesfromrelatedparties",
    ],
    "contract_assets_current": [
        "contractassetscurrent",
        "currentcontractassets",
        "contractassets",
        "unbilledreceivablesthirdparties",
        "unbilledreceivablesrelatedparties",
        "unbilledreceivables",
        "retentionreceivablesthirdparties",
        "retentionreceivablesrelatedparties",
        "grossamountduefromcustomerscurrent",
        "grossamountduefromcustomers",
    ],
    "contract_assets_non_current": [
        "contractassetsnoncurrent",
        "noncurrentcontractassets",
        "grossamountduefromcustomersnoncurrent",
    ],
    "contract_liabilities_current": [
        "currentcontractliabilities",
        "contractliabilitiescurrent",
        "contractliabilities",
        "currentadvancesfromcustomersthirdparties",
        "currentadvancesfromcustomersrelatedparties",
        "advancesfromcustomersthirdparties",
        "advancesfromcustomersrelatedparties",
        "advancesfromcustomerscurrent",
        "advancesfromcustomers",
        "currentunearnedrevenue",
        "grossamountduetocustomerscurrent",
        "grossamountduetocustomers",
    ],
    "contract_liabilities_non_current": [
        "non-currentcontractliabilities",
        "noncurrentcontractliabilities",
        "contractliabilitiesnoncurrent",
        "noncurrentadvancesfromcustomersthirdparties",
        "noncurrentadvancesfromcustomersrelatedparties",
        "advancesfromcustomersnoncurrent",
        "grossamountduetocustomersnoncurrent",
    ],
    "st_debt_bank_loans": [
        "shorttermbankloans",
        "shorttermloans",
        "shorttermborrowings",
        "shorttermnonbankloans",
    ],
    "st_debt_current_maturities_bank_loans": [
        "currentmaturitiesofbankloans",
        "currentmaturitiesoflongtermbankloans",
        "currentmaturitiesoflongtermloans",
        "currentportionoflongtermbankloans",
        "currentportionoflongtermloans",
    ],
    "st_debt_current_maturities_bonds_sukuk_mtn": [
        "currentmaturitiesofbondspayable",
        "currentmaturitiesofsukukpayable",
        "currentmaturitiesofsukuk",
        "currentmaturitiesofmediumtermnotes",
        "currentmaturitiesofbonds",
        "currentportionofbondspayable",
    ],
    "st_debt_current_portion_lease_liabilities": [
        "currentmaturitiesoffinanceleaseliabilities",
        "currentportionofleaseliabilities",
        "currentmaturitiesofleaseliabilities",
        "currentportionoffinanceleaseliabilities",
    ],
    "revenue": [
        "salesandrevenue",
        "salesandrevenues",
        "revenues",
        "revenuefromcontractswithcustomers",
    ],
    "net_income": [
        "profitloss",
        "netincome",
        "profitlossforperiod",
        "profitlossattributabletoownersofparent",
    ],
    "cfo": [
        "netcashflowsreceivedfromusedinoperatingactivities",
        "netcashflowsfromusedinoperatingactivities",
        "netcashflowsfromoperatingactivities",
        "cashflowsfromusedinoperatingactivities",
    ],
}

# Sanity check reconciliation tag candidates
SANITY_TAG_CANDIDATES: dict[str, list[str]] = {
    "assets": ["assets", "totalassets"],
    "liabilities": ["liabilities", "totalliabilities"],
    "equity": ["equity", "totalequity"],
    "equity_parent": [
        "equityattributabletoownersofparent",
        "equityattributabletoequityownersofparententity",
    ],
    "non_controlling_interests": ["noncontrollinginterests"],
    "current_assets": ["currentassets", "totalcurrentassets"],
    "non_current_assets": ["noncurrentassets", "totalnoncurrentassets"],
    "current_liabilities": ["currentliabilities", "totalcurrentliabilities"],
    "non_current_liabilities": ["noncurrentliabilities", "totalnoncurrentliabilities"],
    "cash_cf_ending": [
        "cashandcashequivalentscashflows",
        "cashandcashequivalentscashflowstatement",
        "cashandcashequivalentsatendofyear",
        "cashandcashequivalentsatendofperiod",
    ],
}


def get_elem_localname(elem: Any) -> str:
    """Safely extracts the localname string from an XML element, ignoring comments."""
    if not isinstance(elem.tag, str):
        return ""
    return etree.QName(elem).localname


class ContextMetadata(BaseModel):
    context_id: str
    period_type: str  # "instant" | "duration" | "unknown"
    instant_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    entity_identifier: str | None = None
    is_zero_dimension: bool = True
    dimension_tags_found: list[str] = Field(default_factory=list)


class FactItem(BaseModel):
    tag: str
    local_name: str
    prefix: str | None = None
    context_ref: str
    unit_ref: str | None = None
    decimals: str | None = None
    raw_lexical_value: str
    numeric_value: str | None = None  # Exact Decimal representation as string


class SanityCheckDetail(BaseModel):
    name: str
    formula: str
    left_hand_side: str
    right_hand_side: str
    difference: str
    passed: bool
    notes: str = ""


class SanityReport(BaseModel):
    all_passed: bool
    checks: list[SanityCheckDetail] = Field(default_factory=list)


class FileSpikeResult(BaseModel):
    file_name: str
    file_path: str
    ticker: str | None = None
    primary_instant_date: str | None = None
    primary_duration_period: str | None = None
    total_contexts_count: int = 0
    zero_dim_contexts_count: int = 0
    dimensional_contexts_count: int = 0
    detected_currencies: list[str] = Field(default_factory=list)
    detected_key_tags: dict[str, list[str]] = Field(default_factory=dict)
    sanity_check: SanityReport
    parsing_errors: list[str] = Field(default_factory=list)


def parse_context(context_elem: etree._Element) -> ContextMetadata:
    """Parses an XBRL context element and strictly checks for dimensional elements."""
    context_id = context_elem.get("id", "")
    dims_found: list[str] = []

    for child in context_elem.iter():
        local_name = get_elem_localname(child).lower()
        if not local_name:
            continue
        if local_name in DIMENSIONAL_LOCAL_NAMES:
            dims_found.append(get_elem_localname(child))

    is_zero_dim = len(dims_found) == 0

    # Extract entity identifier
    entity_id: str | None = None
    for elem in context_elem.iter():
        if get_elem_localname(elem).lower() == "identifier":
            if elem.text:
                entity_id = elem.text.strip()
            break

    # Extract period
    period_type = "unknown"
    instant_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    for elem in context_elem.iter():
        loc = get_elem_localname(elem).lower()
        if loc == "instant" and elem.text:
            period_type = "instant"
            instant_date = elem.text.strip()
        elif loc == "startdate" and elem.text:
            period_type = "duration"
            start_date = elem.text.strip()
        elif loc == "enddate" and elem.text:
            end_date = elem.text.strip()

    return ContextMetadata(
        context_id=context_id,
        period_type=period_type,
        instant_date=instant_date,
        start_date=start_date,
        end_date=end_date,
        entity_identifier=entity_id,
        is_zero_dimension=is_zero_dim,
        dimension_tags_found=sorted(list(set(dims_found))),
    )


def parse_decimal_value(raw_val: str | None) -> Decimal | None:
    """Deterministic conversion of raw string to Decimal."""
    if raw_val is None:
        return None
    val = raw_val.strip()
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def extract_xbrl_facts(
    tree: etree._ElementTree,
) -> tuple[dict[str, ContextMetadata], list[FactItem], list[str]]:
    """Extract zero-dimension contexts and facts from an XBRL XML document."""
    root = tree.getroot()
    contexts: dict[str, ContextMetadata] = {}
    currencies: set[str] = set()
    facts: list[FactItem] = []

    # 1. Parse contexts
    for elem in root.iter():
        if get_elem_localname(elem).lower() == "context":
            ctx = parse_context(elem)
            if ctx.context_id:
                contexts[ctx.context_id] = ctx

    # 2. Parse units
    for elem in root.iter():
        if get_elem_localname(elem).lower() == "unit":
            unit_id = elem.get("id")
            for sub in elem.iter():
                if get_elem_localname(sub).lower() == "measure" and sub.text:
                    currencies.add(sub.text.strip())
            if unit_id:
                currencies.add(unit_id)

    # 3. Parse facts (only keep facts referencing zero-dimension contexts)
    for elem in root.iter():
        local_name = get_elem_localname(elem)
        if not local_name:
            continue
        tag_str = elem.tag

        context_ref = elem.get("contextRef")
        if not context_ref or context_ref not in contexts:
            continue

        ctx = contexts[context_ref]
        if not ctx.is_zero_dimension:
            # Strictly ignore dimensional facts
            continue

        unit_ref = elem.get("unitRef")
        decimals = elem.get("decimals")
        raw_val = elem.text if elem.text else ""
        dec_val = parse_decimal_value(raw_val)

        facts.append(
            FactItem(
                tag=tag_str,
                local_name=local_name,
                prefix=elem.prefix,
                context_ref=context_ref,
                unit_ref=unit_ref,
                decimals=decimals,
                raw_lexical_value=raw_val,
                numeric_value=str(dec_val) if dec_val is not None else None,
            )
        )

    return contexts, facts, sorted(list(currencies))


def detect_key_items(
    facts: list[FactItem],
) -> dict[str, list[str]]:
    """Detect which concrete XBRL tags appear for the 8 key items."""
    found_tags: dict[str, set[str]] = {cat: set() for cat in KEY_TAG_CANDIDATES}

    for fact in facts:
        loc_lower = fact.local_name.lower()
        for cat, candidate_list in KEY_TAG_CANDIDATES.items():
            if loc_lower in candidate_list:
                found_tags[cat].add(fact.tag)

    return {cat: sorted(list(tags)) for cat, tags in found_tags.items()}


def get_latest_periods(
    contexts: dict[str, ContextMetadata],
) -> tuple[str | None, str | None]:
    """Identify the primary latest instant date and duration context for current reporting."""
    instant_dates = [
        ctx.instant_date
        for ctx in contexts.values()
        if ctx.is_zero_dimension and ctx.period_type == "instant" and ctx.instant_date
    ]
    primary_instant = max(instant_dates) if instant_dates else None

    # For duration, find zero-dim duration that ends on primary_instant
    durations = [
        ctx
        for ctx in contexts.values()
        if ctx.is_zero_dimension
        and ctx.period_type == "duration"
        and ctx.end_date == primary_instant
    ]
    # Pick the one with the earliest start_date (YTD)
    primary_duration = None
    if durations:
        longest = min(durations, key=lambda d: d.start_date or "9999-12-31")
        primary_duration = longest.context_id
    elif primary_instant:
        # Fallback to any latest duration
        all_durations = [
            ctx
            for ctx in contexts.values()
            if ctx.is_zero_dimension and ctx.period_type == "duration" and ctx.end_date
        ]
        if all_durations:
            latest_dur = max(all_durations, key=lambda d: d.end_date or "")
            primary_duration = latest_dur.context_id

    return primary_instant, primary_duration


def find_fact_value(
    facts: list[FactItem],
    contexts: dict[str, ContextMetadata],
    candidates: list[str],
    period_type: str,
    target_date: str | None = None,
    context_id: str | None = None,
) -> tuple[Decimal | None, str | None]:
    """Find a fact's Decimal value matching candidates and period constraints."""
    cand_lower = {c.lower() for c in candidates}
    for fact in facts:
        if fact.local_name.lower() not in cand_lower:
            continue
        ctx = contexts.get(fact.context_ref)
        if not ctx or not ctx.is_zero_dimension:
            continue

        if context_id and ctx.context_id != context_id:
            continue
        if period_type == "instant":
            if ctx.period_type != "instant":
                continue
            if target_date and ctx.instant_date != target_date:
                continue
        elif period_type == "duration":
            if ctx.period_type != "duration":
                continue
            if target_date and ctx.end_date != target_date:
                continue

        dec = parse_decimal_value(fact.raw_lexical_value)
        if dec is not None:
            return dec, fact.tag
    return None, None


def evaluate_4way_sanity_check(
    facts: list[FactItem],
    contexts: dict[str, ContextMetadata],
    primary_instant: str | None,
    primary_duration_id: str | None,
) -> SanityReport:
    """
    Executes the 4-Way Accounting Sanity Check:
    1. Total Assets == Total Liabilities + Total Equity
    2. Total Assets == Current Assets + Non-Current Assets
    3. Total Liabilities == Current Liabilities + Non-Current Liabilities
    4. Ending Cash (Cash Flow) == Cash and Cash Equivalents (Balance Sheet)
    Tolerance: <= Rp 1.000.000 (SANITY_TOLERANCE_IDR)
    """
    checks: list[SanityCheckDetail] = []
    all_passed = True

    if not primary_instant:
        return SanityReport(
            all_passed=False,
            checks=[
                SanityCheckDetail(
                    name="Missing Instant Context",
                    formula="N/A",
                    left_hand_side="0",
                    right_hand_side="0",
                    difference="0",
                    passed=False,
                    notes="No zero-dimension instant context found in file.",
                )
            ],
        )

    # 1. Total Assets == Total Liabilities + Total Equity
    assets, tag_assets = find_fact_value(
        facts, contexts, SANITY_TAG_CANDIDATES["assets"], "instant", primary_instant
    )
    liab, tag_liab = find_fact_value(
        facts, contexts, SANITY_TAG_CANDIDATES["liabilities"], "instant", primary_instant
    )
    equity, tag_equity = find_fact_value(
        facts, contexts, SANITY_TAG_CANDIDATES["equity"], "instant", primary_instant
    )
    if equity is None:
        eq_parent, _ = find_fact_value(
            facts,
            contexts,
            SANITY_TAG_CANDIDATES["equity_parent"],
            "instant",
            primary_instant,
        )
        nci, _ = find_fact_value(
            facts,
            contexts,
            SANITY_TAG_CANDIDATES["non_controlling_interests"],
            "instant",
            primary_instant,
        )
        if eq_parent is not None:
            equity = eq_parent + (nci or Decimal(0))
            tag_equity = "EquityParent+NCI"

    if assets is not None and liab is not None and equity is not None:
        expected_assets = liab + equity
        diff1 = abs(assets - expected_assets)
        passed1 = diff1 <= SANITY_TOLERANCE_IDR
        if not passed1:
            all_passed = False
        checks.append(
            SanityCheckDetail(
                name="1. Assets == Liabilities + Equity",
                formula="Total Assets == Total Liabilities + Total Equity",
                left_hand_side=str(assets),
                right_hand_side=str(expected_assets),
                difference=str(diff1),
                passed=passed1,
                notes=f"Tags: [{tag_assets}] vs [{tag_liab}] + [{tag_equity}]",
            )
        )
    else:
        all_passed = False
        checks.append(
            SanityCheckDetail(
                name="1. Assets == Liabilities + Equity",
                formula="Total Assets == Total Liabilities + Total Equity",
                left_hand_side=str(assets) if assets is not None else "MISSING",
                right_hand_side=f"Liab={liab}, Equity={equity}",
                difference="N/A",
                passed=False,
                notes="One or more balance sheet elements could not be resolved.",
            )
        )

    # 2. Total Assets == Current Assets + Non-Current Assets
    curr_assets, tag_ca = find_fact_value(
        facts, contexts, SANITY_TAG_CANDIDATES["current_assets"], "instant", primary_instant
    )
    non_curr_assets, tag_nca = find_fact_value(
        facts, contexts, SANITY_TAG_CANDIDATES["non_current_assets"], "instant", primary_instant
    )
    if assets is not None and curr_assets is not None and non_curr_assets is not None:
        sum_assets = curr_assets + non_curr_assets
        diff2 = abs(assets - sum_assets)
        passed2 = diff2 <= SANITY_TOLERANCE_IDR
        if not passed2:
            all_passed = False
        checks.append(
            SanityCheckDetail(
                name="2. Assets == Current + Non-Current Assets",
                formula="Total Assets == Current Assets + Non-Current Assets",
                left_hand_side=str(assets),
                right_hand_side=str(sum_assets),
                difference=str(diff2),
                passed=passed2,
                notes=f"Tags: [{tag_assets}] vs [{tag_ca}] + [{tag_nca}]",
            )
        )
    else:
        all_passed = False
        checks.append(
            SanityCheckDetail(
                name="2. Assets == Current + Non-Current Assets",
                formula="Total Assets == Current Assets + Non-Current Assets",
                left_hand_side=str(assets) if assets is not None else "MISSING",
                right_hand_side=f"CA={curr_assets}, NCA={non_curr_assets}",
                difference="N/A",
                passed=False,
                notes="Current or Non-Current Assets tag missing.",
            )
        )

    # 3. Total Liabilities == Current Liabilities + Non-Current Liabilities
    curr_liab, tag_cl = find_fact_value(
        facts, contexts, SANITY_TAG_CANDIDATES["current_liabilities"], "instant", primary_instant
    )
    non_curr_liab, tag_ncl = find_fact_value(
        facts,
        contexts,
        SANITY_TAG_CANDIDATES["non_current_liabilities"],
        "instant",
        primary_instant,
    )
    if liab is not None and curr_liab is not None and non_curr_liab is not None:
        sum_liab = curr_liab + non_curr_liab
        diff3 = abs(liab - sum_liab)
        passed3 = diff3 <= SANITY_TOLERANCE_IDR
        if not passed3:
            all_passed = False
        checks.append(
            SanityCheckDetail(
                name="3. Liabilities == Current + Non-Current Liabilities",
                formula="Total Liabilities == Current Liabilities + Non-Current Liabilities",
                left_hand_side=str(liab),
                right_hand_side=str(sum_liab),
                difference=str(diff3),
                passed=passed3,
                notes=f"Tags: [{tag_liab}] vs [{tag_cl}] + [{tag_ncl}]",
            )
        )
    else:
        all_passed = False
        checks.append(
            SanityCheckDetail(
                name="3. Liabilities == Current + Non-Current Liabilities",
                formula="Total Liabilities == Current Liabilities + Non-Current Liabilities",
                left_hand_side=str(liab) if liab is not None else "MISSING",
                right_hand_side=f"CL={curr_liab}, NCL={non_curr_liab}",
                difference="N/A",
                passed=False,
                notes="Current or Non-Current Liabilities tag missing.",
            )
        )

    # 4. Cash Flow Ending Cash == Balance Sheet Cash
    cash_bs, tag_cash_bs = find_fact_value(
        facts,
        contexts,
        ["cashandcashequivalents", "cashandcashequivalentsatendofperiod"],
        "instant",
        primary_instant,
    )
    cash_cf, tag_cash_cf = find_fact_value(
        facts,
        contexts,
        SANITY_TAG_CANDIDATES["cash_cf_ending"],
        "instant",
        primary_instant,
    )
    if cash_cf is None:
        cash_cf, tag_cash_cf = find_fact_value(
            facts,
            contexts,
            SANITY_TAG_CANDIDATES["cash_cf_ending"],
            "duration",
            primary_instant,
            context_id=primary_duration_id,
        )

    if cash_bs is not None and cash_cf is not None:
        diff4 = abs(cash_bs - cash_cf)
        passed4 = diff4 <= SANITY_TOLERANCE_IDR
        if not passed4:
            all_passed = False
        checks.append(
            SanityCheckDetail(
                name="4. Cash CF Ending == Balance Sheet Cash",
                formula="Ending Cash (CF) == Cash and Equivalents (Balance Sheet)",
                left_hand_side=str(cash_cf),
                right_hand_side=str(cash_bs),
                difference=str(diff4),
                passed=passed4,
                notes=f"Tags: CF [{tag_cash_cf}] vs BS [{tag_cash_bs}]",
            )
        )
    else:
        checks.append(
            SanityCheckDetail(
                name="4. Cash CF Ending == Balance Sheet Cash",
                formula="Ending Cash (CF) == Cash and Equivalents (Balance Sheet)",
                left_hand_side=str(cash_cf) if cash_cf is not None else "MISSING_CF_CASH",
                right_hand_side=str(cash_bs) if cash_bs is not None else "MISSING_BS_CASH",
                difference="N/A",
                passed=False,
                notes="Ending Cash from Cash Flow Statement tag not found or BS cash missing.",
            )
        )
        all_passed = False

    return SanityReport(all_passed=all_passed, checks=checks)


def audit_xbrl_file(file_path: Path | str) -> FileSpikeResult:
    """Complete audit of a single XBRL instance document."""
    path = Path(file_path)
    errors: list[str] = []

    try:
        parser = etree.XMLParser(recover=True, remove_comments=True)
        tree = etree.parse(str(path), parser)
    except Exception as e:
        return FileSpikeResult(
            file_name=path.name,
            file_path=str(path),
            sanity_check=SanityReport(
                all_passed=False,
                checks=[
                    SanityCheckDetail(
                        name="XML Parsing",
                        formula="N/A",
                        left_hand_side="N/A",
                        right_hand_side="N/A",
                        difference="0",
                        passed=False,
                        notes=f"Failed to parse XML: {e}",
                    )
                ],
            ),
            parsing_errors=[f"XML Parsing Exception: {e}"],
        )

    contexts, facts, currencies = extract_xbrl_facts(tree)

    total_ctx = len(contexts)
    zero_dim_ctx = sum(1 for c in contexts.values() if c.is_zero_dimension)
    dim_ctx = total_ctx - zero_dim_ctx

    primary_instant, primary_duration = get_latest_periods(contexts)

    # Determine ticker
    ticker = None
    for ctx in contexts.values():
        if ctx.entity_identifier:
            ticker = ctx.entity_identifier
            break
    if not ticker:
        ticker = path.stem.split("_")[0] if "_" in path.stem else path.stem

    detected_tags = detect_key_items(facts)
    sanity_report = evaluate_4way_sanity_check(
        facts, contexts, primary_instant, primary_duration
    )

    return FileSpikeResult(
        file_name=path.name,
        file_path=str(path.resolve()),
        ticker=ticker,
        primary_instant_date=primary_instant,
        primary_duration_period=primary_duration,
        total_contexts_count=total_ctx,
        zero_dim_contexts_count=zero_dim_ctx,
        dimensional_contexts_count=dim_ctx,
        detected_currencies=currencies,
        detected_key_tags=detected_tags,
        sanity_check=sanity_report,
        parsing_errors=errors,
    )


def run_spike_audit(
    samples_dir: Path | str = "./spike_samples",
    output_json: Path | str = "./spike_results.json",
) -> dict[str, Any]:
    """Scans all .xbrl files in samples_dir, runs audit, writes JSON, and prints summary table."""
    samples_path = Path(samples_dir)
    results: list[FileSpikeResult] = []

    if not samples_path.exists():
        samples_path.mkdir(parents=True, exist_ok=True)

    xbrl_files = sorted(list(samples_path.glob("*.xbrl")) + list(samples_path.glob("*.xml")))

    print("=" * 80)
    print("🔍 IDX CASH & ACCRUAL RADAR — GATE 0: XBRL TAXONOMY SPIKE")
    print(f"📁 Samples Directory: {samples_path.resolve()}")
    print(f"📊 Files Found: {len(xbrl_files)}")
    print("=" * 80)

    for f in xbrl_files:
        print(f"-> Auditing: {f.name} ...")
        res = audit_xbrl_file(f)
        results.append(res)

    # Collect cross-file taxonomy mapping
    aggregated_tags: dict[str, set[str]] = {cat: set() for cat in KEY_TAG_CANDIDATES}
    for res in results:
        for cat, tags in res.detected_key_tags.items():
            aggregated_tags[cat].update(tags)

    out_data = {
        "summary": {
            "total_files_audited": len(results),
            "files_passed_sanity": sum(1 for r in results if r.sanity_check.all_passed),
            "files_failed_sanity": sum(1 for r in results if not r.sanity_check.all_passed),
        },
        "taxonomy_variations_detected": {
            cat: sorted(list(tags)) for cat, tags in aggregated_tags.items()
        },
        "files": [r.model_dump() for r in results],
    }

    out_path = Path(output_json)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(out_data, fp, indent=2, ensure_ascii=False)

    print(f"\n✅ Audit complete. Saved structured results to: {out_path.resolve()}\n")
    print_console_summary(results, aggregated_tags)

    return out_data


def print_console_summary(
    results: list[FileSpikeResult], aggregated_tags: dict[str, set[str]]
) -> None:
    """Print clean comparison and sanity table to console."""
    if not results:
        print("ℹ️ No .xbrl sample files found in folder. Ready for sample ingestion.")
        return

    print("📋 SANITY CHECK & CONTEXT SUMMARY PER ISSUER:")
    col_hdr = (
        f"{'Ticker':<10} | {'Period':<12} | {'Total Ctx':<9} | "
        f"{'0-Dim Ctx':<9} | {'Currencies':<12} | {'Sanity Check':<15}"
    )
    print(col_hdr)
    print("-" * 80)
    for r in results:
        status = "PASSED" if r.sanity_check.all_passed else "FAILED / PARTIAL"
        curr_str = ",".join(r.detected_currencies) if r.detected_currencies else "None"
        period = r.primary_instant_date or "N/A"
        ticker = r.ticker or r.file_name[:8]
        row_str = (
            f"{ticker:<10} | {period:<12} | {r.total_contexts_count:<9} | "
            f"{r.zero_dim_contexts_count:<9} | {curr_str:<12} | {status:<15}"
        )
        print(row_str)

    print("\n🏷️ DETECTED XBRL TAXONOMY TAG VARIATIONS (8 KEY ITEMS):")
    print("-" * 80)
    for cat, tags in aggregated_tags.items():
        tag_list_str = ", ".join(tags) if tags else "(None detected)"
        print(f"• {cat:<42}: {tag_list_str}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="IDX XBRL Taxonomy Spike Audit Tool")
    parser.add_argument(
        "--dir",
        default="./spike_samples",
        help="Directory containing .xbrl sample files (default: ./spike_samples)",
    )
    parser.add_argument(
        "--out",
        default="./spike_results.json",
        help="Path to output JSON summary (default: ./spike_results.json)",
    )
    args = parser.parse_args()
    run_spike_audit(args.dir, args.out)


if __name__ == "__main__":
    main()
