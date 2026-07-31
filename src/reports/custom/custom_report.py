"""
Custom Report
User-defined custom reports.
"""
import logging

from src.reports.base import BaseReport, ReportContext, ReportResult
from src.reports.registry import register_report

logger = logging.getLogger(__name__)


@register_report("custom")
class CustomReport(BaseReport):
    """Custom user-defined report."""

    kind = "custom"
    name = "Custom Report"
    description = "User-defined custom report"

    def __init__(self, context: ReportContext, template: str = None, params: dict = None):
        super().__init__(context)
        self.template = template or context.extra.get("template", "")
        self.params = params or context.extra.get("params", {})

    def build(self) -> ReportResult:
        """Build custom report from template."""
        # Placeholder implementation
        lines = [
            f"📝 **Custom Report — {self.context.analysis_date.strftime('%d %b %Y')}**",
            "",
            f"Template: {self.template}",
            f"Params: {self.params}",
            "",
            "Custom report coming soon...",
            "",
            "⚠️ _Not financial advice._"
        ]

        content = "\n".join(lines)
        chunks = self.chunk_message(content)
        return ReportResult(content=content, chunks=chunks)
