"""
db/bhavcopy_repo — CRUD for the `bhavcopy` table.

Phase 2 moves (verbatim from /database.py):
- insert_bhavcopy_batch
- _update_stats_cache
- get_stock_history
- get_all_symbols
- get_latest_trade_date
- get_date_range
- get_total_records
- get_unique_symbols_count

All SQL is byte-identical to the original.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from marketmeter.core.config import ANALYSIS_START_DATE, ANALYSIS_WINDOW_DAYS
from marketmeter.db.connection import get_connection
from marketmeter.db.stats_repo import update_stats_cache_after_insert


def insert_bhavcopy_batch(rows: list[dict]) -> int:
    """Bulk insert bhavcopy rows using executemany. Returns count of inserted rows."""
    if not rows:
        return 0

    with get_connection() as conn:
        columns = ['symbol', 'series', 'open', 'high', 'low', 'close', 'last',
                   'prevclose', 'volume', 'value_lakh', 'del_pct', 'trade_date',
                   'avg_price']
        tuples = [tuple(r.get(c) for c in columns) for r in rows]

        # conn.total_changes is an O(1) counter. The previous COUNT(*)
        # before/after pair cost ~23.6s each on 2.3M rows, i.e. ~47s of pure
        # counting per synced date.
        before = conn.total_changes

        conn.executemany("""
            INSERT OR IGNORE INTO bhavcopy
                (symbol, series, open, high, low, close, last, prevclose,
                 volume, value_lakh, del_pct, trade_date, avg_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuples)

        inserted = conn.total_changes - before

        # Update stats cache if new rows were inserted
        if inserted > 0:
            update_stats_cache_after_insert(conn, inserted, rows)

        return inserted


def get_stock_history(symbol: str, min_days: int = 50,
                      window: Optional[int] = ANALYSIS_WINDOW_DAYS) -> list[dict]:
    """
    Get history for a single stock, ordered by date ascending.

    window=None reads every stored row from ANALYSIS_START_DATE onward. A fixed
    window is cheaper but leaves EMA unconverged: EMA is recursive with no fixed
    lookback, and seeding EMA-200 from 260 rows measured 17.28% off on COFORGE.
    SMA is a true rolling window and was exact either way.

    Only the columns the analyzer reads are selected. value_lakh is included so
    avg_price (turnover / volume) can be derived without a second query.

    The series filter is intentionally omitted: transform_bhavcopy hardcodes
    series='EQ', so the column is constant and filtering on it only blocks
    index-only access.
    """
    with get_connection() as conn:
        if window is None:
            rows = conn.execute("""
                SELECT trade_date, close, high, low, volume, value_lakh, avg_price
                FROM bhavcopy
                WHERE symbol = ? AND trade_date >= ?
                ORDER BY trade_date ASC
            """, (symbol, ANALYSIS_START_DATE)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM (
                    SELECT trade_date, close, high, low, volume, value_lakh, avg_price
                    FROM bhavcopy
                    WHERE symbol = ? AND trade_date >= ?
                    ORDER BY trade_date DESC
                    LIMIT ?
                ) ORDER BY trade_date ASC
            """, (symbol, ANALYSIS_START_DATE, window)).fetchall()

        if len(rows) < min_days:
            return []
        return [dict(r) for r in rows]


def get_all_symbols(min_records: int = 50) -> list[str]:
    """Get all symbols with at least min_records data points."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT symbol, COUNT(*) as cnt
            FROM bhavcopy
            WHERE trade_date >= ?
            GROUP BY symbol
            HAVING cnt >= ?
            ORDER BY symbol
        """, (ANALYSIS_START_DATE, min_records)).fetchall()
        return [r['symbol'] for r in rows]


def get_latest_trade_date() -> Optional[date]:
    """Get the most recent trade_date in bhavcopy."""
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(trade_date) as dt FROM bhavcopy").fetchone()
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None


def get_date_range() -> tuple[Optional[date], Optional[date]]:
    """Get min and max trade_date."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MIN(trade_date) as mn, MAX(trade_date) as mx FROM bhavcopy"
        ).fetchone()
        mn = date.fromisoformat(row['mn']) if row['mn'] else None
        mx = date.fromisoformat(row['mx']) if row['mx'] else None
        return mn, mx


def get_total_records() -> int:
    """Total bhavcopy rows."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM bhavcopy").fetchone()
        return row['cnt']


def get_unique_symbols_count() -> int:
    """Count of unique symbols."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT symbol) as cnt FROM bhavcopy WHERE series='EQ'"
        ).fetchone()
        return row['cnt']


__all__ = [
    "insert_bhavcopy_batch",
    "get_stock_history",
    "get_all_symbols",
    "get_latest_trade_date",
    "get_date_range",
    "get_total_records",
    "get_unique_symbols_count",
]