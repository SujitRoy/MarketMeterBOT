"""
Stats Cache Repository
Data access for database statistics caching.
"""
import logging
from typing import Any

from src.core.config import ANALYSIS_START_DATE
from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository
from src.database.connection import get_connection

logger = logging.getLogger(__name__)


class StatsRepository(BaseRepository):
    """Repository for stats cache operations."""

    def initialize_cache(self) -> None:
        """Initialize stats cache from current database state (one-time cold path)."""
        with get_connection() as conn:
            # Check if cache already exists
            total = conn.execute("SELECT value FROM stats_cache WHERE key = 'total_records'").fetchone()
            if total:
                return  # Cache already initialized

            # Build cache from actual data
            total = conn.execute("SELECT COUNT(*) FROM bhavcopy").fetchone()[0]
            symbols = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM bhavcopy WHERE trade_date >= ?",
                (ANALYSIS_START_DATE,)
            ).fetchone()[0]
            date_from = conn.execute("SELECT MIN(trade_date) FROM bhavcopy").fetchone()[0]
            date_to = conn.execute("SELECT MAX(trade_date) FROM bhavcopy").fetchone()[0]

            conn.execute(SET_STATS_CACHE, ('total_records', str(total)))
            conn.execute(SET_STATS_CACHE, ('unique_symbols', str(symbols)))
            conn.execute(SET_STATS_CACHE, ('date_from', str(date_from) if date_from else ''))
            conn.execute(SET_STATS_CACHE, ('date_to', str(date_to) if date_to else ''))
            logger.info("Stats cache initialized: %d records, %d symbols", total, symbols)

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics (uses cached stats only - no COUNT queries)."""
        with get_connection() as conn:
            # Get all cached stats in one query
            rows = conn.execute("""
                SELECT key, value FROM stats_cache 
                WHERE key IN ('total_records', 'unique_symbols', 'date_from', 'date_to',
                              'active_subscribers', 'symbols_dirty')
            """).fetchall()

            cache = {r['key']: r['value'] for r in rows}

            # If cache missing, initialize it (one-time slow query)
            if not cache or 'total_records' not in cache:
                self.initialize_cache()
                # Re-read after init
                rows = conn.execute("""
                    SELECT key, value FROM stats_cache 
                    WHERE key IN ('total_records', 'unique_symbols', 'date_from', 'date_to',
                                  'active_subscribers', 'symbols_dirty')
                """).fetchall()
                cache = {r['key']: r['value'] for r in rows}

            # Settle the deferred symbol count
            if cache.get('symbols_dirty') == '1' or 'unique_symbols' not in cache:
                symbols = conn.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM bhavcopy WHERE trade_date >= ?",
                    (ANALYSIS_START_DATE,)
                ).fetchone()[0]
                conn.execute(SET_STATS_CACHE, ('unique_symbols', str(symbols)))
                conn.execute(DELETE_STATS_CACHE_KEY, ('symbols_dirty',))
                cache['unique_symbols'] = str(symbols)

            # Get active subscribers count (small table, fast)
            subs = conn.execute("SELECT COUNT(*) as cnt FROM subscribers WHERE active = 1").fetchone()['cnt']

            return {
                "total_records": int(cache.get('total_records', 0)),
                "unique_symbols": int(cache.get('unique_symbols', 0)),
                "date_from": cache.get('date_from') or None,
                "date_to": cache.get('date_to') or None,
                "active_subscribers": subs,
            }

    def update_total_records(self, delta: int) -> None:
        """Update total records count by delta."""
        with get_connection() as conn:
            cur = conn.execute("SELECT value FROM stats_cache WHERE key = 'total_records'").fetchone()
            prev = int(cur[0]) if cur else 0
            conn.execute(SET_STATS_CACHE, ('total_records', str(prev + delta)))

    def update_date_range(self, min_date: str, max_date: str) -> None:
        """Update date range in cache."""
        with get_connection() as conn:
            cur = conn.execute("SELECT value FROM stats_cache WHERE key = 'date_from'").fetchone()
            prev_from = cur[0] if cur else ''
            if not prev_from or min_date < prev_from:
                conn.execute(SET_STATS_CACHE, ('date_from', min_date))

            cur = conn.execute("SELECT value FROM stats_cache WHERE key = 'date_to'").fetchone()
            prev_to = cur[0] if cur else ''
            if not prev_to or max_date > prev_to:
                conn.execute(SET_STATS_CACHE, ('date_to', max_date))

    def mark_symbols_dirty(self) -> None:
        """Mark symbols count as needing refresh."""
        self.execute(SET_STATS_CACHE, ('symbols_dirty', '1'))


class StatsReadRepository(ReadOnlyRepository):
    """Read-only repository for stats queries."""

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        # This needs a write connection for potential cache initialization
        # Use the BaseRepository implementation directly
        from src.database.repositories.stats_repo import StatsRepository
        return StatsRepository().get_stats()
