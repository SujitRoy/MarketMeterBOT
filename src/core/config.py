"""
MarketMeter Configuration
All secrets from environment variables, constants centralized here.
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "marketmeter.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Telegram ───────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("MARKETMETER_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("MARKETMETER_BOT_TOKEN environment variable is required")

OWNER_CHAT_ID = os.getenv("MARKETMETER_OWNER_CHAT_ID")
if not OWNER_CHAT_ID:
    raise RuntimeError("MARKETMETER_OWNER_CHAT_ID environment variable is required")
OWNER_CHAT_ID = int(OWNER_CHAT_ID)

OWNER_USERNAME = "@notorious_thug"
OWNER_FIRST_NAME = "Sujit"
BOT_USERNAME = "MarketMeterBOT"
BOT_DISPLAY_NAME = "MarketMeter"

# Local Bot API server for Rich Messages (Bot API 10.1+)
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "http://localhost:8082/bot")

# ── Scheduling (IST) ──────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"
SYNC_TIME = os.getenv("MARKETMETER_SYNC_TIME", "18:30")      # 6:30 PM IST
REPORT_TIME = os.getenv("MARKETMETER_REPORT_TIME", "08:30")   # 8:30 AM IST
PREMARKET_TIME = os.getenv("MARKETMETER_PREMARKET_TIME", "09:00")  # 9:00 AM IST (pre-market live prices)

# ── Data Fetching ──────────────────────────────────────────────────
# First trading day of the reporting window (NSE opened 2022-01-03).
HISTORICAL_START_DATE = "2022-01-01"
REQUEST_DELAY = 0.15                # seconds between NSE requests
MAX_RETRIES = 3
RETRY_BACKOFF = 2                   # exponential backoff multiplier
MAX_RETRY_DATES = 5                 # max failed dates to retry per sync run

# ── Analysis ───────────────────────────────────────────────────────
MIN_PRICE = 20.0                    # minimum stock price filter
MIN_VOLUME = 10_000                 # minimum daily volume filter
MIN_DATA_POINTS = 50                # minimum trading days for analysis
ANALYSIS_BATCH_SIZE = 200           # stocks per batch for memory safety

# Reporting window floor. All analysis/report queries are bounded by this.
ANALYSIS_START_DATE = "2022-01-01"

# Rows fetched per symbol. None = full stored history (accuracy mode).
#
# A fixed window is faster but leaves EMA unconverged. EMA is recursive with no
# fixed lookback, so seeding EMA-200 from only 260 rows measured 17.28% off on
# COFORGE (1471.69 vs true 1779.08). SMA is a true rolling window and was exact
# at 260 either way. Accuracy takes priority, so no window is applied.
ANALYSIS_WINDOW_DAYS = None

# ── Report ─────────────────────────────────────────────────────────
# Curated shape: N fully broken-down picks, then a lean scan table. Replaces
# the old dump of six category tables (~1707 rows truncated behind "N more").
REPORT_TOP_PICKS = 3
REPORT_TABLE_ROWS = 25

# Rich Messages cap at 32,768 UTF-8 chars total; a single Telegram text message
# caps at 4,096. 25 scan rows plus 3 detail blocks lands ~5.5KB, so the report
# is split into multiple rich chunks by _split_rich_markdown.

# Minimum trading days before the 200-period indicators are meaningful. Symbols
# below this still appear in the report, with "-" for what cannot be computed.
LONG_INDICATOR_MIN_DAYS = 200

# ── Composite Scorer Weights ──────────────────────────────────────
# Weights for composite score components (must sum to 1.0)
SCORE_WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.25,
    "volatility": 0.15,
    "volume": 0.20,
    "structure": 0.15,
}

# Recommendation thresholds
REC_THRESHOLDS = {
    "STRONG_BUY": 80,
    "BUY": 65,
    "ACCUMULATE": 50,
    "WATCH": 35,
    "CAUTION": 20,
    # Below 20 = AVOID
}

# ── Report Cache ────────────────────────────────────────────────────
# Bump REPORT_CACHE_VERSION whenever report layout changes, to invalidate
# every previously rendered payload without touching the table.
REPORT_CACHE_VERSION = 4
REPORT_CACHE_RETAIN_DAYS = 7

# ── Message Chunking ──────────────────────────────────────────────
# Telegram hard-caps a text message at 4096 UTF-8 chars (cloud AND local Bot
# API server). Stay under it with headroom so a chunk can never be rejected.
TELEGRAM_MAX_CHARS = 4096
REPORT_CHUNK_MAX_CHARS = 3800

# Rich Message total-payload ceiling (Bot API 10.1+). Distinct from the 4096
# per-message text cap: a single sendRichMessage body cannot exceed this.
RICH_MESSAGE_MAX_CHARS = 32_768

# Delay between chunks sent to the same chat. Telegram throttles bursts to
# roughly 1 message/second per chat; 1.0s keeps us inside that without
# stretching a multi-part report out needlessly.
REPORT_CHUNK_DELAY = 1.0

# ── NSE Source ───────────────────────────────────────────────────
# Official NSE archive. This is the same URL nsefin 0.1.5 requests internally;
# we call it directly to keep the AVG_PRICE column nsefin drops and to tell a
# 404 (not published yet) apart from a real transport error.
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

# NSE publishes the day's BhavCopy after the 15:30 IST close. Attempting the
# current date before this only ever yields a 404 that gets logged as a failed
# sync: on 2026-07-29 a 09:21 run marked the date not_available and no retry
# followed. Today's date is skipped until this hour.
# NOTE: closed-day classification lives in data_fetcher.NSE_HOLIDAYS / is_trading_day,
# so a weekday exchange holiday is 'holiday' (skipped), never a retryable 'failed'.
MARKET_CLOSE_HOUR = 16

# ── Sync Retry ─────────────────────────────────────────────────
# When the 18:30 sync finds NSE has not published, re-attempt on this interval
# instead of waiting a full day for the next scheduled run.
SYNC_RETRY_INTERVAL_MINUTES = 15

# Stop re-attempting at this hour (IST). NSE normally publishes by ~19:00-20:00;
# past this the file is not coming today, so the next 18:30 run picks it up.
# Also keeps retries clear of the 09:00-10:30 cron window.
SYNC_RETRY_UNTIL_HOUR = 23

# ── Intraday (TradingView) ────────────────────────────────────────
# TradingView session cookie for real-time data (free tier requires auth)
TRADINGVIEW_SESSION_ID = os.getenv("TRADINGVIEW_SESSION_ID", "")

# Market hours (IST)
MARKET_OPEN_TIME = "09:15"
MARKET_CLOSE_TIME = "15:30"

# Symbols to track intraday (auto-populated from morning report top picks)
# Can be overridden by adding more via /track command
INTRADAY_SYMBOLS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "BHARTIARTL",
    "TCS", "INFY", "ITC", "SBIN", "LT", "AXISBANK",
    "KOTAKBANK", "BAJFINANCE", "HINDUNILVR", "ASIANPAINT",
    "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO",
]

# Backward compatibility alias
DEFAULT_INTRADAY_SYMBOLS = INTRADAY_SYMBOLS

# Intraday ingest interval (minutes) — runs at :05, :10, :15 past each hour
INTRADAY_INGEST_INTERVAL_MINUTES = 5

# Intraday alert check times (IST)
INTRADAY_ALERT_TIMES = ["11:00", "13:00", "15:00"]

# ── Logging ─────────────────────────────────────────────────────────
LOG_FILE = LOG_DIR / "bot.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_LEVEL = os.getenv("MARKETMETER_LOG_LEVEL", "INFO")
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3  # Keep 3 rotated files
