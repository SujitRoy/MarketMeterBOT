"""
Parameterized SQL Queries
All SQL queries centralized for maintainability and security.
"""

# ── BhavCopy ────────────────────────────────────────────────────────

INSERT_BHAVCOPY = """
    INSERT OR IGNORE INTO bhavcopy
        (symbol, series, open, high, low, close, last, prevclose,
         volume, value_lakh, del_pct, trade_date, avg_price)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

GET_STOCK_HISTORY = """
    SELECT trade_date, close, high, low, volume, value_lakh, avg_price
    FROM bhavcopy
    WHERE symbol = ? AND trade_date >= ?
    ORDER BY trade_date ASC
"""

GET_STOCK_HISTORY_WINDOWED = """
    SELECT * FROM (
        SELECT trade_date, close, high, low, volume, value_lakh, avg_price
        FROM bhavcopy
        WHERE symbol = ? AND trade_date >= ?
        ORDER BY trade_date DESC
        LIMIT ?
    ) ORDER BY trade_date ASC
"""

GET_ALL_SYMBOLS = """
    SELECT symbol, COUNT(*) as cnt
    FROM bhavcopy
    WHERE trade_date >= ?
    GROUP BY symbol
    HAVING cnt >= ?
    ORDER BY symbol
"""

GET_LATEST_TRADE_DATE = """
    SELECT MAX(trade_date) as dt FROM bhavcopy
"""

GET_DATE_RANGE = """
    SELECT MIN(trade_date) as mn, MAX(trade_date) as mx FROM bhavcopy
"""

GET_TOTAL_RECORDS = """
    SELECT COUNT(*) as cnt FROM bhavcopy
"""

GET_UNIQUE_SYMBOLS = """
    SELECT COUNT(DISTINCT symbol) as cnt FROM bhavcopy WHERE series = ?
"""

# ── Sync Log ────────────────────────────────────────────────────────

INSERT_SYNC_LOG = """
    INSERT OR REPLACE INTO sync_log (trade_date, status, records_count, error_message, synced_at)
    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
"""

GET_LAST_SYNCED_DATE = """
    SELECT trade_date FROM sync_log
    WHERE status = 'success'
    ORDER BY trade_date DESC
    LIMIT 1
"""

GET_SYNC_STATUS = """
    SELECT trade_date, status, records_count, error_message, synced_at
    FROM sync_log
    ORDER BY trade_date DESC
    LIMIT ?
"""

GET_FAILED_SYNCS = """
    SELECT trade_date, error_message
    FROM sync_log
    WHERE status IN ('failed', 'not_available')
    ORDER BY trade_date
"""

GET_HOLIDAY_DATES = """
    SELECT trade_date FROM sync_log
    WHERE status = 'holiday'
    ORDER BY trade_date
"""

# ── Daily Analysis ──────────────────────────────────────────────────

INSERT_ANALYSIS = """
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
"""

GET_LATEST_ANALYSIS = """
    SELECT * FROM daily_analysis
    WHERE analysis_date = ?
    ORDER BY composite_score DESC
"""

GET_LATEST_ANALYSIS_DATE = """
    SELECT MAX(analysis_date) as dt FROM daily_analysis
"""

GET_ANALYSIS_BY_RECOMMENDATION = """
    SELECT * FROM daily_analysis
    WHERE analysis_date = ?
    ORDER BY recommendation, composite_score DESC
"""

# ── Report Cache ────────────────────────────────────────────────────

GET_CACHED_REPORT = """
    SELECT payload FROM report_cache
    WHERE kind = ? AND analysis_date = ? AND version = ?
"""

PUT_CACHED_REPORT = """
    INSERT OR REPLACE INTO report_cache
        (kind, analysis_date, version, payload, built_at)
    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
"""

PRUNE_REPORT_CACHE = """
    DELETE FROM report_cache
    WHERE version <> ?
       OR analysis_date NOT IN (
            SELECT analysis_date FROM report_cache
            WHERE kind = ?
            ORDER BY analysis_date DESC
            LIMIT ?
       )
"""

INVALIDATE_REPORT_CACHE = """
    DELETE FROM report_cache WHERE kind = ?
