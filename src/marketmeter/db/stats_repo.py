"""
db/stats_repo — stats_cache CRUD + monitoring reads.

Phase 2 moves (verbatim from /database.py):
- _update_stats_cache (now public as update_stats_cache_after_insert)
- init_stats_cache
- _init_stats_cache_impl (now public as _init_stats_cache_impl; private by
  convention but imported by bhavcopy_repo)
- get_db_stats
- vacuum_db

All SQL is byte-identical to the original.

The split exposes one internal helper publicly so bhavcopy_repo can call it
without reaching through a closure: update_stats_cache_after_insert() does
exactly what _update_stats_cache did, but is now a module-level function so
imports work cleanly across the package boundary.

The same pattern applies to _init_stats_cache_impl, which init_stats_cache
and get_db_stats both call.
"""
from __future__ import annotations

from marketmeter.core.config import ANALYSIS_START_DATE
from marketmeter.core.logging import get_logger
from marketmeter.db.connection import get_connection

logger = get_logger(__name__)


def update_stats_cache_after_insert(conn, inserted: int, rows: list[dict]) -> None:
    """Update stats cache after bulk insert.

    Phase 2 promotion: was `_update_stats_cache` private in /database.py.
    Now module-public so bhavcopy_repo can call it across the package
    boundary. Behaviour byte-identical to the original.
    """
    if not rows:
        return

    # Get date range from inserted rows
    dates = [r['trade_date'] for r in rows if r.get('trade_date')]
    if not dates:
        return

    min_date = min(dates)
    max_date = max(dates)

    # Read current cache once, then update arithmetically. No COUNT(*) here:
    # on 2.3M rows that scan cost ~23.6s per call.
    cur = {r['key']: r['value'] for r in conn.execute(
        "SELECT key, value FROM stats_cache "
        "WHERE key IN ('total_records','date_from','date_to')"
    ).fetchall()}

    prev_total = int(cur.get('total_records') or 0)
    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                 ('total_records', str(prev_total + inserted)))

    # Widen the stored range instead of recomputing MIN/MAX over the table.
    prev_from = cur.get('date_from') or ''
    prev_to = cur.get('date_to') or ''
    if not prev_from or min_date < prev_from:
        conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                     ('date_from', min_date))
    if not prev_to or max_date > prev_to:
        conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                     ('date_to', max_date))

    # COUNT(DISTINCT symbol) costs ~4.2s. Flag it instead and let the next
    # stats read settle it, so a 1100-date backfill pays it once, not 1100x.
    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                 ('symbols_dirty', '1'))


def _init_stats_cache_impl(conn) -> None:
    """Internal implementation of stats cache initialization.

    Phase 2: kept underscore-prefixed as before. init_stats_cache and
    get_db_stats both call it.
    """
    # Check if cache already exists
    total = conn.execute("SELECT value FROM stats_cache WHERE key = 'total_records'").fetchone()
    if total:
        return  # Cache already initialized

    # Build cache from actual data (one-time cold path)
    total = conn.execute("SELECT COUNT(*) FROM bhavcopy").fetchone()[0]
    symbols = conn.execute(
        "SELECT COUNT(DISTINCT symbol) FROM bhavcopy WHERE trade_date >= ?",
        (ANALYSIS_START_DATE,)
    ).fetchone()[0]
    date_from = conn.execute("SELECT MIN(trade_date) FROM bhavcopy").fetchone()[0]
    date_to = conn.execute("SELECT MAX(trade_date) FROM bhavcopy").fetchone()[0]

    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                 ('total_records', str(total)))
    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                 ('unique_symbols', str(symbols)))
    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                 ('date_from', str(date_from) if date_from else ''))
    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                 ('date_to', str(date_to) if date_to else ''))
    logger.info("Stats cache initialized: %d records, %d symbols", total, symbols)


def init_stats_cache(conn=None) -> None:
    """Initialize stats cache from current database state.
    Args:
        conn: Optional existing connection to use."""
    if conn is not None:
        # Use provided connection
        _init_stats_cache_impl(conn)
    else:
        # Create own connection
        with get_connection() as c:
            _init_stats_cache_impl(c)


def get_db_stats() -> dict:
    """Get database statistics for monitoring (uses cached stats only - no COUNT queries)."""
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
            init_stats_cache(conn)
            # Re-read after init
            rows = conn.execute("""
                SELECT key, value FROM stats_cache
                WHERE key IN ('total_records', 'unique_symbols', 'date_from', 'date_to',
                              'active_subscribers', 'symbols_dirty')
            """).fetchall()
            cache = {r['key']: r['value'] for r in rows}

        # Settle the deferred symbol count. insert_bhavcopy_batch only raises a
        # dirty flag because COUNT(DISTINCT symbol) costs ~4.2s; paying it here
        # means a 1100-date backfill pays it once, not once per date.
        if cache.get('symbols_dirty') == '1' or 'unique_symbols' not in cache:
            symbols = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM bhavcopy WHERE trade_date >= ?",
                (ANALYSIS_START_DATE,)
            ).fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)",
                         ('unique_symbols', str(symbols)))
            conn.execute("DELETE FROM stats_cache WHERE key = 'symbols_dirty'")
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


def vacuum_db() -> None:
    """Reclaim space and optimize database."""
    with get_connection() as conn:
        conn.execute("VACUUM")
    logger.info("Database vacuumed")


__all__ = [
    "update_stats_cache_after_insert",
    "init_stats_cache",
    "_init_stats_cache_impl",
    "get_db_stats",
    "vacuum_db",
]