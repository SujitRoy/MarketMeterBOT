"""
db/schema — CREATE TABLE / CREATE INDEX statements and migration logic.

Phase 2 moves:
- init_db() (the master bootstrap that creates every table and runs the
  sync_log -> sync_log_old migration) from /database.py.
- _migrate_analysis_columns() (post-init column additions for daily_analysis
  and bhavcopy) from /database.py.

The `_ANALYSIS_ADDED_COLUMNS` and `_BHAVCOPY_ADDED_COLUMNS` dicts stay here
because they are part of the schema contract.

All SQL is byte-identical to the original. The split is purely a file move.
"""
from __future__ import annotations

from marketmeter.core.config import DB_PATH
from marketmeter.core.logging import get_logger
from marketmeter.db.connection import get_connection

logger = get_logger(__name__)


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


def init_db() -> None:
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


def init_intraday_tables() -> None:
    """Create intraday tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript(_INTRADAY_SCHEMA)
    logger.info("Intraday tables initialized")


__all__ = [
    "init_db",
    "init_intraday_tables",
    "_migrate_analysis_columns",
    "_INTRADAY_SCHEMA",
    "_ANALYSIS_ADDED_COLUMNS",
    "_BHAVCOPY_ADDED_COLUMNS",
]