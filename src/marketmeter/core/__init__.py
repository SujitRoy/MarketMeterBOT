"""
MarketMeter — cross-cutting infrastructure.

This package owns everything that is not a feature:
- config:        constants & env-driven settings
- logging:       structured logger + rotating file handler
- time:          IST clock + NSE trading calendar
- errors:        typed exception hierarchy (only BhavcopyNotPublished used)

Public surface is re-exported here so callers can
`from marketmeter.core import now_ist, BhavcopyNotPublished`.
"""
from __future__ import annotations

from .errors import BhavcopyNotPublished
from .logging import get_logger, setup
from .time import (
    IST,
    NSE_HOLIDAYS,
    now_ist,
    today_ist,
    to_ist,
    ist_hour_minute,
    parse_ist_time,
    is_trading_day,
    is_nse_holiday,
    is_weekend_or_holiday,
    is_market_open_now,
    trading_days_between,
    get_trading_days,
)
from .config import (
    BASE_DIR,
    DATA_DIR,
    LOG_DIR,
    DB_PATH,
    BOT_TOKEN,
    OWNER_CHAT_ID,
    OWNER_USERNAME,
    OWNER_FIRST_NAME,
    BOT_USERNAME,
    BOT_DISPLAY_NAME,
    TELEGRAM_API_BASE_URL,
    TIMEZONE,
    SYNC_TIME,
    REPORT_TIME,
    PREMARKET_TIME,
    HISTORICAL_START_DATE,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_BACKOFF,
    MAX_RETRY_DATES,
    MIN_PRICE,
    MIN_VOLUME,
    MIN_DATA_POINTS,
    ANALYSIS_BATCH_SIZE,
    ANALYSIS_START_DATE,
    ANALYSIS_WINDOW_DAYS,
    REPORT_TOP_PICKS,
    REPORT_TABLE_ROWS,
    TELEGRAM_MAX_CHARS,
    REPORT_CHUNK_MAX_CHARS,
    RICH_MESSAGE_MAX_CHARS,
    REPORT_CHUNK_DELAY,
    LONG_INDICATOR_MIN_DAYS,
    REPORT_CACHE_VERSION,
    REPORT_CACHE_RETAIN_DAYS,
    NSE_BHAVCOPY_URL,
    NSE_REQUEST_HEADERS,
    NSE_HTTP_TIMEOUT,
    MARKET_CLOSE_HOUR,
    SYNC_RETRY_INTERVAL_MINUTES,
    SYNC_RETRY_UNTIL_HOUR,
    TRADINGVIEW_SESSION_ID,
    MARKET_OPEN_TIME,
    MARKET_CLOSE_TIME,
    INTRADAY_SYMBOLS,
    INTRADAY_INGEST_INTERVAL_MINUTES,
    INTRADAY_ALERT_TIMES,
    LOG_FILE,
    LOG_FORMAT,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
)

__all__ = [
    # config (re-exported from config module)
    "BASE_DIR", "DATA_DIR", "LOG_DIR", "DB_PATH",
    "BOT_TOKEN", "OWNER_CHAT_ID", "OWNER_USERNAME", "OWNER_FIRST_NAME",
    "BOT_USERNAME", "BOT_DISPLAY_NAME", "TELEGRAM_API_BASE_URL",
    "TIMEZONE", "SYNC_TIME", "REPORT_TIME", "PREMARKET_TIME",
    "HISTORICAL_START_DATE", "REQUEST_DELAY", "MAX_RETRIES", "RETRY_BACKOFF",
    "MAX_RETRY_DATES",
    "MIN_PRICE", "MIN_VOLUME", "MIN_DATA_POINTS", "ANALYSIS_BATCH_SIZE",
    "ANALYSIS_START_DATE", "ANALYSIS_WINDOW_DAYS",
    "REPORT_TOP_PICKS", "REPORT_TABLE_ROWS",
    "TELEGRAM_MAX_CHARS", "REPORT_CHUNK_MAX_CHARS", "RICH_MESSAGE_MAX_CHARS",
    "REPORT_CHUNK_DELAY", "LONG_INDICATOR_MIN_DAYS",
    "REPORT_CACHE_VERSION", "REPORT_CACHE_RETAIN_DAYS",
    "NSE_BHAVCOPY_URL", "NSE_REQUEST_HEADERS", "NSE_HTTP_TIMEOUT",
    "MARKET_CLOSE_HOUR", "SYNC_RETRY_INTERVAL_MINUTES", "SYNC_RETRY_UNTIL_HOUR",
    "TRADINGVIEW_SESSION_ID", "MARKET_OPEN_TIME", "MARKET_CLOSE_TIME",
    "INTRADAY_SYMBOLS", "INTRADAY_INGEST_INTERVAL_MINUTES", "INTRADAY_ALERT_TIMES",
    "LOG_FILE", "LOG_FORMAT", "LOG_LEVEL", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT",
    # errors
    "BhavcopyNotPublished",
    # logging
    "get_logger", "setup",
    # time
    "IST", "NSE_HOLIDAYS",
    "now_ist", "today_ist", "to_ist", "ist_hour_minute", "parse_ist_time",
    "is_trading_day", "is_nse_holiday", "is_weekend_or_holiday",
    "is_market_open_now", "trading_days_between", "get_trading_days",
]