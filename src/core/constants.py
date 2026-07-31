"""
MarketMeter Constants
All magic values, enums, and shared constants centralized here.
"""
from datetime import time
from enum import Enum


class Recommendation(str, Enum):
    """Stock recommendation categories."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    ACCUMULATE = "ACCUMULATE"
    WATCH = "WATCH"
    CAUTION = "CAUTION"
    AVOID = "AVOID"

    @property
    def is_bullish(self) -> bool:
        return self in (Recommendation.STRONG_BUY, Recommendation.BUY, Recommendation.ACCUMULATE)

    @property
    def emoji(self) -> str:
        return {
            Recommendation.STRONG_BUY: "🟢🟢",
            Recommendation.BUY: "🟢",
            Recommendation.ACCUMULATE: "🟡",
            Recommendation.WATCH: "🔵",
            Recommendation.CAUTION: "🟠",
            Recommendation.AVOID: "🔴",
        }[self]


class SyncStatus(str, Enum):
    """Sync operation statuses."""
    SUCCESS = "success"
    FAILED = "failed"
    HOLIDAY = "holiday"
    SKIPPED = "skipped"
    NOT_AVAILABLE = "not_available"


class ReportKind(str, Enum):
    """Types of reports."""
    MORNING = "morning"
    PREMARKET = "premarket"
    OPEN_CROSSCHECK = "open_crosscheck"
    COMBINED_PREMAKET = "combined_premarket"
    TECHNICAL = "technical"
    SECTOR = "sector"
    SCANNER = "scanner"
    BACKTEST = "backtest"
    CUSTOM = "custom"


# Market hours (IST)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PRE_MARKET_START = time(9, 0)

# NSE Series
NSE_EQ_SERIES = "EQ"

# Default analysis parameters
DEFAULT_RSI_PERIOD = 14
DEFAULT_ADX_PERIOD = 14
DEFAULT_ATR_PERIOD = 14
DEFAULT_BB_PERIOD = 20
DEFAULT_BB_STD = 2
DEFAULT_MACD_FAST = 12
DEFAULT_MACD_SLOW = 26
DEFAULT_MACD_SIGNAL = 9

# Moving average periods
SMA_PERIODS = [20, 50, 100, 200]
EMA_PERIODS = [20, 50, 100, 200]

# Composite score weights (must sum to 1.0)
SCORE_WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.25,
    "volatility": 0.15,
    "volume": 0.20,
    "structure": 0.15,
}

# Recommendation thresholds
REC_THRESHOLDS = {
    Recommendation.STRONG_BUY: 80,
    Recommendation.BUY: 65,
    Recommendation.ACCUMULATE: 50,
    Recommendation.WATCH: 35,
    Recommendation.CAUTION: 20,
    # Below 20 = AVOID
}

# Minimum data requirements
MIN_PRICE = 20.0
MIN_VOLUME = 10_000
MIN_DATA_POINTS = 50
LONG_INDICATOR_MIN_DAYS = 200

# Report settings
REPORT_TOP_PICKS = 3
REPORT_TABLE_ROWS = 25
REPORT_CACHE_VERSION = 4
REPORT_CACHE_RETAIN_DAYS = 7

# Telegram limits
TELEGRAM_MAX_CHARS = 4096
REPORT_CHUNK_MAX_CHARS = 3800
RICH_MESSAGE_MAX_CHARS = 32_768
REPORT_CHUNK_DELAY = 1.0

# NSE
NSE_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/products/content/"
    "sec_bhavdata_full_{date_str}.csv"
)
NSE_REQUEST_HEADERS = {
    "Accept": "*/*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Connection": "keep-alive",
}
NSE_HTTP_TIMEOUT = 30
MARKET_CLOSE_HOUR = 16

# Sync
SYNC_RETRY_INTERVAL_MINUTES = 15
SYNC_RETRY_UNTIL_HOUR = 23
REQUEST_DELAY = 0.15
MAX_RETRIES = 3
RETRY_BACKOFF = 2
MAX_RETRY_DATES = 5

# Intraday
INTRADAY_INGEST_INTERVAL_MINUTES = 5
INTRADAY_ALERT_TIMES = ["11:00", "13:00", "15:00"]
DEFAULT_INTRADAY_SYMBOLS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "BHARTIARTL",
    "TCS", "INFY", "ITC", "SBIN", "LT", "AXISBANK",
    "KOTAKBANK", "BAJFINANCE", "HINDUNILVR", "ASIANPAINT",
    "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO",
]

# Timezone
TIMEZONE = "Asia/Kolkata"

# Logging
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

# Database pragmas (memory-optimized for 1GB RAM)
DB_PRAGMAS = {
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    "cache_size": -32768,       # 32MB cache
    "temp_store": "MEMORY",
    "mmap_size": 134217728,     # 128MB
    "page_size": 4096,
    "auto_vacuum": "INCREMENTAL",
    "secure_delete": "OFF",
    "foreign_keys": "ON",
}
