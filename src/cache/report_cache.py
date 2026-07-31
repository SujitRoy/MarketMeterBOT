"""
Report Cache
Specialized cache for rendered reports with database persistence.
"""
import logging
from datetime import date

from src.database.repositories import ReportCacheRepository

logger = logging.getLogger(__name__)


class ReportCache:
    """Cache for rendered reports with DB persistence."""

    def __init__(self):
        self.repo = ReportCacheRepository()

    def get(self, kind: str, analysis_date: date) -> str | None:
        """Get cached report."""
        return self.repo.get_cached_report(kind, analysis_date)

    def set(self, kind: str, analysis_date: date, content: str) -> None:
        """Cache a report."""
        self.repo.put_cached_report(kind, analysis_date, content)

    def invalidate(self, kind: str | None = None) -> int:
        """Invalidate cached reports."""
        return self.repo.invalidate(kind)

    def warm(self, kind: str, analysis_date: date, content: str) -> bool:
        """Warm cache with pre-rendered content."""
        try:
            self.set(kind, analysis_date, content)
            logger.info("Warmed %s report cache for %s", kind, analysis_date)
            return True
        except Exception as e:
            logger.error("Failed to warm cache: %s", e)
            return False


# Global instance
report_cache = ReportCache()


def get_report_cache() -> ReportCache:
    """Get global report cache."""
    return report_cache
