"""
Taxonomy Normalizer for IDX XBRL filings.
Maps raw taxonomy elements into CanonicalFactModel based on config/taxonomy_mapping.yaml.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.models.canonical import CanonicalFactModel, FilingExtractionResult, FilingModel
from src.parser.sanity_check import run_4way_accounting_check
from src.parser.xbrl_reader import RawFact, RawXBRLDocument

DEFAULT_MAPPING_PATH = Path(__file__).parents[2] / "config" / "taxonomy_mapping.yaml"


class TaxonomyNormalizer:
    def __init__(self, mapping_path: Path | str = DEFAULT_MAPPING_PATH) -> None:
        self.mapping_path = Path(mapping_path)
        with open(self.mapping_path, encoding="utf-8") as f:
            self.mapping_data: dict[str, Any] = yaml.safe_load(f)

    def _find_fact(
        self,
        doc: RawXBRLDocument,
        candidate_tags: list[str],
        period_type: str,
        target_instant: str | None = None,
        duration_context_id: str | None = None,
    ) -> RawFact | None:
        """Find single fact matching candidates and period constraints."""
        cand_lower = {t.lower() for t in candidate_tags}
        for f in doc.facts:
            if f.local_name.lower() not in cand_lower:
                continue
            ctx = doc.contexts.get(f.context_ref)
            if not ctx or not ctx.is_zero_dimension:
                continue

            if period_type == "instant":
                if ctx.period_type != "instant":
                    continue
                if target_instant and ctx.instant_date != target_instant:
                    continue
            elif period_type == "duration":
                if ctx.period_type != "duration":
                    continue
                if duration_context_id and ctx.context_id != duration_context_id:
                    continue
                elif target_instant and ctx.end_date != target_instant:
                    continue

            if f.numeric_value is not None:
                return f
        return None

    def _sum_facts(
        self,
        doc: RawXBRLDocument,
        candidate_tags: list[str],
        period_type: str,
        target_instant: str | None = None,
        duration_context_id: str | None = None,
    ) -> tuple[Decimal, list[RawFact]]:
        """Sum multiple non-overlapping facts matching candidate tags."""
        cand_lower = {t.lower() for t in candidate_tags}
        total = Decimal("0")
        matched_facts = []
        seen_tags = set()

        for f in doc.facts:
            loc = f.local_name.lower()
            if loc not in cand_lower or loc in seen_tags:
                continue
            ctx = doc.contexts.get(f.context_ref)
            if not ctx or not ctx.is_zero_dimension:
                continue

            if period_type == "instant":
                if ctx.period_type != "instant":
                    continue
                if target_instant and ctx.instant_date != target_instant:
                    continue
            elif period_type == "duration":
                if ctx.period_type != "duration":
                    continue
                if duration_context_id and ctx.context_id != duration_context_id:
                    continue

            if f.numeric_value is not None:
                total += f.numeric_value
                matched_facts.append(f)
                seen_tags.add(loc)

        return total, matched_facts

    def normalize(self, doc: RawXBRLDocument) -> FilingExtractionResult:
        """Extract all canonical facts and execute 4-way sanity check."""
        canonical_facts: list[CanonicalFactModel] = []

        # 1. Sanity check items
        f_assets = self._find_fact(
            doc, ["Assets", "TotalAssets"], "instant", doc.primary_instant_date
        )
        f_liab = self._find_fact(
            doc, ["Liabilities", "TotalLiabilities"], "instant", doc.primary_instant_date
        )
        f_equity = self._find_fact(
            doc, ["Equity", "TotalEquity"], "instant", doc.primary_instant_date
        )
        if not f_equity:
            # Fallback EquityParent + NCI
            f_eq_p = self._find_fact(
                doc,
                [
                    "EquityAttributableToOwnersOfParent",
                    "EquityAttributableToEquityOwnersOfParentEntity",
                ],
                "instant",
                doc.primary_instant_date,
            )
            f_nci = self._find_fact(
                doc, ["NonControllingInterests"], "instant", doc.primary_instant_date
            )
            if f_eq_p:
                combined_equity = f_eq_p.numeric_value or Decimal(0)
                if f_nci and f_nci.numeric_value:
                    combined_equity += f_nci.numeric_value
                f_equity = RawFact(
                    tag="EquityParent+NCI",
                    local_name="Equity",
                    context_ref=f_eq_p.context_ref,
                    unit_ref=f_eq_p.unit_ref,
                    decimals=f_eq_p.decimals,
                    raw_lexical_value=str(combined_equity),
                    numeric_value=combined_equity,
                )

        f_ca = self._find_fact(
            doc, ["CurrentAssets", "TotalCurrentAssets"], "instant", doc.primary_instant_date
        )
        f_nca = self._find_fact(
            doc, ["NonCurrentAssets", "TotalNonCurrentAssets"], "instant", doc.primary_instant_date
        )
        f_cl = self._find_fact(
            doc,
            ["CurrentLiabilities", "TotalCurrentLiabilities"],
            "instant",
            doc.primary_instant_date,
        )
        f_ncl = self._find_fact(
            doc,
            ["NonCurrentLiabilities", "TotalNonCurrentLiabilities"],
            "instant",
            doc.primary_instant_date,
        )

        f_cash_bs = self._find_fact(
            doc,
            ["CashAndCashEquivalents", "CashAndCashEquivalentsAtEndOfPeriod"],
            "instant",
            doc.primary_instant_date,
        )
        # CF Ending cash: check instant first (IDX style CashAndCashEquivalentsCashFlows),
        # then fallback to duration context
        f_cash_cf = self._find_fact(
            doc,
            ["CashAndCashEquivalentsCashFlows", "CashAndCashEquivalentsCashFlowStatement"],
            "instant",
            doc.primary_instant_date,
        )
        if not f_cash_cf:
            f_cash_cf = self._find_fact(
                doc,
                ["CashAndCashEquivalentsCashFlows", "CashAndCashEquivalentsCashFlowStatement"],
                "duration",
                duration_context_id=doc.primary_duration_context_id,
            )

        # Execute 4-Way Sanity Check
        sanity_res = run_4way_accounting_check(
            assets=f_assets.numeric_value if f_assets else None,
            liabilities=f_liab.numeric_value if f_liab else None,
            equity=f_equity.numeric_value if f_equity else None,
            current_assets=f_ca.numeric_value if f_ca else None,
            non_current_assets=f_nca.numeric_value if f_nca else None,
            current_liabilities=f_cl.numeric_value if f_cl else None,
            non_current_liabilities=f_ncl.numeric_value if f_ncl else None,
            cash_balance_sheet=f_cash_bs.numeric_value if f_cash_bs else None,
            cash_flow_ending=f_cash_cf.numeric_value if f_cash_cf else None,
            raise_on_error=False,
        )

        # Store Balance Sheet & Core Totals in canonical facts
        if f_assets:
            canonical_facts.append(self._fact_to_canonical("total_assets", f_assets))
        if f_liab:
            canonical_facts.append(self._fact_to_canonical("total_liabilities", f_liab))
        if f_equity:
            canonical_facts.append(self._fact_to_canonical("total_equity", f_equity))
        if f_ca:
            canonical_facts.append(self._fact_to_canonical("current_assets", f_ca))
        if f_nca:
            canonical_facts.append(self._fact_to_canonical("non_current_assets", f_nca))
        if f_cl:
            canonical_facts.append(self._fact_to_canonical("current_liabilities", f_cl))
        if f_ncl:
            canonical_facts.append(self._fact_to_canonical("non_current_liabilities", f_ncl))

        # 2. Key Item 1: Cash and Cash Equivalents
        if f_cash_bs:
            canonical_facts.append(self._fact_to_canonical("cash_and_equivalents", f_cash_bs))

        # 3. Key Item 2: Trade Receivables (Third Parties & Related Parties)
        f_tr_tp = self._find_fact(
            doc, ["TradeReceivablesThirdParties"], "instant", doc.primary_instant_date
        )
        f_tr_rp = self._find_fact(
            doc, ["TradeReceivablesRelatedParties"], "instant", doc.primary_instant_date
        )
        if f_tr_tp:
            canonical_facts.append(
                self._fact_to_canonical("trade_receivables_third_parties", f_tr_tp)
            )
        if f_tr_rp:
            canonical_facts.append(
                self._fact_to_canonical("trade_receivables_related_parties", f_tr_rp)
            )

        # 4. Key Item 3: Contract Assets (Current & Non-Current)
        # Sum unbilled receivables + retention receivables + contract assets
        contract_assets_tags = [
            "UnbilledReceivablesThirdParties",
            "UnbilledReceivablesRelatedParties",
            "RetentionReceivablesThirdParties",
            "RetentionReceivablesRelatedParties",
            "CurrentContractAssets",
            "ContractAssetsCurrent",
            "ContractAssets",
            "GrossAmountDueFromCustomersCurrent",
            "GrossAmountDueFromCustomers",
        ]
        sum_ca, matched_ca = self._sum_facts(
            doc, contract_assets_tags, "instant", doc.primary_instant_date
        )
        if matched_ca:
            canonical_facts.append(
                CanonicalFactModel(
                    canonical_key="contract_assets_current",
                    value_idr=sum_ca,
                    raw_xbrl_tag=",".join([f.local_name for f in matched_ca]),
                    raw_context_ref=matched_ca[0].context_ref,
                    raw_unit_ref=matched_ca[0].unit_ref,
                    raw_decimals=matched_ca[0].decimals,
                    raw_lexical_value=str(sum_ca),
                )
            )

        f_ca_nc = self._find_fact(
            doc,
            [
                "Non-CurrentContractAssets",
                "NonCurrentContractAssets",
                "ContractAssetsNonCurrent",
                "GrossAmountDueFromCustomersNonCurrent",
            ],
            "instant",
            doc.primary_instant_date,
        )
        if f_ca_nc:
            canonical_facts.append(
                self._fact_to_canonical("contract_assets_non_current", f_ca_nc)
            )

        # 5. Key Item 4: Contract Liabilities (Current & Non-Current)
        contract_liab_tags = [
            "CurrentAdvancesFromCustomersThirdParties",
            "CurrentAdvancesFromCustomersRelatedParties",
            "CurrentContractLiabilities",
            "CurrentUnearnedRevenue",
            "AdvancesFromCustomersThirdParties",
            "AdvancesFromCustomersRelatedParties",
            "AdvancesFromCustomersCurrent",
            "ContractLiabilitiesCurrent",
            "ContractLiabilities",
            "GrossAmountDueToCustomersCurrent",
        ]
        sum_cl, matched_cl = self._sum_facts(
            doc, contract_liab_tags, "instant", doc.primary_instant_date
        )
        if matched_cl:
            canonical_facts.append(
                CanonicalFactModel(
                    canonical_key="contract_liabilities_current",
                    value_idr=sum_cl,
                    raw_xbrl_tag=",".join([f.local_name for f in matched_cl]),
                    raw_context_ref=matched_cl[0].context_ref,
                    raw_unit_ref=matched_cl[0].unit_ref,
                    raw_decimals=matched_cl[0].decimals,
                    raw_lexical_value=str(sum_cl),
                )
            )

        f_cl_nc = self._find_fact(
            doc,
            [
                "Non-CurrentContractLiabilities",
                "NonCurrentContractLiabilities",
                "NonCurrentAdvancesFromCustomersThirdParties",
                "NonCurrentAdvancesFromCustomersRelatedParties",
                "AdvancesFromCustomersNonCurrent",
                "GrossAmountDueToCustomersNonCurrent",
            ],
            "instant",
            doc.primary_instant_date,
        )
        if f_cl_nc:
            canonical_facts.append(
                self._fact_to_canonical("contract_liabilities_non_current", f_cl_nc)
            )

        # 6. Key Item 5: Short-Term Interest-Bearing Debt (4 distinct components)
        # 6a. Bank Loans
        sum_bank, matched_bank = self._sum_facts(
            doc,
            ["ShortTermBankLoans", "ShortTermNonBankLoans", "ShortTermLoans"],
            "instant",
            doc.primary_instant_date,
        )
        if matched_bank:
            canonical_facts.append(
                CanonicalFactModel(
                    canonical_key="st_debt_bank_loans",
                    value_idr=sum_bank,
                    raw_xbrl_tag=",".join([f.local_name for f in matched_bank]),
                    raw_context_ref=matched_bank[0].context_ref,
                    raw_unit_ref=matched_bank[0].unit_ref,
                    raw_decimals=matched_bank[0].decimals,
                    raw_lexical_value=str(sum_bank),
                )
            )

        # 6b. Current Maturities of Long-Term Bank Loans
        f_cm_bank = self._find_fact(
            doc,
            [
                "CurrentMaturitiesOfBankLoans",
                "CurrentMaturitiesOfLongTermBankLoans",
                "CurrentMaturitiesOfLongTermLoans",
                "CurrentPortionOfLongTermBankLoans",
            ],
            "instant",
            doc.primary_instant_date,
        )
        if f_cm_bank:
            canonical_facts.append(
                self._fact_to_canonical("st_debt_current_maturities_bank_loans", f_cm_bank)
            )

        # 6c. Current Maturities of Bonds, Sukuk, MTN
        sum_bonds, matched_bonds = self._sum_facts(
            doc,
            [
                "CurrentMaturitiesOfBondsPayable",
                "CurrentMaturitiesOfSukuk",
                "CurrentMaturitiesOfSukukPayable",
                "CurrentMaturitiesOfMediumTermNotes",
                "CurrentMaturitiesOfBonds",
            ],
            "instant",
            doc.primary_instant_date,
        )
        if matched_bonds:
            canonical_facts.append(
                CanonicalFactModel(
                    canonical_key="st_debt_current_maturities_bonds_sukuk_mtn",
                    value_idr=sum_bonds,
                    raw_xbrl_tag=",".join([f.local_name for f in matched_bonds]),
                    raw_context_ref=matched_bonds[0].context_ref,
                    raw_unit_ref=matched_bonds[0].unit_ref,
                    raw_decimals=matched_bonds[0].decimals,
                    raw_lexical_value=str(sum_bonds),
                )
            )

        # 6d. Current Portion of Lease Liabilities
        f_cm_lease = self._find_fact(
            doc,
            [
                "CurrentMaturitiesOfFinanceLeaseLiabilities",
                "CurrentPortionOfLeaseLiabilities",
                "CurrentMaturitiesOfLeaseLiabilities",
            ],
            "instant",
            doc.primary_instant_date,
        )
        if f_cm_lease:
            canonical_facts.append(
                self._fact_to_canonical("st_debt_current_portion_lease_liabilities", f_cm_lease)
            )

        # 7. Key Item 6: Revenue
        f_rev = self._find_fact(
            doc,
            [
                "SalesAndRevenue",
                "SalesAndRevenues",
                "Revenues",
                "RevenueFromContractsWithCustomers",
            ],
            "duration",
            duration_context_id=doc.primary_duration_context_id,
        )
        if f_rev:
            canonical_facts.append(self._fact_to_canonical("revenue", f_rev))

        # 8. Key Item 7: Net Income (Profit / Loss)
        f_ni = self._find_fact(
            doc,
            ["ProfitLoss", "NetIncome", "ProfitLossAttributableToOwnersOfParent"],
            "duration",
            duration_context_id=doc.primary_duration_context_id,
        )
        if f_ni:
            canonical_facts.append(self._fact_to_canonical("net_income", f_ni))

        # 9. Key Item 8: CFO (Operating Cash Flow)
        f_cfo = self._find_fact(
            doc,
            [
                "NetCashFlowsReceivedFromUsedInOperatingActivities",
                "NetCashFlowsFromUsedInOperatingActivities",
                "NetCashFlowsFromOperatingActivities",
            ],
            "duration",
            duration_context_id=doc.primary_duration_context_id,
        )
        if f_cfo:
            canonical_facts.append(self._fact_to_canonical("cfo", f_cfo))

        # Build Filing Header
        filing_id = f"{doc.ticker}_{doc.fiscal_year}_{doc.period_code}_FIRST"
        is_audited = doc.period_code == "FY"

        filing_model = FilingModel(
            filing_id=filing_id,
            ticker=doc.ticker,
            fiscal_year=doc.fiscal_year,
            period_code=doc.period_code,
            period_end_date=doc.primary_instant_date,
            is_audited=is_audited,
            is_restatement=False,
            reporting_currency="IDR",
            fx_rate_to_idr=Decimal("1"),
            sanity_check_passed=sanity_res["all_passed"],
            source_xbrl_hash=doc.source_hash,
        )

        return FilingExtractionResult(
            filing=filing_model,
            facts=canonical_facts,
            sanity_passed=sanity_res["all_passed"],
            sanity_details=sanity_res["checks"],
        )

    def _fact_to_canonical(self, key: str, f: RawFact) -> CanonicalFactModel:
        return CanonicalFactModel(
            canonical_key=key,
            value_idr=f.numeric_value or Decimal(0),
            raw_xbrl_tag=f.local_name,
            raw_context_ref=f.context_ref,
            raw_unit_ref=f.unit_ref,
            raw_decimals=f.decimals,
            raw_lexical_value=f.raw_lexical_value,
        )
