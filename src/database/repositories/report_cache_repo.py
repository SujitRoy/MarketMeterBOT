"""
Report Cache Repository
Data access for rendered report caching.
"""
import logging
from datetime import date

from src.core.config import REPORT_CACHE_RETAIN_DAYS, REPORT_CACHE_VERSION
from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository

logger = logging.getLogger(__name__)


class ReportCacheRepository(BaseRepository):
    """Repository for report cache operations."""

    def get_cached_report(self, kind: str, analysis_date: date) -> str | None:
        """Return a previously rendered report, or None on miss."""
        row = self.fetch_one(GET_CACHED_REPORT, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION))
        return row['payload'] if row else None

    def put_cached_report(self, kind: str, analysis_date: date, payload: str) -> None:
        """Store a rendered report and prune payloads outside the retention window."""
        self.execute(PUT_CACHED_REPORT, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION, payload))

        # Prune old cache entries
        self.execute(PRUNE_REPORT_CACHE, (REPORT_CACHE_VERSION, kind, REPORT_CACHE_RETAIN_DAYS))

    def invalidate(self, kind: str | None = None) -> int:
        """Drop cached reports. Returns rows removed."""
        if kind is None:
            cur = self.execute(INVALIDATE_ALL_REPORT_CACHE)
        else:
            cur = self.execute(INVALIDATE_REPORT_CACHE, (kind,))
        logger.info("Invalidated %d report cache entries (kind=%s)", cur, kind or "all")
        return cur


class ReportCacheReadRepository(ReadOnlyRepository):
    """Read-only repository for report cache queries."""

    def get_cached_report(self, kind: str, analysis_date: date) -> str | None:
        """Return a previously rendered report, or None on miss."""
        row = self.fetch_one(GET_CACHED_REPORT, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION))
        return row['payload'] if row else None