"""

INVALIDATE_ALL_REPORT_CACHE = """
    DELETE FROM report_cache
"""

# ── Subscribers ─────────────────────────────────────────────────────

INSERT_SUBSCRIBER = """
    INSERT INTO subscribers (chat_id, username, first_name, last_name)
    VALUES (?, ?, ?, ?)
"""

UPDATE_SUBSCRIBER = """
    UPDATE subscribers SET active = 1, receive_reports = 1,
        username = COALESCE(?, username),
        first_name = COALESCE(?, first_name),
        last_name = COALESCE(?, last_name)
    WHERE chat_id = ?
"""

SOFT_DELETE_SUBSCRIBER = """
    UPDATE subscribers SET active = 0, receive_reports = 0
    WHERE chat_id = ? AND active = 1
"""

GET_ACTIVE_SUBSCRIBERS = """
    SELECT chat_id, username, first_name, last_name
    FROM subscribers
    WHERE active = 1 AND receive_reports = 1
"""

GET_ALL_SUBSCRIBERS = """
    SELECT chat_id, username, first_name, last_name, active, receive_reports, subscribed_at
    FROM subscribers
    ORDER BY subscribed_at DESC
"""

GET_SUBSCRIBER_COUNT = """
    SELECT COUNT(*) as cnt FROM subscribers WHERE active = 1
"""

# ── Stats Cache ────────────────────────────────────────────────────

GET_STATS_CACHE = """
    SELECT key, value FROM stats_cache 
    WHERE key IN ('total_records', 'unique_symbols', 'date_from', 'date_to',
                  'active_subscribers', 'symbols_dirty')
"""

SET_STATS_CACHE = """
    INSERT OR REPLACE INTO stats_cache (key, value) VALUES (?, ?)
"""

DELETE_STATS_CACHE_KEY = """
    DELETE FROM stats_cache WHERE key = ?
"""

# ── Intraday ────────────────────────────────────────────────────────

INSERT_INTRADAY_CANDLES = """
    INSERT OR REPLACE INTO intraday_candles
        (symbol, candle_ts, open, high, low, close, volume, vwap)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

GET_INTRADAY_CANDLES = """
    SELECT * FROM intraday_candles
    WHERE symbol = ? AND candle_ts >= ?
    ORDER BY candle_ts ASC
    LIMIT ?
"""

GET_INTRADAY_CANDLES_RECENT = """
    SELECT * FROM intraday_candles
    WHERE symbol = ?
    ORDER BY candle_ts DESC
    LIMIT ?
"""

INSERT_TRACKED_SYMBOL = """
    INSERT OR REPLACE INTO tracked_symbols (symbol, added_by, active)
    VALUES (?, ?, 1)
"""

GET_TRACKED_SYMBOLS = """
    SELECT symbol, added_by, added_at FROM tracked_symbols
    WHERE active = 1
    ORDER BY added_at DESC
"""

REMOVE_TRACKED_SYMBOL = """
    UPDATE tracked_symbols SET active = 0 WHERE symbol = ?
"""

INSERT_INTRADAY_ALERT = """
    INSERT INTO intraday_alerts (symbol, alert_type, candle_ts, price, details)
    VALUES (?, ?, ?, ?, ?)
"""

GET_RECENT_ALERTS = """
    SELECT * FROM intraday_alerts
    WHERE symbol = ? AND candle_ts >= datetime('now', ?)
    ORDER BY candle_ts DESC
"""

GET_RECENT_ALERTS_ALL = """
    SELECT * FROM intraday_alerts
    WHERE candle_ts >= datetime('now', ?)
    ORDER BY candle_ts DESC
    LIMIT 100
"""

PRUNE_INTRADAY_CANDLES = """
    DELETE FROM intraday_candles
    WHERE candle_ts < datetime('now', ?)
"""

PRUNE_INTRADAY_ALERTS = """
    DELETE FROM intraday_alerts
    WHERE created_at < datetime('now', ?)
"""

# ── Maintenance ─────────────────────────────────────────────────────

VACUUM = "VACUUM"

ANALYZE = "ANALYZE"
