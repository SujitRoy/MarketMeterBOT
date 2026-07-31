"""
SQLite database layer for MarketMeter.
Handles schema creation, migrations, and all CRUD operations.
"""
import sqlite3
import logging
from datetime import date, datetime
from typing import Optional, Any
from contextlib import contextmanager

from src.core.config import (
    DB_PATH, ANALYSIS_START_DATE, ANALYSIS_WINDOW_DAYS,
    REPORT_CACHE_VERSION, REPORT_CACHE_RETAIN_DAYS,
)

logger = logging.getLogger(__name__)

# ── Connection Management ──────────────────────────────────────────

@contextmanager
def get_connection():
    """Yield a sqlite3 connection optimized for 1GB RAM server."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Memory-optimized settings for 1GB RAM
    conn.execute("PRAGMA journal_mode = WAL")          # Faster, less memory
    conn.execute("PRAGMA synchronous = NORMAL")       # Balance speed/safety
    conn.execute("PRAGMA cache_size = -32768")        # 32MB cache (not 64MB)
    conn.execute("PRAGMA temp_store = MEMORY")        # Temp tables in RAM
    conn.execute("PRAGMA mmap_size = 134217728")      # 128MB mmap (not 256MB)
    conn.execute("PRAGMA page_size = 4096")           # Optimal page size
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # Prevent bloat
    conn.execute("PRAGMA secure_delete = OFF")        # Faster deletes
    conn.execute("PRAGMA foreign_keys = ON")
    
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables and indexes if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
        -- Core bhavcopy data
        CREATE TABLE IF NOT EXISTS bhavcopy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            series TEXT DEFAULT 'EQ',
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            last REAL,
            prevclose REAL,
            volume INTEGER,
            value_lakh REAL,
            del_pct REAL,
            avg_price REAL,
            trade_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            UNIQUE(symbol, trade_date)
        );

        CREATE INDEX IF NOT EXISTS idx_bhavcopy_symbol_date
            ON bhavcopy(symbol, trade_date);
        CREATE INDEX IF NOT EXISTS idx_bhavcopy_date
            ON bhavcopy(trade_date);
        CREATE INDEX IF NOT EXISTS idx_bhavcopy_symbol
            ON bhavcopy(symbol);

        -- DECISION (idx_bhavcopy_cover; measured on a byte-identical replica, live DB untouched):
        -- a covering index (symbol, trade_date, close, high, low, volume,
        -- value_lakh, avg_price) speeds the analyzer range scan ~1.7-1.9x but costs
        -- ~153 MB extra disk (15%) plus a one-time ~85 s CREATE on this 1 GB table.
        -- The analyzer path is not a nightly bottleneck (report is cache-served at
        -- ~1 ms), so the index is deliberately NOT created on the 954 MB host.

        -- Sync tracking
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date DATE UNIQUE NOT NULL,
            status TEXT CHECK(status IN ('success','failed','holiday','skipped','not_available')),
            records_count INTEGER DEFAULT 0,
            error_message TEXT,
            synced_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
        );

        -- Daily pre-computed analysis cache
        CREATE TABLE IF NOT EXISTS daily_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            analysis_date DATE NOT NULL,
            close REAL,
            volume INTEGER,
            rsi_14 REAL,
            adx_14 REAL,
            macd_line REAL,
            signal_line REAL,
            macd_hist REAL,
            sma_20 REAL,
            sma_50 REAL,
            sma_100 REAL,
            sma_200 REAL,
            ema_20 REAL,
            ema_50 REAL,
            ema_100 REAL,
            ema_200 REAL,
            atr_14 REAL,
            bb_upper REAL,
            bb_lower REAL,
            rel_volume REAL,
            obv_trend REAL,
            avg_price REAL,
            composite_score INTEGER,
            recommendation TEXT CHECK(recommendation IN
                ('STRONG_BUY','BUY','ACCUMULATE','WATCH','CAUTION','AVOID')),
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            UNIQUE(symbol, analysis_date)
        );

        CREATE INDEX IF NOT EXISTS idx_analysis_date
            ON daily_analysis(analysis_date);
        CREATE INDEX IF NOT EXISTS idx_analysis_rec
            ON daily_analysis(analysis_date, recommendation);

        -- Stats cache for fast dashboard queries
        CREATE TABLE IF NOT EXISTS stats_cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
        );

        -- Rendered report cache. Keyed by resolved analysis_date (never
        -- date.today()) plus a layout version so a format change invalidates
        -- every stale payload without a migration. WITHOUT ROWID keeps the
        -- hit path a single primary-key seek.
        CREATE TABLE IF NOT EXISTS report_cache (
            kind          TEXT NOT NULL,
            analysis_date DATE NOT NULL,
            version       INTEGER NOT NULL,
            payload       TEXT NOT NULL,
            built_at      TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (kind, analysis_date, version)
        ) WITHOUT ROWID;

        -- Telegram subscribers
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscribed_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            active BOOLEAN DEFAULT 1,
            receive_reports BOOLEAN DEFAULT 1
        );
        """)
    logger.info("Database initialized at %s", DB_PATH)

    # Migration: check if sync_log constraint needs updating (separate connection)
    with get_connection() as conn:
        row = conn.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='sync_log'
        """).fetchone()
        if row and "'not_available'" not in row[0]:
            conn.executescript("""
                ALTER TABLE sync_log RENAME TO sync_log_old;
                CREATE TABLE sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date DATE UNIQUE NOT NULL,
                    status TEXT CHECK(status IN ('success','failed','holiday','skipped','not_available')),
                    records_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO sync_log SELECT * FROM sync_log_old;
                DROP TABLE sync_log_old;
            """)
            logger.info("Migrated sync_log to include 'not_available' status")

    _migrate_analysis_columns()


# Columns added after the original daily_analysis schema shipped. CREATE TABLE
# IF NOT EXISTS will not alter an existing table, so pre-existing databases need
# an explicit ADD COLUMN. ALTER TABLE ADD COLUMN is metadata-only in SQLite, so
# this stays O(1) even against the 2.3M-row database.
_ANALYSIS_ADDED_COLUMNS = {
    "ema_100":   "REAL",
    "ema_200":   "REAL",
    "avg_price": "REAL",
}

# NSE ships AVG_PRICE in the BhavCopy CSV. Storing it means avg_price is the
# exchange's own figure rather than a turnover/volume approximation.
_BHAVCOPY_ADDED_COLUMNS = {
    "avg_price": "REAL",
}


def _migrate_analysis_columns() -> None:
    """Add any missing daily_analysis / bhavcopy columns. Idempotent."""
    with get_connection() as conn:
        for table, wanted in (("daily_analysis", _ANALYSIS_ADDED_COLUMNS),
                              ("bhavcopy", _BHAVCOPY_ADDED_COLUMNS)):
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for col, decl in wanted.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                    logger.info("Added %s.%s", table, col)


# ── BhavCopy CRUD ───────────────────────────────────────────────────

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
            _update_stats_cache(conn, inserted, rows)

        return inserted


def _update_stats_cache(conn, inserted: int, rows: list[dict]):
    """Update stats cache after bulk insert."""
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


# ── Sync Log ────────────────────────────────────────────────────────

def log_sync(trade_date: date, status: str, records: int = 0, error: str = None):
    """Record a sync attempt."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO sync_log (trade_date, status, records_count, error_message, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (trade_date.isoformat(), status, records, error))


