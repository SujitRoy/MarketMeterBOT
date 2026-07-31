"""
Technical Summary Report
Generates a detailed technical analysis for a single symbol.
"""
import logging

from src.reports.base import BaseReport, ReportContext, ReportResult
from src.reports.registry import register_report

logger = logging.getLogger(__name__)


@register_report("technical")
class TechnicalReport(BaseReport):
    """Technical summary report for a single symbol."""

    kind = "technical"
    name = "Technical Summary"
    description = "Detailed technical analysis for a specific stock"

    def __init__(self, context: ReportContext, symbol: str = None):
        super().__init__(context)
        self.symbol = symbol or context.extra.get("symbol")

    def build(self) -> ReportResult:
        """Build technical report for a symbol."""
        if not self.symbol:
            return ReportResult(
                content="No symbol specified for technical report",
                chunks=["No symbol specified for technical report"]
            )

        # This would fetch detailed data and build the report
        # Placeholder implementation
        lines = [
            f"📈 **Technical Summary — {self.symbol}**",
            f"📅 {self.context.analysis_date.strftime('%d %b %Y')}",
            "",
            "Detailed technical analysis coming soon...",
            "",
            "⚠️ _Not financial advice._"
        ]

        content = "\n".join(lines)
        chunks = self.chunk_message(content)
        return ReportResult(content=content, chunks=chunks)
