"""
Backtest Results Report
Generates formatted backtest results.
"""
import logging
from typing import Any

from src.reports.base import BaseReport, ReportContext, ReportResult
from src.reports.registry import register_report

logger = logging.getLogger(__name__)


@register_report("backtest")
class BacktestReport(BaseReport):
    """Backtest results report."""

    kind = "backtest"
    name = "Backtest Results"
    description = "Historical backtest performance report"

    def __init__(self, context: ReportContext, backtest_result: Any = None):
        super().__init__(context)
        self.backtest_result = backtest_result or context.extra.get("backtest_result")

    def build(self) -> ReportResult:
        """Build backtest report from results."""
        if not self.backtest_result:
            return ReportResult(
                content="No backtest result provided",
                chunks=["No backtest result provided"]
            )

        r = self.backtest_result
        lines = [
            f"📊 **Backtest Results — {r.strategy_name}**",
            f"📅 {r.start_date.strftime('%d %b %Y')} → {r.end_date.strftime('%d %b %Y')}",
            "",
            f"Total Trades: {r.total_trades}",
            f"Win Rate: {r.win_rate:.2f}%",
            f"Avg Return: {r.avg_return:.2f}%",
            f"Total Return: {r.total_return:.2f}%",
            f"Max Drawdown: {r.max_drawdown:.2f}%",
            f"Sharpe Ratio: {r.sharpe_ratio:.2f}",
            "",
            "⚠️ _Past performance does not guarantee future results._"
        ]

        content = "\n".join(lines)
        chunks = self.chunk_message(content)
        return ReportResult(content=content, chunks=chunks)
