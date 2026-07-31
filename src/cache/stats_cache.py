"""
Stats Cache
Cache for database statistics with auto-refresh.
"""
import logging
import time
from typing import Any

from src.database.repositories import StatsRepository

logger = logging.getLogger(__name__)


class StatsCache:
    """Cache for database statistics."""

    def __init__(self, ttl: int = 300):  # 5 minutes default
        self.repo = StatsRepository()
        self._cache: dict[str, Any] = {}
        self._cached_at: float = 0
        self._ttl = ttl

    def get(self, force_refresh: bool = False) -> dict[str, Any]:
        """Get stats, using cache if valid."""
        now = time.time()

        if not force_refresh and self._cache and (now - self._cached_at) < self._ttl:
            return self._cache

        self._cache = self.repo.get_stats()
        self._cached_at = now
        return self._cache

    def invalidate(self) -> None:
        """Invalidate cache."""
        self._cache = {}
        self._cached_at = 0

    def get_cached(self) -> dict[str, Any] | None:
        """Get cached stats without refreshing."""
        if self._cache and (time.time() - self._cached_at) < self._ttl:
            return self._cache
        return None

    def refresh(self) -> dict[str, Any]:
        """Force refresh stats."""
        return self.get(force_refresh=True)


# Global instance
stats_cache = StatsCache()


def get_stats_cache() -> StatsCache:
    """Get global stats cache."""
    return stats_cache
