"""
Report Registry
Central registry for all report types.
"""
import logging

from src.reports.base import BaseReport, ReportContext, ReportResult

logger = logging.getLogger(__name__)


class ReportRegistry:
    """Registry for report classes."""

    def __init__(self):
        self._reports: dict[str, type[BaseReport]] = {}
        self._instances: dict[str, BaseReport] = {}

    def register(self, kind: str, report_class: type[BaseReport]) -> None:
        """Register a report class."""
        if kind in self._reports:
            logger.warning("Overriding existing report for kind: %s", kind)
        self._reports[kind] = report_class
        logger.debug("Registered report: %s -> %s", kind, report_class.__name__)

    def unregister(self, kind: str) -> bool:
        """Unregister a report class."""
        if kind in self._reports:
            del self._reports[kind]
            self._instances.pop(kind, None)
            return True
        return False

    def get(self, kind: str) -> type[BaseReport] | None:
        """Get a report class by kind."""
        return self._reports.get(kind)

    def create(self, kind: str, context: ReportContext) -> BaseReport | None:
        """Create a report instance."""
        report_class = self.get(kind)
        if report_class is None:
            logger.error("Unknown report kind: %s", kind)
            return None

        # Cache instance per context (by analysis_date)
        cache_key = f"{kind}:{context.analysis_date.isoformat()}"
        if cache_key not in self._instances:
            self._instances[cache_key] = report_class(context)

        return self._instances[cache_key]

    def build(self, kind: str, context: ReportContext) -> ReportResult | None:
        """Build a report directly."""
        report = self.create(kind, context)
        if report is None:
            return None
        return report.build()

    def list_registered(self) -> list[str]:
        """List all registered report kinds."""
        return list(self._reports.keys())

    def clear_cache(self):
        """Clear instance cache."""
        self._instances.clear()


# Global registry instance
registry = ReportRegistry()


def register_report(kind: str):
    """Decorator to register a report class."""
    def decorator(cls: type[BaseReport]):
        registry.register(kind, cls)
        cls.kind = kind  # Set kind attribute
        return cls
    return decorator