def get_last_synced_date() -> Optional[date]:
    """Get the last successfully synced trade date."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT trade_date FROM sync_log
            WHERE status = 'success'
            ORDER BY trade_date DESC
            LIMIT 1
        """).fetchone()
        if row:
            return date.fromisoformat(row['trade_date'])
        return None


def get_sync_status(days: int = 10) -> list[dict]:
    """Get recent sync log entries."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT trade_date, status, records_count, error_message, synced_at
            FROM sync_log
            ORDER BY trade_date DESC
            LIMIT ?
        """, (days,)).fetchall()
        return [dict(r) for r in rows]


def get_failed_syncs() -> list[dict]:
    """Get all failed/not_available syncs that need retry."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT trade_date, error_message
            FROM sync_log
            WHERE status IN ('failed', 'not_available')
            ORDER BY trade_date
        """).fetchall()
        return [dict(r) for r in rows]


def get_holiday_dates() -> list[dict]:
    """Get dates marked as confirmed holidays (weekends + known NSE holidays)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT trade_date
            FROM sync_log
            WHERE status = 'holiday'
            ORDER BY trade_date
        """).fetchall()
        return [dict(r) for r in rows] 


# ── Daily Analysis Cache ───────────────────────────────────────────

def save_daily_analysis(rows: list[dict]) -> int:
    """Bulk insert/update analysis results using executemany. Returns count."""
    if not rows:
        return 0

    with get_connection() as conn:
        columns = [
            'symbol', 'analysis_date', 'close', 'volume',
            'rsi_14', 'adx_14', 'macd_line', 'signal_line', 'macd_hist',
            'sma_20', 'sma_50', 'sma_100', 'sma_200',
            'ema_20', 'ema_50', 'ema_100', 'ema_200',
            'atr_14', 'bb_upper', 'bb_lower',
            'rel_volume', 'obv_trend', 'avg_price',
            'composite_score', 'recommendation'
        ]
        tuples = [tuple(r.get(c) for c in columns) for r in rows]

        # O(1) counter instead of a COUNT(*) pair. Note INSERT OR REPLACE
        # counts both the delete and the insert of a replaced row, so this is
        # "rows written", which is what the caller reports.
        before = conn.total_changes

        conn.executemany("""
            INSERT OR REPLACE INTO daily_analysis
                (symbol, analysis_date, close, volume,
                 rsi_14, adx_14, macd_line, signal_line, macd_hist,
                 sma_20, sma_50, sma_100, sma_200,
                 ema_20, ema_50, ema_100, ema_200,
                 atr_14, bb_upper, bb_lower,
                 rel_volume, obv_trend, avg_price,
                 composite_score, recommendation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?)
        """, tuples)

        return conn.total_changes - before


