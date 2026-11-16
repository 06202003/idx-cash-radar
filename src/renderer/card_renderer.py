"""
Deterministic Card Renderer using Jinja2 templates.
Strictly implements Section 8 of AGENTS.md.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.db.repository import FinancialRepository
from src.models.metrics import ComputedFilingMetrics
from src.renderer.formatter import (
    format_bps,
    format_decimal_id,
    format_idr_nominal,
    format_percentage_id,
    format_progress_bar,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class DiagnosticCardRenderer:
    def __init__(self, templates_dir: Path | str = TEMPLATES_DIR) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.construction_template = self.env.get_template("card_construction.j2")
        self.empty_state_template = self.env.get_template("card_empty_state.j2")
        self.leaderboard_template = self.env.get_template("card_leaderboard.j2")
        self.comparison_template = self.env.get_template("card_comparison.j2")
        self.trend_template = self.env.get_template("card_trend.j2")
        self.calk_template = self.env.get_template("card_calk.j2")
        self.fmcg_template = self.env.get_template("card_fmcg.j2")
        self.banking_template = self.env.get_template("card_banking.j2")

    def render_construction_card(
        self,
        metrics: ComputedFilingMetrics,
        company_name: str,
        repo: FinancialRepository | None = None,
        ai_narrative: str | None = None,
        news_items: list[Any] | None = None,
    ) -> str:
        """Renders diagnostic report card for a construction sector issuer."""
        # 1. Fetch raw tags for audit trail if repository provided
        tag_receivable = "TradeReceivablesThirdParties"
        tag_contract = "UnbilledReceivables / CurrentContractAssets"
        tag_cfo = "NetCashFlowsReceivedFromUsedInOperatingActivities"
        tag_debt = "ShortTermBankLoans / CurrentMaturities"

        if repo:
            facts = repo.get_canonical_facts(metrics.filing_id)
            if "trade_receivables_third_parties" in facts:
                tag_receivable = facts["trade_receivables_third_parties"].raw_xbrl_tag
            if "contract_assets_current" in facts:
                tag_contract = facts["contract_assets_current"].raw_xbrl_tag
            if "cfo" in facts:
                tag_cfo = facts["cfo"].raw_xbrl_tag
            if "st_debt_bank_loans" in facts:
                tag_debt = facts["st_debt_bank_loans"].raw_xbrl_tag

        # Helper for cohort rank display
        def rank_str(cat_key: str) -> str:
            cr = metrics.cohort_ranks.get(cat_key)
            if not cr:
                return "Peer N/A"
            if cr.small_n_guard:
                med = format_decimal_id(cr.industry_median, 2)
                return f"vs. Median: {med}"
            return f"Peringkat {cr.exact_rank} dari {cr.total_peers} ({cr.quartile})"

        peer_cnt = 3
        if "contract_exposure" in metrics.cohort_ranks:
            peer_cnt = metrics.cohort_ranks["contract_exposure"].peer_count

        context_data: dict[str, Any] = {
            "company_name": company_name,
            "ticker": metrics.ticker,
            "period_code": "FY" if metrics.is_audit_derived_q4 else "Interim",
            "fiscal_year": metrics.period_end_date[:4],
            "is_audited": metrics.is_audit_derived_q4,
            "status_safeguard": metrics.safeguards.status_summary,
            "peer_count": peer_cnt,
            # PSAK 72
            "gross_bar": format_progress_bar(
                metrics.contract_exposure.gross_contract_exposure_ratio
            ),
            "gross_ratio": format_percentage_id(
                metrics.contract_exposure.gross_contract_exposure_ratio
            ),
            "net_ratio": format_percentage_id(
                metrics.contract_exposure.net_contract_exposure_ratio
            ),
            "divergence_bps": format_bps(
                metrics.contract_exposure.gross_divergence_yoy_bps
            ),
            "cohort_rank_contract": rank_str("contract_exposure"),
            # Helpers for friendly retail interpretation
            "is_debt_free": bool(metrics.cash_coverage.debt_free_short_term),
            "is_cfo_negative": bool(
                metrics.sloan_accrual.cfo_ttm_idr is not None
                and metrics.sloan_accrual.cfo_ttm_idr < 0
            ),
            "is_coverage_low": bool(
                metrics.cash_coverage.cash_coverage_ratio is not None
                and metrics.cash_coverage.cash_coverage_ratio < 0.5
            ),
            # Sloan Accrual
            "sloan_ratio": format_decimal_id(
                metrics.sloan_accrual.sloan_ratio_ttm, 3
            ),
            "cohort_rank_sloan": rank_str("sloan_accrual"),
            "net_income": format_idr_nominal(metrics.sloan_accrual.net_income_ttm_idr),
            "cfo_ttm": format_idr_nominal(metrics.sloan_accrual.cfo_ttm_idr),
            # Cash Coverage
            "cov_bar": (
                "[████████] Bebas Utang Bank"
                if metrics.cash_coverage.debt_free_short_term
                else format_progress_bar(metrics.cash_coverage.cash_coverage_ratio)
            ),
            "cash_coverage": format_decimal_id(
                metrics.cash_coverage.cash_coverage_ratio, 2
            ),
            "cohort_rank_coverage": rank_str("cash_coverage"),
            "cash": format_idr_nominal(metrics.cash_coverage.cash_idr),
            "st_debt": format_idr_nominal(metrics.cash_coverage.st_debt_idr),
            # Audit Trail
            "tag_receivable": tag_receivable,
            "tag_contract": tag_contract,
            "tag_cfo": tag_cfo,
            "tag_debt": tag_debt,
            # AI Narrative
            "ai_narrative": ai_narrative,
            # News Sentiment Radar
            "news_items": news_items,
        }

        return self.construction_template.render(context_data)

    def render_empty_state_card(self, ticker: str) -> str:
        """Renders informative educational card for out-of-scope tickers."""
        return self.empty_state_template.render({"ticker": ticker.upper()})

    def render_leaderboard_card(
        self, items: list[dict[str, Any]], fiscal_year: int | str = 2025
    ) -> str:
        """Renders financial solvency podium leaderboard for construction issuers."""
        return self.leaderboard_template.render(
            {
                "items": items,
                "fiscal_year": fiscal_year,
                "total_emitens": len(items),
            }
        )

    def render_comparison_card(
        self,
        m1: ComputedFilingMetrics,
        name1: str,
        m2: ComputedFilingMetrics,
        name2: str,
        ai_narrative: str,
        fiscal_year: int | str = 2025,
    ) -> str:
        """Renders side-by-side comparative card for two issuers."""
        cov1_val = m1.cash_coverage.cash_coverage_ratio
        cov2_val = m2.cash_coverage.cash_coverage_ratio

        if m1.cash_coverage.debt_free_short_term:
            cov1_str = "Bebas Utang Jk. Pendek 🟢"
        elif cov1_val is not None:
            cov1_str = f"{format_decimal_id(cov1_val, 2)}x"
        else:
            cov1_str = "N/A"

        if m2.cash_coverage.debt_free_short_term:
            cov2_str = "Bebas Utang Jk. Pendek 🟢"
        elif cov2_val is not None:
            cov2_str = f"{format_decimal_id(cov2_val, 2)}x"
        else:
            cov2_str = "N/A"

        sloan1_val = m1.sloan_accrual.sloan_ratio_ttm
        sloan2_val = m2.sloan_accrual.sloan_ratio_ttm

        sloan1_str = (
            f"{format_decimal_id(sloan1_val * 100, 1)}%"
            if sloan1_val is not None
            else "N/A"
        )
        sloan2_str = (
            f"{format_decimal_id(sloan2_val * 100, 1)}%"
            if sloan2_val is not None
            else "N/A"
        )

        context_data = {
            "m1": m1,
            "name1": name1,
            "m2": m2,
            "name2": name2,
            "fiscal_year": fiscal_year,
            "cash1_str": format_idr_nominal(m1.cash_coverage.cash_idr),
            "cash2_str": format_idr_nominal(m2.cash_coverage.cash_idr),
            "debt1_str": format_idr_nominal(m1.cash_coverage.st_debt_idr),
            "debt2_str": format_idr_nominal(m2.cash_coverage.st_debt_idr),
            "cov1_str": cov1_str,
            "cov2_str": cov2_str,
            "cfo1_str": format_idr_nominal(m1.sloan_accrual.cfo_ttm_idr),
            "cfo2_str": format_idr_nominal(m2.sloan_accrual.cfo_ttm_idr),
            "sloan1_str": sloan1_str,
            "sloan2_str": sloan2_str,
            "status1_badge": m1.safeguards.status_summary,
            "status2_badge": m2.safeguards.status_summary,
            "ai_narrative": ai_narrative,
        }
        return self.comparison_template.render(context_data)

    def render_trend_card(
        self,
        ticker: str,
        company_name: str,
        history: list[dict[str, Any]],
        ai_narrative: str,
    ) -> str:
        """Renders 4-year evolution trend card for an issuer."""
        return self.trend_template.render(
            {
                "ticker": ticker.upper(),
                "company_name": company_name,
                "history": history,
                "ai_narrative": ai_narrative,
            }
        )

    def render_calk_card(self, extraction: Any) -> str:
        """Renders CALK footnote extraction card with verbatim grounding verification."""
        return self.calk_template.render(
            {
                "extraction": extraction,
                "format_idr_nominal": format_idr_nominal,
                "format_decimal_id": format_decimal_id,
            }
        )

    def render_fmcg_card(
        self,
        ticker: str,
        company_name: str,
        sub_industry: str,
        fiscal_year: int | str,
        cfo_val: Decimal,
        ni_val: Decimal,
        cash_val: Decimal,
        debt_val: Decimal,
        rec_val: Decimal,
        inv_val: Decimal,
        rev_val: Decimal,
    ) -> str:
        """Renders diagnostic report card for an FMCG / Consumer Goods issuer."""
        cfo_to_ni = round((cfo_val / ni_val * 100), 1) if ni_val > 0 else Decimal("100")
        wc_exposure = rec_val + inv_val
        wc_ratio = round((wc_exposure / rev_val * 100), 1) if rev_val > 0 else Decimal("0")
        cov_val = round((cash_val / debt_val), 2) if debt_val > 0 else Decimal("999")

        return self.fmcg_template.render(
            {
                "ticker": ticker.upper(),
                "company_name": company_name,
                "sub_industry": sub_industry,
                "fiscal_year": fiscal_year,
                "cfo_str": format_idr_nominal(cfo_val),
                "net_income_str": format_idr_nominal(ni_val),
                "cash_str": format_idr_nominal(cash_val),
                "debt_str": format_idr_nominal(debt_val),
                "wc_exposure_str": format_idr_nominal(wc_exposure),
                "cfo_to_ni_pct": format_decimal_id(cfo_to_ni, 1),
                "wc_ratio_pct": format_decimal_id(wc_ratio, 1),
                "cov_str": f"{format_decimal_id(cov_val, 2)}x",
            }
        )

    def render_banking_card(
        self,
        ticker: str,
        company_name: str,
        sub_industry: str,
        fiscal_year: int | str,
        cash_val: Decimal,
        dpk_val: Decimal,
        loans_val: Decimal,
        npl_val: Decimal,
        rev_val: Decimal,
        ni_val: Decimal,
        cfo_val: Decimal,
    ) -> str:
        """Renders diagnostic report card for a Banking & Financials issuer."""
        cov_pct = round((cash_val / dpk_val * 100), 1) if dpk_val > 0 else Decimal("15.0")
        npl_pct = round((npl_val / loans_val * 100), 2) if loans_val > 0 else Decimal("2.0")

        return self.banking_template.render(
            {
                "ticker": ticker.upper(),
                "company_name": company_name,
                "sub_industry": sub_industry,
                "fiscal_year": fiscal_year,
                "cash_str": format_idr_nominal(cash_val),
                "debt_str": format_idr_nominal(dpk_val),
                "loans_str": format_idr_nominal(loans_val),
                "rev_str": format_idr_nominal(rev_val),
                "net_income_str": format_idr_nominal(ni_val),
                "cfo_str": format_idr_nominal(cfo_val),
                "cov_pct": format_decimal_id(cov_pct, 1),
                "npl_pct": format_decimal_id(npl_pct, 2),
            }
        )

