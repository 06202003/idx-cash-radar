"""
Pure lxml XBRL Reader for IDX instance documents.
Zero external dependencies on Arelle as strictly mandated in AGENTS.md Section 3.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from lxml import etree

DIMENSIONAL_TAGS = {"segment", "scenario", "explicitmember", "typedmember"}


@dataclass
class ParsedContext:
    context_id: str
    period_type: str  # "instant" | "duration" | "unknown"
    instant_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    entity_identifier: str | None = None
    is_zero_dimension: bool = True
    dimension_tags: list[str] = field(default_factory=list)


@dataclass
class RawFact:
    tag: str
    local_name: str
    context_ref: str
    unit_ref: str | None
    decimals: str | None
    raw_lexical_value: str
    numeric_value: Decimal | None


@dataclass
class RawXBRLDocument:
    file_path: Path
    source_hash: str
    ticker: str
    fiscal_year: int
    period_code: str  # "Q1" | "Q2" | "Q3" | "FY"
    primary_instant_date: str
    primary_duration_context_id: str | None
    contexts: dict[str, ParsedContext]
    facts: list[RawFact]
    currencies: list[str]


def compute_file_sha256(file_path: Path) -> str:
    """Compute exact SHA-256 hash of the input XBRL file for audit trail."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_elem_localname(elem: Any) -> str:
    """Safely return element localname, ignoring comments and processing instructions."""
    if not isinstance(elem.tag, str):
        return ""
    return etree.QName(elem).localname


def parse_context_element(context_elem: etree._Element) -> ParsedContext:
    """Extract context metadata and check for multidimensional structures."""
    ctx_id = context_elem.get("id", "")
    dims: list[str] = []

    for child in context_elem.iter():
        loc = get_elem_localname(child).lower()
        if loc in DIMENSIONAL_TAGS:
            dims.append(get_elem_localname(child))

    is_zero_dim = len(dims) == 0

    entity_id = None
    for child in context_elem.iter():
        if get_elem_localname(child).lower() == "identifier":
            if child.text:
                entity_id = child.text.strip()
            break

    period_type = "unknown"
    instant_date = None
    start_date = None
    end_date = None

    for child in context_elem.iter():
        loc = get_elem_localname(child).lower()
        if loc == "instant" and child.text:
            period_type = "instant"
            instant_date = child.text.strip()
        elif loc == "startdate" and child.text:
            period_type = "duration"
            start_date = child.text.strip()
        elif loc == "enddate" and child.text:
            end_date = child.text.strip()

    return ParsedContext(
        context_id=ctx_id,
        period_type=period_type,
        instant_date=instant_date,
        start_date=start_date,
        end_date=end_date,
        entity_identifier=entity_id,
        is_zero_dimension=is_zero_dim,
        dimension_tags=dims,
    )


def parse_decimal(raw_val: str | None) -> Decimal | None:
    if raw_val is None:
        return None
    val = raw_val.strip()
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def read_xbrl_document(file_path: Path | str) -> RawXBRLDocument:
    """Read and parse an XBRL file into a structured RawXBRLDocument."""
    path = Path(file_path)
    file_hash = compute_file_sha256(path)

    parser = etree.XMLParser(recover=True, remove_comments=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()

    contexts: dict[str, ParsedContext] = {}
    currencies: set[str] = set()
    facts: list[RawFact] = []

    # 1. Parse contexts
    for elem in root.iter():
        if get_elem_localname(elem).lower() == "context":
            ctx = parse_context_element(elem)
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

    # 3. Parse facts belonging ONLY to zero-dimension contexts
    for elem in root.iter():
        local_name = get_elem_localname(elem)
        if not local_name:
            continue
        context_ref = elem.get("contextRef")
        if not context_ref or context_ref not in contexts:
            continue
        ctx = contexts[context_ref]
        if not ctx.is_zero_dimension:
            continue

        raw_val = elem.text.strip() if elem.text else ""
        dec_val = parse_decimal(raw_val)

        facts.append(
            RawFact(
                tag=elem.tag,
                local_name=local_name,
                context_ref=context_ref,
                unit_ref=elem.get("unitRef"),
                decimals=elem.get("decimals"),
                raw_lexical_value=raw_val,
                numeric_value=dec_val,
            )
        )

    # Identify primary periods
    instants = [
        ctx.instant_date
        for ctx in contexts.values()
        if ctx.is_zero_dimension and ctx.period_type == "instant" and ctx.instant_date
    ]
    primary_instant = max(instants) if instants else "1970-01-01"

    # Identify primary duration (longest ending on primary_instant)
    durations = [
        ctx
        for ctx in contexts.values()
        if (
            ctx.is_zero_dimension
            and ctx.period_type == "duration"
            and ctx.end_date == primary_instant
        )
    ]
    primary_duration_id = None
    if durations:
        primary_duration = min(durations, key=lambda d: d.start_date or "9999-12-31")
        primary_duration_id = primary_duration.context_id

    # Determine ticker
    ticker = ""
    known_tickers = {
        "ADHI", "PTPP", "WIKA", "WSKT", "TOTL", "NRCA", "JKON", "ACST",
        "WEGE", "PPRE", "DGIK", "PBSA"
    }
    # 1. If path is inside standard folder data/raw_xbrl/{TICKER}/{YEAR}/, use that verified ticker
    parent_ticker = path.parent.parent.name.upper()
    if parent_ticker in known_tickers:
        ticker = parent_ticker
    else:
        for ctx in contexts.values():
            if ctx.entity_identifier:
                cand = ctx.entity_identifier.upper()
                if "_" in cand:
                    cand = cand.split("_")[0]
                ticker = cand
                break
        if not ticker:
            parts = path.stem.split("_")
            ticker = parts[1] if len(parts) > 1 and parts[0].lower() == "instance" else parts[0]
            ticker = ticker.upper()

    # Determine fiscal year and period code (e.g. 12 -> FY, 09 -> Q3, 06 -> Q2, 03 -> Q1)
    year_str, month_str, _ = primary_instant.split("-")
    fiscal_year = int(year_str)
    if month_str in ("12", "01"):
        period_code = "FY"
    elif month_str in ("09", "10"):
        period_code = "Q3"
    elif month_str in ("06", "07"):
        period_code = "Q2"
    elif month_str in ("03", "04"):
        period_code = "Q1"
    else:
        period_code = "FY"

    return RawXBRLDocument(
        file_path=path,
        source_hash=file_hash,
        ticker=ticker,
        fiscal_year=fiscal_year,
        period_code=period_code,
        primary_instant_date=primary_instant,
        primary_duration_context_id=primary_duration_id,
        contexts=contexts,
        facts=facts,
        currencies=sorted(list(currencies)),
    )