def get_latest_analysis(analysis_date: Optional[date] = None) -> list[dict]:
    """Get analysis for a specific date (default: latest)."""
    with get_connection() as conn:
        if analysis_date is None:
            # Get latest analysis date
            row = conn.execute(
                "SELECT MAX(analysis_date) as dt FROM daily_analysis"
            ).fetchone()
            if not row or not row['dt']:
                return []
            analysis_date = row['dt']

        rows = conn.execute("""
            SELECT * FROM daily_analysis
            WHERE analysis_date = ?
            ORDER BY composite_score DESC
        """, (analysis_date.isoformat() if isinstance(analysis_date, date) else analysis_date,)).fetchall()
        return [dict(r) for r in rows]


def get_resolved_analysis_date() -> Optional[date]:
    """
    The latest date that actually has analysis rows.

    Callers must resolve through this rather than assuming date.today():
    analysis runs after the 6:30 PM sync, so between midnight and the next
    run date.today() has zero rows. Keying a cache on today() would store the
    empty "no data" report and serve it all day.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(analysis_date) as dt FROM daily_analysis"
        ).fetchone()
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None


def get_analysis_by_recommendation(analysis_date: Optional[date] = None) -> dict[str, list[dict]]:
    """Get analysis grouped by recommendation category."""
    results = get_latest_analysis(analysis_date)
    grouped: dict[str, list[dict]] = {
        "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
        "WATCH": [], "CAUTION": [], "AVOID": []
    }
    for r in results:
        rec = r.get('recommendation', 'AVOID')
        if rec in grouped:
            grouped[rec].append(r)
    return grouped


# ── Report Cache ────────────────────────────────────────────────────

def get_cached_report(kind: str, analysis_date: date) -> Optional[str]:
    """
    Return a previously rendered report, or None on miss.

    Single primary-key seek on a WITHOUT ROWID table: ~0.08ms, against ~1.1s
    to render from scratch.
    """
    with get_connection() as conn:
        row = conn.execute("""
            SELECT payload FROM report_cache
            WHERE kind = ? AND analysis_date = ? AND version = ?
        """, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION)).fetchone()
        return row['payload'] if row else None


def put_cached_report(kind: str, analysis_date: date, payload: str) -> None:
    """Store a rendered report and prune payloads outside the retention window."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO report_cache
                (kind, analysis_date, version, payload, built_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION, payload))

        # Keep the table tiny: newest N dates per kind, plus drop stale versions.
        conn.execute("""
            DELETE FROM report_cache
            WHERE version <> ?
               OR analysis_date NOT IN (
                    SELECT analysis_date FROM report_cache
                    WHERE kind = ?
                    ORDER BY analysis_date DESC
                    LIMIT ?
               )
        """, (REPORT_CACHE_VERSION, kind, REPORT_CACHE_RETAIN_DAYS))


