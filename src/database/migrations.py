"""
Database Migrations
Schema version management and migration logic.
"""
import logging
import sqlite3

from src.database.connection import get_connection

logger = logging.getLogger(__name__)

# Current schema version - increment when making breaking changes
SCHEMA_VERSION = 4


def run_migrations() -> None:
    """Run all pending migrations."""
    with get_connection() as conn:
        # Create schema_version table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Get current version
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        current_version = row[0] if row else 0

        logger.info("Current schema version: %d, target: %d", current_version, SCHEMA_VERSION)

        # Run migrations
        if current_version < 1:
            _migrate_v1(conn)
        if current_version < 2:
            _migrate_v2(conn)
        if current_version < 3:
            _migrate_v3(conn)
        if current_version < 4:
            _migrate_v4(conn)

        # Update version
        conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        logger.info("Migrations complete. Schema version: %d", SCHEMA_VERSION)


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Migration v1: Initial schema creation."""
    logger.info("Running migration v1: Initial schema")

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

        -- Rendered report cache
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


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """Migration v2: Add missing columns to existing tables."""
    logger.info("Running migration v2: Add missing columns")

    # Add avg_price to bhavcopy if missing
    _add_column_if_missing(conn, "bhavcopy", "avg_price", "REAL")

    # Add ema_100, ema_200, avg_price to daily_analysis if missing
    _add_column_if_missing(conn, "daily_analysis", "ema_100", "REAL")
    _add_column_if_missing(conn, "daily_analysis", "ema_200", "REAL")
    _add_column_if_missing(conn, "daily_analysis", "avg_price", "REAL")


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """Migration v3: Add intraday tables."""
    logger.info("Running migration v3: Intraday tables")

    conn.executescript("""
        -- 5-minute candles for tracked symbols (intraday)
        CREATE TABLE IF NOT EXISTS intraday_candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            candle_ts TIMESTAMP NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            vwap REAL,
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            UNIQUE(symbol, candle_ts)
        );

        CREATE INDEX IF NOT EXISTS idx_intraday_symbol_ts
            ON intraday_candles(symbol, candle_ts);

        -- Intraday alerts log
        CREATE TABLE IF NOT EXISTS intraday_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            candle_ts TIMESTAMP NOT NULL,
            price REAL,
            details TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_symbol_ts
            ON intraday_alerts(symbol, candle_ts);

        -- Symbols tracked for intraday
        CREATE TABLE IF NOT EXISTS tracked_symbols (
            symbol TEXT PRIMARY KEY,
            added_by TEXT DEFAULT 'AUTO_REPORT',
            added_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            active BOOLEAN DEFAULT 1
        );
    """)


def _migrate_v4(conn: sqlite3.Connection) -> None:
    """Migration v4: Sync log status constraint update."""
    logger.info("Running migration v4: Sync log constraint")

    # Check if constraint needs updating
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


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """Add a column to a table if it doesn't exist."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        logger.info("Added %s.%s", table, column)


def get_schema_version() -> int:
    """Get current schema version."""
    with get_connection() as conn:
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return row[0] if row else 0


def reset_migrations() -> None:
    """Reset migration history (use with caution)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM schema_version")
    logger.warning("Migration history reset")
