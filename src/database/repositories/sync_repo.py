"""
Sync Repository
Data access for sync log operations.
"""
import logging
from datetime import date
from typing import Any

from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository

logger = logging.getLogger(__name__)


class SyncRepository(BaseRepository):
    """Repository for sync log operations."""

    def log_sync(
        self,
        trade_date: date,
        status: str,
        records: int = 0,
        error: str | None = None
    ) -> None:
        """Record a sync attempt."""
        self.execute(INSERT_SYNC_LOG, (trade_date.isoformat(), status, records, error))

    def get_last_synced_date(self) -> date | None:
        """Get the last successfully synced trade date."""
        row = self.fetch_one(GET_LAST_SYNCED_DATE)
        if row:
            return date.fromisoformat(row['trade_date'])
        return None

    def get_sync_status(self, days: int = 10) -> list[dict[str, Any]]:
        """Get recent sync log entries."""
        return self.fetch_all(GET_SYNC_STATUS, (days,))

    def get_failed_syncs(self) -> list[dict[str, Any]]:
        """Get all failed/not_available syncs that need retry."""
        return self.fetch_all(GET_FAILED_SYNCS)

    def get_holiday_dates(self) -> list[dict[str, Any]]:
        """Get dates marked as confirmed holidays."""
        return self.fetch_all(GET_HOLIDAY_DATES)


class SyncReadRepository(ReadOnlyRepository):
    """Read-only repository for sync queries."""

    def get_last_synced_date(self) -> date | None:
        """Get the last successfully synced trade date."""
        row = self.fetch_one(GET_LAST_SYNCED_DATE)
        if row:
            return date.fromisoformat(row['trade_date'])
        return None

    def get_sync_status(self, days: int = 10) -> list[dict[str, Any]]:
        """Get recent sync log entries."""
        return self.fetch_all(GET_SYNC_STATUS, (days,))

    def get_failed_syncs(self) -> list[dict[str, Any]]:
        """Get all failed/not_available syncs that need retry."""
        return self.fetch_all(GET_FAILED_SYNCS)

    def get_holiday_dates(self) -> list[dict[str, Any]]:
        """Get dates marked as confirmed holidays."""
        return self.fetch_all(GET_HOLIDAY_DATES)
