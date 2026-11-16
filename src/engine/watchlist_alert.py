"""
Watchlist Notification Engine & Automated Filing Alert Poller.
Phase 2 Implementation according to docs/PRD.md Section 10.2.
Detects financial distress events or new filings and formats push notifications for users.
"""

from __future__ import annotations

from src.db.repository import FinancialRepository
from src.engine.llm_explainer import check_language_compliance
from src.models.metrics import ComputedFilingMetrics
from src.renderer.formatter import format_decimal_id, format_idr_nominal


class FilingAlertNotification:
    def __init__(
        self,
        ticker: str,
        fiscal_year: int,
        period_code: str,
        alert_level: str,  # "CRITICAL" | "WARNING" | "INFO"
        title: str,
        message: str,
        metrics: ComputedFilingMetrics | None = None,
    ) -> None:
        self.ticker = ticker
        self.fiscal_year = fiscal_year
        self.period_code = period_code
        self.alert_level = alert_level
        self.title = title
        self.message = message
        self.metrics = metrics

    def format_telegram_alert(self) -> str:
        """Formats clean, compliant markdown alert message for Telegram push."""
        if self.alert_level == "CRITICAL":
            icon = "🚨"
        elif self.alert_level == "WARNING":
            icon = "⚠️"
        else:
            icon = "📢"
        lines = [
            f"{icon} {self.title}",
            "━" * 40,
            f"Emiten: {self.ticker} | Periode: {self.period_code} {self.fiscal_year}",
            "",
            self.message,
            "",
            "━" * 40,
            f"💡 Ketik `/check {self.ticker}` untuk diagnostik lengkap atau `/calk {self.ticker}`.",
        ]
        return "\n".join(lines)


class WatchlistAlertEngine:
    """Evaluates filing metrics and generates automated alerts for subscribed users."""

    def __init__(self, repository: FinancialRepository | None = None) -> None:
        self.repo = repository or FinancialRepository()

    def evaluate_filing_for_alerts(
        self,
        metrics: ComputedFilingMetrics,
        company_name: str,
    ) -> list[FilingAlertNotification]:
        """
        Evaluates a filing against critical cash flow and accrual triggers.
        Returns a list of alerts to be dispatched.
        """
        alerts: list[FilingAlertNotification] = []

        ticker = metrics.ticker
        cov = metrics.cash_coverage.cash_coverage_ratio
        cfo = metrics.sloan_accrual.cfo_ttm_idr
        ni = metrics.sloan_accrual.net_income_ttm_idr
        sloan = metrics.sloan_accrual.sloan_ratio_ttm

        cfo_disp = format_idr_nominal(cfo)
        cov_disp = f"{format_decimal_id(cov, 2)}x" if cov is not None else "N/A"
        sloan_pct = f"{format_decimal_id(sloan * 100, 1)}%" if sloan is not None else "N/A"

        # 1. Critical Trigger: Acute Liquidity Pressure
        if metrics.safeguards.flag_acute_liquidity:
            title = f"PERINGATAN LIKUIDITAS: {ticker} ({company_name})"
            msg = (
                f"Kapasitas kas tertekan menjadi {cov_disp} dari utang jangka pendek berbunga, "
                f"sementara arus kas operasional (CFO TTM) mencatat defisit Rp {cfo_disp}."
            )
            if check_language_compliance(msg):
                alerts.append(
                    FilingAlertNotification(
                        ticker=ticker,
                        fiscal_year=2025,
                        period_code="FY",
                        alert_level="CRITICAL",
                        title=title,
                        message=msg,
                        metrics=metrics,
                    )
                )

        # 2. Warning Trigger: Accrual Divergence (Paper Profits without Cash)
        if metrics.safeguards.flag_accrual_divergence:
            title = f"PERINGATAN DIVERGENSI AKRUAL: {ticker} ({company_name})"
            msg = (
                f"Emiten membukukan laba di atas kertas (Rp {format_idr_nominal(ni)}) "
                f"namun arus kas operasional negatif (Rp {cfo_disp}). "
                f"Rasio Sloan Accrual berada pada level tinggi ({sloan_pct})."
            )
            if check_language_compliance(msg):
                alerts.append(
                    FilingAlertNotification(
                        ticker=ticker,
                        fiscal_year=2025,
                        period_code="FY",
                        alert_level="WARNING",
                        title=title,
                        message=msg,
                        metrics=metrics,
                    )
                )

        # 3. Informational Trigger: Normal filing release with solid metrics
        if not alerts:
            title = f"UPDATE LAPORAN KEUANGAN: {ticker} ({company_name})"
            debt_status = (
                "Bebas utang jangka pendek"
                if metrics.cash_coverage.debt_free_short_term
                else f"Rasio kas {cov_disp}"
            )
            msg = (
                f"Laporan keuangan tercatat dengan kondisi kas stabil. "
                f"Arus kas operasional Rp {cfo_disp} dan {debt_status}."
            )
            alerts.append(
                FilingAlertNotification(
                    ticker=ticker,
                    fiscal_year=2025,
                    period_code="FY",
                    alert_level="INFO",
                    title=title,
                    message=msg,
                    metrics=metrics,
                )
            )

        return alerts

    def get_notifications_for_user(self, user_id: str) -> list[str]:
        """
        Retrieves formatted notifications for all tickers on user's watchlist.
        """
        watched_tickers = self.repo.get_user_watchlist(user_id)
        if not watched_tickers:
            return []

        from scripts.run_case_evaluation import evaluate_filing

        notifications: list[str] = []
        for ticker in watched_tickers:
            issuer = self.repo.get_issuer(ticker)
            if not issuer:
                continue

            # Latest filing
            query = """
            SELECT filing_id FROM filings
            WHERE ticker = ? ORDER BY fiscal_year DESC LIMIT 1;
            """
            with self.repo.get_connection() as conn:
                row = conn.execute(query, (ticker,)).fetchone()
            if not row:
                continue

            metrics = evaluate_filing(row["filing_id"], self.repo)
            if not metrics:
                continue

            alerts = self.evaluate_filing_for_alerts(metrics, issuer.company_name)
            for alert in alerts:
                notifications.append(alert.format_telegram_alert())

        return notifications
