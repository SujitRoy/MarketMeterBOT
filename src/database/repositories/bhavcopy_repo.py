"""
BhavCopy Repository
Data access for NSE BhavCopy (EOD) data.
"""
import logging
from datetime import date
from typing import Any

from src.database.models import BhavCopyRow
from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository

logger = logging.getLogger(__name__)


class BhavCopyRepository(BaseRepository):
    """Repository for BhavCopy operations."""

    def insert_batch(self, rows: list[BhavCopyRow]) -> int:
        """Bulk insert bhavcopy rows. Returns count of inserted rows."""
        if not rows:
            return 0

        tuples = [row.to_db_tuple() for row in rows]

        with get_connection() as conn:
            before = conn.total_changes
            conn.executemany(INSERT_BHAVCOPY, tuples)
            inserted = conn.total_changes - before

            if inserted > 0:
                self._update_stats_cache(conn, inserted, rows)

            logger.info("Inserted %d bhavcopy rows", inserted)
            return inserted

    def _update_stats_cache(self, conn, inserted: int, rows: list[BhavCopyRow]) -> None:
        """Update stats cache after bulk insert."""
        dates = [r.trade_date.isoformat() for r in rows]
        if not dates:
            return

        min_date = min(dates)
        max_date = max(dates)

        # Read current cache
        cur = {r['key']: r['value'] for r in conn.execute(
            "SELECT key, value FROM stats_cache "
            "WHERE key IN ('total_records','date_from','date_to')"
        ).fetchall()}

        prev_total = int(cur.get('total_records') or 0)
        conn.execute(SET_STATS_CACHE, ('total_records', str(prev_total + inserted)))

        prev_from = cur.get('date_from') or ''
        prev_to = cur.get('date_to') or ''
        if not prev_from or min_date < prev_from:
            conn.execute(SET_STATS_CACHE, ('date_from', min_date))
        if not prev_to or max_date > prev_to:
            conn.execute(SET_STATS_CACHE, ('date_to', max_date))

        conn.execute(SET_STATS_CACHE, ('symbols_dirty', '1'))

    def get_history(
        self,
        symbol: str,
        min_days: int = 50,
        window: int | None = None
    ) -> list[dict[str, Any]]:
        """Get history for a single stock, ordered by date ascending."""
        from src.core.config import ANALYSIS_START_DATE, ANALYSIS_WINDOW_DAYS

        if window is None:
            window = ANALYSIS_WINDOW_DAYS

        if window is None:
            rows = self.fetch_all(GET_STOCK_HISTORY, (symbol, ANALYSIS_START_DATE))
        else:
            rows = self.fetch_all(GET_STOCK_HISTORY_WINDOWED, (symbol, ANALYSIS_START_DATE, window))

        if len(rows) < min_days:
            return []
        return rows

    def get_all_symbols(self, min_records: int = 50) -> list[str]:
        """Get all symbols with at least min_records data points."""
        from src.core.config import ANALYSIS_START_DATE
        rows = self.fetch_all(GET_ALL_SYMBOLS, (ANALYSIS_START_DATE, min_records))
        return [r['symbol'] for r in rows]

    def get_latest_trade_date(self) -> date | None:
        """Get the most recent trade_date in bhavcopy."""
        row = self.fetch_one(GET_LATEST_TRADE_DATE)
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None

    def get_date_range(self) -> tuple[date | None, date | None]:
        """Get min and max trade_date."""
        row = self.fetch_one(GET_DATE_RANGE)
        mn = date.fromisoformat(row['mn']) if row and row['mn'] else None
        mx = date.fromisoformat(row['mx']) if row and row['mx'] else None
        return mn, mx

    def get_total_records(self) -> int:
        """Total bhavcopy rows."""
        return self.fetch_scalar(GET_TOTAL_RECORDS) or 0

    def get_unique_symbols_count(self) -> int:
        """Count of unique symbols."""
        return self.fetch_scalar(GET_UNIQUE_SYMBOLS, ("EQ",)) or 0


class BhavCopyReadRepository(ReadOnlyRepository):
    """Read-only repository for BhavCopy queries."""

    def get_history(
        self,
        symbol: str,
        min_days: int = 50,
        window: int | None = None
    ) -> list[dict[str, Any]]:
        """Get history for a single stock, ordered by date ascending."""
        from src.core.config import ANALYSIS_START_DATE, ANALYSIS_WINDOW_DAYS

        if window is None:
            window = ANALYSIS_WINDOW_DAYS

        if window is None:
            rows = self.fetch_all(GET_STOCK_HISTORY, (symbol, ANALYSIS_START_DATE))
        else:
            rows = self.fetch_all(GET_STOCK_HISTORY_WINDOWED, (symbol, ANALYSIS_START_DATE, window))

        if len(rows) < min_days:
            return []
        return rows

    def get_all_symbols(self, min_records: int = 50) -> list[str]:
        """Get all symbols with at least min_records data points."""
        from src.core.config import ANALYSIS_START_DATE
        rows = self.fetch_all(GET_ALL_SYMBOLS, (ANALYSIS_START_DATE, min_records))
        return [r['symbol'] for r in rows]

    def get_latest_trade_date(self) -> date | None:
        """Get the most recent trade_date in bhavcopy."""
        row = self.fetch_one(GET_LATEST_TRADE_DATE)
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None