def invalidate_report_cache(kind: Optional[str] = None) -> int:
    """Drop cached reports. Returns rows removed."""
    with get_connection() as conn:
        if kind is None:
            cur = conn.execute("DELETE FROM report_cache")
        else:
            cur = conn.execute("DELETE FROM report_cache WHERE kind = ?", (kind,))
        return cur.rowcount


# ── Subscribers ─────────────────────────────────────────────────────

def add_subscriber(chat_id: int, username: str = None,
                   first_name: str = None, last_name: str = None) -> bool:
    """Add or re-activate a subscriber. Returns True if newly added."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT chat_id, active FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if existing:
            if not existing['active']:
                conn.execute("""
                    UPDATE subscribers SET active = 1, receive_reports = 1,
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name),
                        last_name = COALESCE(?, last_name)
                    WHERE chat_id = ?
                """, (username, first_name, last_name, chat_id))
                return True
            return False
        else:
            conn.execute("""
                INSERT INTO subscribers (chat_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (chat_id, username, first_name, last_name))
            return True


def remove_subscriber(chat_id: int) -> bool:
    """Soft-delete a subscriber. Returns True if they existed and were active."""
    with get_connection() as conn:
        cur = conn.execute("""
            UPDATE subscribers SET active = 0, receive_reports = 0
            WHERE chat_id = ? AND active = 1
        """, (chat_id,))
        return cur.rowcount > 0


def get_active_subscribers() -> list[dict]:
    """Get all active subscribers who want reports."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT chat_id, username, first_name, last_name
            FROM subscribers
            WHERE active = 1 AND receive_reports = 1
        """).fetchall()
        return [dict(r) for r in rows]


def get_all_subscribers() -> list[dict]:
    """Get all subscribers (including inactive)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT chat_id, username, first_name, last_name, active, receive_reports, subscribed_at
            FROM subscribers
            ORDER BY subscribed_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_subscriber_count() -> int:
    """Count of active subscribers."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM subscribers WHERE active = 1"
        ).fetchone()
        return row['cnt']


# ── Maintenance ─────────────────────────────────────────────────────

def vacuum_db():
    """Reclaim space and optimize database."""
    with get_connection() as conn:
        conn.execute("VACUUM")
    logger.info("Database vacuumed")


def init_stats_cache(conn=None):
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


def _init_stats_cache_impl(conn):
    """Internal implementation of stats cache initialization."""
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


# ── Intraday Tables ──────────────────────────────────────────────────

_INTRADAY_SCHEMA = """
-- 5-minute candles for tracked symbols (intraday)
CREATE TABLE IF NOT EXISTS intraday_candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    candle_ts TIMESTAMP NOT NULL,        -- 5-min bucket start (IST)
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    vwap REAL,                           -- Session VWAP from TradingView
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    UNIQUE(symbol, candle_ts)
);

CREATE INDEX IF NOT EXISTS idx_intraday_symbol_ts
    ON intraday_candles(symbol, candle_ts);

-- Intraday alerts log
CREATE TABLE IF NOT EXISTS intraday_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,            -- BREAKOUT, VOLUME_SPIKE, RSI_EXTREME, VWAP_RECLAIM
    candle_ts TIMESTAMP NOT NULL,
    price REAL,
    details TEXT,                        -- JSON with indicator values
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_alerts_symbol_ts
    ON intraday_alerts(symbol, candle_ts);

-- Symbols tracked for intraday (auto from morning report + manual)
CREATE TABLE IF NOT EXISTS tracked_symbols (
    symbol TEXT PRIMARY KEY,
    added_by TEXT DEFAULT 'AUTO_REPORT', -- AUTO_REPORT, MANUAL
    added_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    active BOOLEAN DEFAULT 1
);
"""


def init_intraday_tables():
    """Create intraday tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript(_INTRADAY_SCHEMA)
    logger.info("Intraday tables initialized")


def upsert_intraday_candles(rows: list[dict]) -> int:
    """Bulk insert/update 5-minute candles."""
    if not rows:
        return 0

    with get_connection() as conn:
        before = conn.total_changes
        conn.executemany("""
            INSERT OR REPLACE INTO intraday_candles
                (symbol, candle_ts, open, high, low, close, volume, vwap)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (r["symbol"], r["candle_ts"], r.get("open"), r.get("high"),
             r.get("low"), r.get("close"), r.get("volume"), r.get("vwap"))
            for r in rows
        ])
        return conn.total_changes - before


def get_intraday_candles(symbol: str, from_ts: str = None, limit: int = 78) -> list[dict]:
    """
    Get intraday candles for a symbol.
    Default limit 78 = 6.5 hours * 12 (5-min buckets) = full trading day.
    """
    with get_connection() as conn:
        if from_ts:
            rows = conn.execute("""
                SELECT * FROM intraday_candles
                WHERE symbol = ? AND candle_ts >= ?
                ORDER BY candle_ts ASC
                LIMIT ?
            """, (symbol, from_ts, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM intraday_candles
                WHERE symbol = ?
                ORDER BY candle_ts DESC
                LIMIT ?
            """, (symbol, limit)).fetchall()
        return [dict(r) for r in rows]


def add_tracked_symbol(symbol: str, added_by: str = "MANUAL") -> bool:
    """Add symbol to intraday tracking list."""
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT OR REPLACE INTO tracked_symbols (symbol, added_by, active)
            VALUES (?, ?, 1)
        """, (symbol, added_by))
        return cur.rowcount > 0


def get_tracked_symbols() -> list[dict]:
    """Get all active tracked symbols."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT symbol, added_by, added_at FROM tracked_symbols
            WHERE active = 1
            ORDER BY added_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def remove_tracked_symbol(symbol: str) -> bool:
    """Soft-delete a tracked symbol."""
    with get_connection() as conn:
        cur = conn.execute("""
            UPDATE tracked_symbols SET active = 0 WHERE symbol = ?
        """, (symbol,))
        return cur.rowcount > 0


def log_intraday_alert(symbol: str, alert_type: str, candle_ts: str,
                        price: float, details: dict) -> int:
    """Log an intraday alert."""
    import json
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO intraday_alerts (symbol, alert_type, candle_ts, price, details)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, alert_type, candle_ts, price, json.dumps(details)))
        return cur.lastrowid


def get_recent_alerts(symbol: str = None, hours: int = 24) -> list[dict]:
    """Get recent intraday alerts."""
    with get_connection() as conn:
        if symbol:
            rows = conn.execute("""
                SELECT * FROM intraday_alerts
                WHERE symbol = ? AND candle_ts >= datetime('now', ?)
                ORDER BY candle_ts DESC
            """, (symbol, f'-{hours} hours')).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM intraday_alerts
                WHERE candle_ts >= datetime('now', ?)
                ORDER BY candle_ts DESC
                LIMIT 100
            """, (f'-{hours} hours',)).fetchall()
        return [dict(r) for r in rows]


def prune_old_intraday(days: int = 30):
    """Remove intraday data older than N days."""
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM intraday_candles
            WHERE candle_ts < datetime('now', ?)
        """, (f'-{days} days',))
        conn.execute("""
            DELETE FROM intraday_alerts
            WHERE created_at < datetime('now', ?)
        """, (f'-{days} days',))
    logger.info("Pruned intraday data older than %d days", days)

