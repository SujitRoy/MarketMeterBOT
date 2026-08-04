# MarketMeterBOT — NSE Stock Analysis Telegram Bot

A production-grade Telegram bot that downloads daily NSE BhavCopy data, runs technical analysis on 3,066 tracked symbols (~2,900 with enough history), and delivers curated morning reports with BUY/WATCH/AVOID signals.

> **Current state (verified 2026-08-04):** pipeline live — BhavCopy synced through `2026-08-03`, 2.33 M rows, 5 active subscribers, report cache warm (`v4`).

---

## 🏗 Architecture Overview (v2 Package Structure)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            MarketMeterBOT System v2                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐           │
│  │  NSE Archive    │────▶│ marketmeter.sources│────▶│ marketmeter.db  │           │
│  │  (CSV over HTTPS)│     │  • nse.py       │     │  • bhavcopy     │           │
│  └─────────────────┘     │  • tradingview.py│     │  • daily_analysis│          │
│                          │  • base.py      │     │  • sync_log     │           │
│                          └────────┬────────┘     │  • report_cache │           │
│                                   │              │  • subscribers  │           │
│                                   ▼              │  • stats_cache  │           │
│                          ┌─────────────────┐     │  • intraday_*   │           │
│                          │marketmeter.analysis│────▶│                 │           │
│                          │  • indicators.py │     └────────┬────────┘           │
│                          │  • scoring.py    │              │                    │
│                          │  • analyzer.py   │              ▼                    │
│                          │  • batch.py      │     ┌─────────────────┐           │
│                          └────────┬────────┘     │marketmeter.reports          │
│                                   │              │  • morning.py   │           │
│                                   ▼              │  • cache.py     │           │
│                          ┌─────────────────┐     │  • formatters.py│           │
│                          │marketmeter.scheduler│    │  • premarket_*.py│          │
│                          │  • jobs.py      │     │  • status.py    │           │
│                          │  • sync_cycle.py│     │  • reference.py │           │
│                          └────────┬────────┘     └────────┬────────┘           │
│                                   │                       │                    │
│                                   ▼                       ▼                    │
│                          ┌─────────────────────────────────────────┐           │
│                          │         marketmeter.telegram            │           │
│                          │  • app.py (Application factory)         │           │
│                          │  • delivery.py (broadcast, owner notify)│           │
│                          │  • rich/ (Bot API 10.1+ Rich Messages)  │           │
│                          │  • handlers/ (core, report, search)     │           │
│                          │  • menu.py, search/                     │           │
│                          └─────────────────────────────────────────┘           │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 Codebase Structure

```
MarketMeterBOT/
├── main.py                         # Entry point: bot, CLI (--sync, --backfill, --report, --analyze, --status)
├── config.py                       # Shim → re-exports marketmeter.core.config
├── database.py                     # Shim → re-exports marketmeter.db
├── data_fetcher.py                 # Shim → re-exports marketmeter.sources.nse
├── analyzer.py                     # Shim → re-exports marketmeter.analysis
├── report_generator.py             # Shim → re-exports marketmeter.reports
├── bot.py                          # Shim → re-exports marketmeter.telegram
├── scheduler.py                    # Shim → re-exports marketmeter.scheduler
├── premarket_report.py             # Shim → re-exports marketmeter.reports.premarket_live
├── premarket_open_report.py        # Shim → re-exports marketmeter.reports.premarket_open
├── premarket_combined_report.py    # Shim → re-exports marketmeter.reports.premarket_combined
├── requirements.txt                # Pinned dependencies
├── .env.example                    # Environment variable template
├── data/
│   ├── marketmeter.db              # Main SQLite database (~1.0 GB, 2.33M rows)
│   └── marketmeter.lock            # Single-instance advisory lock
├── logs/
│   └── bot.log                     # Rotating log (5 MB × 3 backups)
├── venv/                           # Python virtual environment
├── tests/                          # Pytest suite
└── src/
    └── marketmeter/                # Main package (Phase 2+ migration target)
        ├── __init__.py
        ├── core/                   # Cross-cutting infrastructure
        │   ├── __init__.py
        │   ├── config.py           # All configuration (env vars, constants, paths, schedules)
        │   ├── logging.py          # Structured logging + rotating file handler
        │   ├── time.py             # IST clock + NSE trading calendar (holidays)
        │   ├── concurrency.py      # Single-instance lock (fcntl.flock)
        │   ├── retry.py            # Generic async retry with exponential backoff
        │   └── errors.py           # Typed exception hierarchy
        ├── db/                     # Persistence layer (8 modules + migrations/)
        │   ├── __init__.py
        │   ├── connection.py       # get_connection() factory (optimized PRAGMAs)
        │   ├── schema.py           # init_db(), init_intraday_tables(), migrations
        │   ├── bhavcopy_repo.py    # bhavcopy CRUD + stats cache updates
        │   ├── analysis_repo.py    # daily_analysis CRUD
        │   ├── sync_repo.py        # sync_log CRUD
        │   ├── cache_repo.py       # report_cache CRUD (WITHOUT ROWID)
        │   ├── subscriber_repo.py  # subscribers CRUD
        │   ├── stats_repo.py       # stats_cache + vacuum_db + get_db_stats()
        │   ├── intraday_repo.py    # intraday_candles/alerts/tracked_symbols CRUD
        │   └── migrations/         # Future home for versioned .sql files
        ├── sources/                # Data providers
        │   ├── __init__.py
        │   ├── base.py             # Provider protocol + canonical schema
        │   ├── nse.py              # NSE BhavCopy download, sync, backfill, retry
        │   └── tradingview.py      # TradingView live snapshots + symbol search
        ├── analysis/               # Technical analysis engine
        │   ├── __init__.py
        │   ├── indicators.py       # SMA, EMA, RSI, MACD, ATR, ADX, BB, OBV
        │   ├── scoring.py          # Composite score + recommendation mapping
        │   ├── analyzer.py         # analyze_stock() per-symbol pipeline
        │   └── batch.py            # run_batch_analysis() + market outlook
        ├── reports/                # Report generation & formatting
        │   ├── __init__.py
        │   ├── morning.py          # 8:30 AM morning report (generate_morning_report)
        │   ├── cache.py            # warm_report_cache() + no-data fallback
        │   ├── formatters.py       # None-safe numeric/string helpers
        │   ├── labels.py           # Signal labels, emoji, narrative text
        │   ├── status.py           # /status, sync status, failure alerts
        │   ├── reference.py        # /indicators, /welcome, /help
        │   ├── premarket_live.py   # 09:00 IST live prices (top 25)
        │   ├── premarket_open.py   # 09:15 IST cross-check (top 15)
        │   └── premarket_combined.py # Combined historical + live pre-market
        ├── scheduler/              # APScheduler jobs
        │   ├── __init__.py
        │   ├── jobs.py             # Job callbacks (daily_sync, daily_report, premarket, crosscheck)
        │   ├── sync_cycle.py       # Sync execution + 15-min retry logic
        │   └── timeparse.py        # IST timezone constants
        ├── telegram/               # Telegram transport layer
        │   ├── __init__.py
        │   ├── app.py              # create_application() handler registration
        │   ├── menu.py             # Menu button (≡) setup
        │   ├── delivery.py         # send_to_owner, broadcast_to_subscribers, send_report_to_all
        │   ├── rich/               # Bot API 10.1+ Rich Message primitives
        │   │   ├── detect.py       # _needs_rich()
        │   │   ├── split.py        # _split_rich_markdown() (table/<details> aware)
        │   │   └── send.py         # _send_rich_message, _send_rich_chunks, _reply
        │   ├── handlers/           # Command handlers
        │   │   ├── __init__.py
        │   │   ├── core.py         # /start /help /status /indicators /subscribe /unsubscribe
        │   │   ├── report.py       # /report [date]
        │   │   └── search.py       # /search + callback query handler
        │   └── search/             # TradingView symbol search
        │       ├── __init__.py
        │       ├── lookup.py       # tv_symbol_lookup()
        │       ├── keyboards.py    # Inline keyboard builders
        │       └── detail.py       # Live stock detail formatting
        └── cli/                    # CLI command implementations
            ├── __init__.py
            ├── cmd_sync.py
            ├── cmd_backfill.py
            ├── cmd_report.py
            ├── cmd_analyze.py
            └── cmd_status.py
```

---

## ⚙️ Configuration (`marketmeter.core.config`)

All secrets from environment variables; constants centralized. Validates required vars at import.

| Variable | Default | Description |
|----------|---------|-------------|
| `MARKETMETER_BOT_TOKEN` | **required** | Bot token from @BotFather |
| `MARKETMETER_OWNER_CHAT_ID` | **required** | Owner's Telegram chat ID (notifications) |
| `MARKETMETER_SYNC_TIME` | `18:30` | Daily sync time (IST) |
| `MARKETMETER_REPORT_TIME` | `08:30` | Daily report time (IST) |
| `MARKETMETER_PREMARKET_TIME` | `09:00` | Pre-market live prices time (IST) |
| `MARKETMETER_LOG_LEVEL` | `INFO` | Logging level |
| `TELEGRAM_API_BASE_URL` | `http://localhost:8082/bot` | Local Bot API server for Rich Messages |

**Key Constants:**
```python
HISTORICAL_START_DATE = "2022-01-01"   # First trading day in DB
MIN_PRICE = 20.0                        # Filter: minimum stock price
MIN_VOLUME = 10_000                     # Filter: minimum daily volume
MIN_DATA_POINTS = 50                    # Minimum history for analysis
ANALYSIS_BATCH_SIZE = 200               # Stocks per batch (memory safety)
ANALYSIS_WINDOW_DAYS = None             # None = full history for exact EMA-200
REPORT_TOP_PICKS = 3                    # Detailed breakdown count
REPORT_TABLE_ROWS = 25                  # Scan table rows
SYNC_RETRY_INTERVAL_MINUTES = 15        # Retry cadence when NSE not published
SYNC_RETRY_UNTIL_HOUR = 23              # Stop retrying at this hour (IST)
MARKET_CLOSE_HOUR = 16                  # Skip today's date before this hour
REPORT_CACHE_VERSION = 4                # Bump to invalidate all cached reports
REPORT_CACHE_RETAIN_DAYS = 7            # Retain last 7 dates per kind
REPORT_CHUNK_MAX_CHARS = 4000           # Chunk size for Rich Message splitting
TELEGRAM_MAX_CHARS = 4096               # Telegram message limit
RICH_MESSAGE_MAX_CHARS = 4096           # Bot API server limit
REPORT_CHUNK_DELAY = 0.15               # Delay between chunk sends
LONG_INDICATOR_MIN_DAYS = 200           # Minimum bars for EMA-200 convergence
```

---

## 🗄 Database Schema (`marketmeter.db.schema`)

### Core Tables

| Table | Rows (approx) | Purpose | Key Indexes |
|-------|---------------|---------|-------------|
| `bhavcopy` | 2,330,000 | Daily OHLCV + avg_price per symbol | `idx_bhavcopy_symbol_date (symbol, trade_date)` — covering index includes `close, high, low, volume, value_lakh, avg_price` |
| `daily_analysis` | 8,200+ | Pre-computed indicators + score per symbol/date | `idx_analysis_date (analysis_date)`, `idx_analysis_rec (analysis_date, recommendation)` |
| `sync_log` | 270 | Per-date sync status | `trade_date` UNIQUE |
| `report_cache` | ~7 | Rendered Rich Markdown payloads | `PRIMARY KEY (kind, analysis_date, version)` — `WITHOUT ROWID` |
| `stats_cache` | 5 | Aggregated counts (avoids COUNT(*)) | `key` PRIMARY KEY |
| `subscribers` | 5 | Telegram chat_ids | `chat_id` PRIMARY KEY |
| `intraday_candles` | (intraday) | 5-minute candles for tracked symbols | `idx_intraday_symbol_ts (symbol, candle_ts)` |
| `intraday_alerts` | (intraday) | Intraday alerts log | `idx_alerts_symbol_ts (symbol, candle_ts)` |
| `tracked_symbols` | (intraday) | Symbols tracked for intraday | `symbol` PRIMARY KEY |

### `bhavcopy` Schema
```sql
CREATE TABLE bhavcopy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    series TEXT DEFAULT 'EQ',
    open REAL, high REAL, low REAL, close REAL, last REAL, prevclose REAL,
    volume INTEGER, value_lakh REAL, del_pct REAL, avg_price REAL,
    trade_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    UNIQUE(symbol, trade_date)
);
```

### `daily_analysis` Schema
```sql
CREATE TABLE daily_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    analysis_date DATE NOT NULL,
    close REAL, volume INTEGER,
    rsi_14 REAL, adx_14 REAL,
    macd_line REAL, signal_line REAL, macd_hist REAL,
    sma_20 REAL, sma_50 REAL, sma_100 REAL, sma_200 REAL,
    ema_20 REAL, ema_50 REAL, ema_100 REAL, ema_200 REAL,
    atr_14 REAL, bb_upper REAL, bb_lower REAL,
    rel_volume REAL, obv_trend REAL, avg_price REAL,
    composite_score INTEGER,
    recommendation TEXT CHECK(recommendation IN (
        'STRONG_BUY','BUY','ACCUMULATE','WATCH','CAUTION','AVOID'
    )),
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    UNIQUE(symbol, analysis_date)
);
```

### `sync_log` Schema
```sql
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE UNIQUE NOT NULL,
    status TEXT CHECK(status IN ('success','failed','holiday','skipped','not_available')),
    records_count INTEGER DEFAULT 0,
    error_message TEXT,
    synced_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
);
```

### `report_cache` Schema (WITHOUT ROWID)
```sql
CREATE TABLE report_cache (
    kind          TEXT NOT NULL,
    analysis_date DATE NOT NULL,
    version       INTEGER NOT NULL,
    payload       TEXT NOT NULL,
    built_at      TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (kind, analysis_date, version)
) WITHOUT ROWID;
```

### Connection Settings (Optimized for 1 GB RAM)
```python
PRAGMA journal_mode = WAL              # Faster, less memory
PRAGMA synchronous = NORMAL            # Balance speed/safety
PRAGMA cache_size = -32768             # 32 MB cache
PRAGMA temp_store = MEMORY             # Temp tables in RAM
PRAGMA mmap_size = 134217728           # 128 MB mmap
PRAGMA page_size = 4096                # Optimal page size
PRAGMA auto_vacuum = INCREMENTAL       # Prevent bloat
PRAGMA secure_delete = OFF             # Faster deletes
PRAGMA foreign_keys = ON
```

---

## 🔄 Complete Database Operations

### 1. BhavCopy Insertion (`marketmeter.db.bhavcopy_repo`)

```python
def insert_bhavcopy_batch(rows: list[dict]) -> int:
    """
    Bulk insert bhavcopy rows using executemany.
    Returns count of inserted rows (O(1) via conn.total_changes).
    """
    # Schema columns in order
    columns = ['symbol', 'series', 'open', 'high', 'low', 'close', 'last',
               'prevclose', 'volume', 'value_lakh', 'del_pct', 'trade_date',
               'avg_price']

    with get_connection() as conn:
        before = conn.total_changes  # O(1) counter
        conn.executemany("""
            INSERT OR IGNORE INTO bhavcopy
                (symbol, series, open, high, low, close, last, prevclose,
                 volume, value_lakh, del_pct, trade_date, avg_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [tuple(r.get(c) for c in columns) for r in rows])
        inserted = conn.total_changes - before
        if inserted:
            update_stats_cache_after_insert(conn, inserted, rows)
        return inserted
```

**Key Points:**
- `INSERT OR IGNORE` prevents duplicates on `UNIQUE(symbol, trade_date)`
- Uses `conn.total_changes` instead of `COUNT(*)` (saves ~47s per sync on 2.3M rows)
- Calls `update_stats_cache_after_insert()` to maintain `stats_cache` arithmetically
- Series resolution: prefers `EQ` → `BE` → other (handled in `transform_bhavcopy`)

### 2. Daily Analysis Insertion (`marketmeter.db.analysis_repo`)

```python
def save_daily_analysis(rows: list[dict]) -> int:
    """
    Bulk insert/update analysis results using executemany.
    Returns count of rows written (INSERT OR REPLACE counts both delete+insert).
    """
    columns = [
        'symbol', 'analysis_date', 'close', 'volume',
        'rsi_14', 'adx_14', 'macd_line', 'signal_line', 'macd_hist',
        'sma_20', 'sma_50', 'sma_100', 'sma_200',
        'ema_20', 'ema_50', 'ema_100', 'ema_200',
        'atr_14', 'bb_upper', 'bb_lower',
        'rel_volume', 'obv_trend', 'avg_price',
        'composite_score', 'recommendation'
    ]

    with get_connection() as conn:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [tuple(r.get(c) for c in columns) for r in rows])
        return conn.total_changes - before
```

**Key Points:**
- `INSERT OR REPLACE` upserts on `UNIQUE(symbol, analysis_date)`
- All 24 indicators + score + recommendation stored
- `conn.total_changes` used for O(1) row count

### 3. Sync Logging (`marketmeter.db.sync_repo`)

```python
def log_sync(trade_date: date, status: str, records: int = 0, error: str = None):
    """Record a sync attempt. Upserts on trade_date."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO sync_log (trade_date, status, records_count, error_message, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (trade_date.isoformat(), status, records, error))
```

**Status Values:**
- `success` — BhavCopy downloaded and inserted
- `failed` — Network/HTTP error
- `holiday` — Weekend or known NSE holiday (from `NSE_HOLIDAYS`)
- `not_available` — Weekday, NSE hasn't published yet (retryable)
- `skipped` — Before market close guard (today < 16:00 IST)

### 4. Report Cache (`marketmeter.db.cache_repo`)

```python
def get_cached_report(kind: str, analysis_date: date) -> Optional[str]:
    """Single PK seek on WITHOUT ROWID table: ~0.08 ms vs ~1.1 s render."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT payload FROM report_cache
            WHERE kind = ? AND analysis_date = ? AND version = ?
        """, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION)).fetchone()
        return row['payload'] if row else None


def put_cached_report(kind: str, analysis_date: date, payload: str) -> None:
    """Store rendered report and prune old versions/dates."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO report_cache
                (kind, analysis_date, version, payload, built_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION, payload))

        # Retention: newest N dates per kind + drop stale versions
        conn.execute("""
            DELETE FROM report_cache
            WHERE version <> ?
               OR analysis_date NOT IN (
                    SELECT analysis_date FROM report_cache
                    WHERE kind = ? ORDER BY analysis_date DESC LIMIT ?
               )
        """, (REPORT_CACHE_VERSION, kind, REPORT_CACHE_RETAIN_DAYS))
```

**Key Points:**
- Keyed by `(kind, analysis_date, REPORT_CACHE_VERSION)` — bump version to invalidate
- `WITHOUT ROWID` makes PK seek a single B-tree lookup (~0.1 ms)
- Retains last 7 dates per kind (`morning`, `premarket`, etc.)
- Auto-prunes on every write

### 5. Stats Cache (`marketmeter.db.stats_repo`)

```python
def update_stats_cache_after_insert(conn, inserted: int, rows: list[dict]) -> None:
    """Update stats cache arithmetically — NO COUNT(*) on 2.3M rows."""
    if not rows:
        return
    dates = [r['trade_date'] for r in rows if r.get('trade_date')]
    if not dates:
        return
    min_date = min(dates)
    max_date = max(dates)

    # Read current cache once
    row = conn.execute("SELECT value FROM stats_cache WHERE key = 'total_records'").fetchone()
    total_records = int(row['value']) if row else 0
    total_records += inserted

    # Update all stats in one transaction
    conn.execute("INSERT OR REPLACE INTO stats_cache (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                 ('total_records', str(total_records)))
    # ... unique_symbols, date_range, etc.
```

**Why Stats Cache?**
- `COUNT(*)` on 2.3M rows = ~23.6 seconds each
- Updated arithmetically on every insert (O(1))
- `get_db_stats()` reads only 5 rows from `stats_cache` → **instant**

### 6. Subscriber Management (`marketmeter.db.subscriber_repo`)

```python
def add_subscriber(chat_id: int, username: str = None,
                   first_name: str = None, last_name: str = None) -> bool:
    """Add or re-activate. Returns True if newly added."""
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
```

**Broadcast Logic (`marketmeter.telegram.delivery.broadcast_to_subscribers`):**
- Iterates `get_active_subscribers()` (only `active=1 AND receive_reports=1`)
- Uses `_send_rich_chunks()` for Rich Message delivery
- On `Forbidden` (user blocked bot): **skips only, does NOT deactivate**
- Rate-limits: 25 messages → 1 second pause

### 7. Migration Strategy (`marketmeter.db.schema`)

```python
_ANALYSIS_ADDED_COLUMNS = {
    "ema_100":   "REAL",
    "ema_200":   "REAL",
    "avg_price": "REAL",
}
_BHAVCOPY_ADDED_COLUMNS = {
    "avg_price": "REAL",
}

def _migrate_analysis_columns():
    """Add missing columns. ALTER TABLE ADD COLUMN is metadata-only (O(1))."""
    with get_connection() as conn:
        for table, wanted in (("daily_analysis", _ANALYSIS_ADDED_COLUMNS),
                              ("bhavcopy", _BHAVCOPY_ADDED_COLUMNS)):
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for col, decl in wanted.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
```

**Sync Log Migration (run once at startup):**
```python
# If old sync_log lacks 'not_available' in CHECK constraint:
ALTER TABLE sync_log RENAME TO sync_log_old;
CREATE TABLE sync_log (...status IN ('success','failed','holiday','skipped','not_available')...);
INSERT INTO sync_log SELECT * FROM sync_log_old;
DROP TABLE sync_log_old;
```

---

## 📊 Data Flow & Scheduling

### Daily Schedule (APScheduler, IST)

| Job | Trigger | Time (IST) | Function | Weekdays |
|-----|---------|------------|----------|----------|
| `daily_sync` | `cron` daily | 18:30 | `_daily_sync_job` | Mon–Fri |
| `daily_report` | `cron` daily | 08:30 | `_daily_report_job` | Mon–Fri |
| `premarket_report` | `cron` daily | 09:00 | `_premarket_report_job` | Mon–Fri |
| `open_crosscheck_report` | `cron` daily | 09:15 | `_open_crosscheck_job` | Mon–Fri |
| `sync_retry` | `interval` 15 min | dynamic | `_sync_retry_job` | when armed |

**Setup (`marketmeter.scheduler.setup_scheduled_jobs`):**
```python
def setup_scheduled_jobs(app: Application):
    jq = app.job_queue
    # Parse SYNC_TIME like "18:30"
    sync_h, sync_m = map(int, SYNC_TIME.split(":"))
    report_h, report_m = map(int, REPORT_TIME.split(":"))
    premarket_h, premarket_m = map(int, PREMARKET_TIME.split(":"))

    jq.run_daily(_daily_sync_job, time=time(sync_h, sync_m, tzinfo=IST),
                 name="daily_sync", days=MON_FRI)
    jq.run_daily(_daily_report_job, time=time(report_h, report_m, tzinfo=IST),
                 name="daily_report", days=MON_FRI)
    jq.run_daily(_premarket_report_job, time=time(premarket_h, premarket_m, tzinfo=IST),
                 name="premarket_report", days=MON_FRI)
    jq.run_daily(_open_crosscheck_job, time=time(9, 15, tzinfo=IST),
                 name="open_crosscheck_report", days=MON_FRI)
```

### 18:30 Sync Flow (`_daily_sync_job` → `_run_sync_cycle`)

```
18:30 IST ──▶ _daily_sync_job(context)
                │
                ▼
        _run_sync_cycle(app, is_retry=False)
                │
                ▼
    sync_incremental_data()  ──▶ marketmeter.sources.nse
                │
                ├── find missing dates since last 'success'
                ├── retry last 5 'failed'/'not_available' dates
                ├── skip today if before 16:00 (market not closed)
                ├── for each date:
                │     download CSV (150 ms avg)
                │     transform → insert_bhavcopy_batch()
                │     log_sync(status, records)
                │
                ├── if total_records > 0:
                │     confirm_bhavcopy_insertion(app, result)  # owner receipt
                │     run_batch_analysis()                     # technical analysis
                │     warm_report_cache()                      # pre-render report
                │
                └── if not_available dates remain:
                      _schedule_sync_retry(context)           # arm 15-min retry
                      notify owner: pending dates + retry info
```

### 15-Minute Retry Loop (`_sync_retry_job` → `_schedule_sync_retry`)

```
Every 15 min (armed) ──▶ _sync_retry_job(context)
                           │
                           ▼
                   _run_sync_cycle(app, is_retry=True)
                           │
                           ├── if records landed BUT not_available still non-empty:
                           │     KEEP RETRY LOOP ALIVE (Bug #3 fix)
                           │     _schedule_sync_retry(context)  # re-arm
                           │
                           ├── if not_available empty:
                           │     success → owner notified, loop stops
                           │
                           └── if cutoff hour (23:00 IST) reached:
                                 give up for today
                                 notify owner: "pending dates, next try at 18:30"
```

**IST-Aware Cutoff (`marketmeter.scheduler.timeparse.IST`):**
```python
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")

# In _schedule_sync_retry:
if datetime.now(IST).hour >= SYNC_RETRY_UNTIL_HOUR:  # 23
    return False  # Stop retrying today
```

### 08:30 Morning Report (`_daily_report_job` → `send_report_to_all`)

```
08:30 IST ──▶ _daily_report_job(context)
                │
                ▼
        send_report_to_all(app)
                │
                ├── get_resolved_analysis_date()  # latest date with analysis
                ├── generate_morning_report(date)  # cache hit: 0.1 ms
                ├── broadcast_to_subscribers(app, report)  # Rich chunks
                └── notify owner: sent/failed counts
```

### 09:00 Pre-Market Live (`_premarket_report_job`)

```
09:00 IST ──▶ _premarket_report_job(context)
                │
                ▼
        send_premarket_report(app)
                │
                ├── get_resolved_analysis_date()
                ├── get top 25 by composite_score
                ├── fetch live prices (TradingView)
                ├── build_premarket_message()
                └── send to OWNER only
```

### 09:15 Market-Open Cross-Check (`_open_crosscheck_job`)

```
09:15 IST ──▶ _open_crosscheck_job(context)
                │
                ▼
        send_open_crosscheck_report(app)
                │
                ├── get top 15 by composite_score (EOD analysis)
                ├── fetch live 09:15 prices (TradingView)
                ├── merge EOD + live: gap%, live RSI/Vol, verdict
                ├── build_open_crosscheck()
                └── send to OWNER only
```

---

## 🔑 Key Functions Reference (New Package Paths)

### Database (`marketmeter.db`)
| Function | Module | Purpose |
|----------|--------|---------|
| `get_connection()` | `connection` | Optimized SQLite connection factory |
| `init_db()` | `schema` | Bootstrap all tables, indexes, migrations |
| `insert_bhavcopy_batch(rows)` | `bhavcopy_repo` | Bulk insert BhavCopy (O(1) counter) |
| `get_stock_history(symbol, min_days, window)` | `bhavcopy_repo` | OHLCV for analysis (covering index) |
| `get_all_symbols(min_records)` | `bhavcopy_repo` | Symbols with sufficient history |
| `log_sync(date, status, records, error)` | `sync_repo` | Upsert sync_log |
| `save_daily_analysis(rows)` | `analysis_repo` | Bulk upsert analysis results |
| `get_latest_analysis(date?)` | `analysis_repo` | All analysis for a date |
| `get_resolved_analysis_date()` | `analysis_repo` | Latest date with analysis (never `date.today()`) |
| `get_cached_report(kind, date)` | `cache_repo` | Report cache lookup (0.1 ms) |
| `put_cached_report(kind, date, payload)` | `cache_repo` | Store + prune report cache |
| `add_subscriber(...)` | `subscriber_repo` | Upsert subscriber |
| `get_active_subscribers()` | `subscriber_repo` | Broadcast target list |
| `get_db_stats()` | `stats_repo` | Cached stats (no COUNT(*)) |
| `init_stats_cache()` | `stats_repo` | One-time cold cache build |
| `vacuum_db()` | `stats_repo` | Reclaim space |

### NSE Sync (`marketmeter.sources.nse`)
| Function | Purpose |
|----------|---------|
| `fetch_bhavcopy_csv(date, session)` | Download CSV; raises `BhavcopyNotPublished` on 404 |
| `transform_bhavcopy(df, date)` | Map NSE columns → schema; keeps `AVG_PRICE` |
| `download_bhavcopy_for_date(date, session)` | Retries with exponential backoff |
| `download_and_store_date(date, session)` | Download → transform → insert → log_sync |
| `sync_incremental_data()` | **Main entry**: missing dates + failed retry → download → store → analysis trigger |
| `backfill_historical_data(start, end)` | Full historical load (1100+ trading days) |
| `classify_sync_status(date, message)` | 'holiday' / 'not_available' / 'failed' |

### Analysis (`marketmeter.analysis`)
| Function | Purpose |
|----------|---------|
| `calc_sma/ema/rsi/macd/atr/adx/bollinger/obv` | `indicators.py` — pure pandas/numpy |
| `_get_recommendation(score, rsi, adx)` | `scoring.py` — BUY/WATCH/AVOID mapping |
| `analyze_stock(df, symbol)` | `analyzer.py` — per-symbol pipeline |
| `run_batch_analysis(date?)` | `batch.py` — all 2,959 symbols in batches of 200 |
| `get_market_outlook(date?)` | `batch.py` — aggregate bullish/bearish/neutral % |
| `get_analysis_aggregate(date?)` | `batch.py` — detailed category breakdown |

### Reports (`marketmeter.reports`)
| Function | Module | Purpose |
|----------|--------|---------|
| `generate_morning_report(date)` | `morning.py` | 8:30 AM report (cache-aware) |
| `warm_report_cache(date?)` | `cache.py` | Pre-render morning report |
| `build_premarket_message(date)` | `premarket_live.py` | 09:00 live prices |
| `send_premarket_report(app)` | `premarket_live.py` | Owner-only pre-market |
| `build_open_crosscheck(date)` | `premarket_open.py` | 09:15 EOD + live merge |
| `send_open_crosscheck_report(app)` | `premarket_open.py` | Owner-only cross-check |
| `merge_historical_live(...)` | `premarket_combined.py` | Combined report merge |
| `generate_sync_status_message(result)` | `status.py` | Sync result formatting |
| `generate_status_message()` | `status.py` | `/status` command output |
| `generate_indicators_message()` | `reference.py` | `/indicators` glossary |
| `generate_welcome_message(name)` | `reference.py` | `/start` welcome |
| `generate_help_message()` | `reference.py` | `/help` command list |

### Telegram (`marketmeter.telegram`)
| Function | Module | Purpose |
|----------|--------|---------|
| `create_application()` | `app.py` | Bot factory + handler registration |
| `send_to_owner(app, msg, use_rich)` | `delivery.py` | Owner notification (Rich/Markdown) |
| `broadcast_to_subscribers(app, msg)` | `delivery.py` | Broadcast to all active subscribers |
| `send_report_to_all(app)` | `delivery.py` | 08:30 broadcast entry point |
| `_send_rich_chunks(bot, chat_id, md)` | `rich.send` | Split + send Rich Message chunks |
| `_split_rich_markdown(text, max)` | `rich.split` | Table/<details>-aware chunking |
| `_needs_rich(text)` | `rich.detect` | Detect Rich-only syntax |
| `tv_symbol_lookup(query)` | `search.lookup` | TradingView symbol search |

### Scheduler (`marketmeter.scheduler`)
| Function | Module | Purpose |
|----------|--------|---------|
| `setup_scheduled_jobs(app)` | `__init__.py` | Register all APScheduler jobs |
| `_daily_sync_job(context)` | `jobs.py` | 18:30 sync entry |
| `_daily_report_job(context)` | `jobs.py` | 08:30 report entry |
| `_premarket_report_job(context)` | `jobs.py` | 09:00 pre-market entry |
| `_open_crosscheck_job(context)` | `jobs.py` | 09:15 cross-check entry |
| `_run_sync_cycle(app, is_retry)` | `sync_cycle.py` | Shared sync execution |
| `_schedule_sync_retry(context)` | `sync_cycle.py` | Arm 15-min retry (IST-aware) |
| `_sync_retry_job(context)` | `sync_cycle.py` | Retry execution + re-arm logic |
| `confirm_bhavcopy_insertion(app, result)` | `sync_cycle.py` | Owner receipt for net-new records |

---

## 📈 Query Performance (Measured on 2.33M rows)

| Query | Index Used | Time |
|-------|------------|------|
| `get_stock_history` (full) | `idx_bhavcopy_symbol_date` (real) | 68 ms |
| `get_stock_history` (260-day window) | `idx_bhavcopy_symbol_date` + LIMIT | 1.3 ms |
| `get_latest_analysis` | `idx_analysis_date` | 300 ms |
| `report_cache` lookup | PK `(kind, date, version)` | 0.1 ms |
| `stats_cache` lookup | PK `key` | 0.2 ms |
| `get_all_symbols` (GROUP BY) | `idx_bhavcopy_symbol_date` | 4.2 s (cached after first run) |

**Optimization Notes:**
- **Covering-index decision:** `idx_bhavcopy_cover (symbol, trade_date, close, high, low, volume, value_lakh, avg_price)` would speed analyzer ~1.7-1.9x but costs ~153 MB extra disk (15%) + one-time ~85s CREATE on 1 GB table. Analyzer path is **not** a nightly bottleneck (report is cache-served at ~1 ms), so index is **deliberately NOT created** on this 954 MB host. See `schema.py` comment.
- `stats_cache` avoids `COUNT(*)` on 2.3M rows (23.6 s each). Updated arithmetically on insert.
- `report_cache` turns 1.1 s render into 0.1 ms read.
- `ANALYSIS_WINDOW_DAYS = None` ensures EMA-200 converges exactly (tested: 17% error with 260-row window).

---

## 🚀 Deployment (systemd)

**Service File**: `~/.config/systemd/user/marketmeter.service`
```ini
[Unit]
Description=MarketMeterBOT - NSE Stock Analysis Telegram Bot
After=network.target

[Service]
Type=exec
WorkingDirectory=/home/ubuntu/MarketMeterBOT
EnvironmentFile=/home/ubuntu/.config/marketmeter/env
Environment=MARKETMETER_SYNC_TIME=18:30
Environment=MARKETMETER_REPORT_TIME=08:30
Environment=MARKETMETER_PREMARKET_TIME=09:00
Environment=MARKETMETER_LOG_LEVEL=INFO
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONNOUSERSITE=1
ExecStart=/home/ubuntu/MarketMeterBOT/venv/bin/python3 -u main.py
ExecStop=/bin/kill -SIGINT $MAINPID
Restart=on-failure
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=30
MemoryHigh=280M
MemoryMax=380M
CPUQuota=60%
StandardOutput=null
StandardError=journal
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths=/home/ubuntu/MarketMeterBOT/data /home/ubuntu/MarketMeterBOT/logs

[Install]
WantedBy=default.target
```

**Commands:**
```bash
systemctl --user daemon-reload
systemctl --user enable --now marketmeter.service
systemctl --user status marketmeter.service
journalctl --user -u marketmeter.service -f
```

**Local Bot API Server** (for Rich Messages):
```bash
docker run -d --name telegram-bot-api \
  -p 8082:8081 \
  -e TELEGRAM_API_ID=<api_id> \
  -e TELEGRAM_API_HASH=<api_hash> \
  -v /home/ubuntu/telegram-bot-api:/var/lib/telegram-bot-api \
  aiogram/telegram-bot-api:latest
```

---

## 🧪 Testing / Manual Commands

```bash
cd /home/ubuntu/MarketMeterBOT

# One-shot sync (run at 18:30)
venv/bin/python3 main.py --sync

# Full backfill (run once)
venv/bin/python3 main.py --backfill

# Generate report to stdout
venv/bin/python3 main.py --report

# Run analysis only
venv/bin/python3 main.py --analyze

# Database stats
venv/bin/python3 main.py --status

# View logs
tail -f logs/bot.log

# Run pytest suite
venv/bin/pytest tests/ -v
```

---

## 📊 Data Flow Summary (Complete)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 18:30 IST ──▶ sync_incremental_data()                                      │
│                  ├─ find missing dates since last 'success'                │
│                  ├─ retry last 5 'failed'/'not_available' dates            │
│                  ├─ skip today if before 16:00 (market not closed)         │
│                  ├─ for each date:                                         │
│                  │     download CSV from nsearchives.nseindia.com          │
│                  │     transform: NSE cols → schema (keeps AVG_PRICE)     │
│                  │     insert_bhavcopy_batch() → conn.total_changes        │
│                  │     log_sync(status, records)                           │
│                  │     update_stats_cache_after_insert()                  │
│                  │                                                         │
│                  ├─ if total_records > 0:                                  │
│                  │     confirm_bhavcopy_insertion(app, result)  # owner   │
│                  │     run_batch_analysis()  ──▶ save_daily_analysis()    │
│                  │     warm_report_cache()  ──▶ put_cached_report()       │
│                  │                                                         │
│                  └─ if not_available dates remain:                         │
│                        _schedule_sync_retry()  # 15-min interval until 23:00│
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 08:30 IST ──▶ send_report_to_all()                                         │
│                  ├─ get_resolved_analysis_date()  # latest with analysis   │
│                  ├─ generate_morning_report(date)                          │
│                  │     ├─ cache hit? → get_cached_report() (0.1 ms)        │
│                  │     └─ miss → _render_morning_report() (1.1 s)         │
│                  ├─ broadcast_to_subscribers()                             │
│                  │     ├─ get_active_subscribers()                         │
│                  │     ├─ _send_rich_chunks() per subscriber              │
│                  │     └─ rate-limit: 25 msg → 1 sec pause                │
│                  └─ notify owner: sent/failed counts                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 09:00 IST ──▶ send_premarket_report() (owner only)                         │
│                  ├─ top 25 by composite_score                              │
│                  ├─ fetch live prices (TradingView)                        │
│                  ├─ build_premarket_message()                              │
│                  └─ _send_rich_chunks() to owner                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 09:15 IST ──▶ send_open_crosscheck_report() (owner only)                   │
│                  ├─ top 15 by composite_score (EOD analysis)              │
│                  ├─ fetch live 09:15 prices (TradingView)                 │
│                  ├─ merge: gap%, live RSI/Vol, verdict                    │
│                  ├─ build_open_crosscheck()                                │
│                  └─ _send_rich_chunks() to owner                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Security & Hygiene

- **No secrets in code**: All tokens/IDs via `EnvironmentFile` (0600).
- **Single-instance lock**: `fcntl.flock` on `data/marketmeter.lock` prevents concurrent DB writers.
- **Input validation**: NSE CSV columns validated; `INSERT OR IGNORE` prevents duplicates.
- **SQL injection**: All queries parameterized (`?` placeholders).
- **PII**: No user data logged; only `chat_id` (integer) stored.
- **Logging**: Rotating file handler (5 MB × 3), no stdout duplication.
- **Memory limits**: systemd `MemoryHigh`/`MemoryMax` prevent OOM.
- **Correlation IDs**: Logger filter attaches `correlation_id` for future tracing.

---

## 📦 Dependencies (`requirements.txt`)

```txt
pandas>=2.2,<3.0
numpy>=1.26,<3.0
python-telegram-bot[job-queue]>=21.0,<22.0
requests>=2.31.0
```

Pinned to tested major versions. `python-telegram-bot[job-queue]` pulls APScheduler.

---

## 🛠 Extending / Customizing (New Package Paths)

| Change | Files to Edit |
|--------|---------------|
| Add indicator | `marketmeter/analysis/indicators.py` + `scoring.py` |
| Change scoring | `marketmeter/analysis/scoring.py` |
| Modify report layout | `marketmeter/reports/morning.py` / `formatters.py` |
| Add command | `marketmeter/telegram/handlers/` (core/report/search) + `app.py` |
| Change schedule | `marketmeter/core/config.py` + systemd `Environment=` |
| Add DB column | `marketmeter/db/schema.py` (`_ANALYSIS_ADDED_COLUMNS`/`_BHAVCOPY_ADDED_COLUMNS`) |
| Change NSE source | `marketmeter/sources/nse.py` |
| Modify 09:00 pre-market | `marketmeter/reports/premarket_live.py` |
| Modify 09:15 cross-check | `marketmeter/reports/premarket_open.py` |
| Modify combined pre-market | `marketmeter/reports/premarket_combined.py` |
| Add data provider | `marketmeter/sources/` (new file + `base.py` protocol) |
| Add intraday feature | `marketmeter/db/intraday_repo.py` + `schema.py` |

---

## 📝 Migration Status (Phase 1–6)

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Core infrastructure: `config`, `logging`, `time`, `concurrency`, `retry`, `errors` |
| 2 | ✅ Done | Database layer split: 8 repo modules + `connection`, `schema`, `migrations` |
| 3 | ✅ Done | Sources: `nse.py`, `tradingview.py`, `base.py` (Provider protocol) |
| 4 | ✅ Done | Analysis + Reports packages: 5 analysis modules, 9 report modules |
| 5 | ✅ Done | Telegram layer: `app`, `delivery`, `rich`, `handlers`, `search`, `menu` |
| 6 | ✅ Done | Scheduler: `jobs`, `sync_cycle`, `timeparse`; CLI package |
| **Shim Retirement** | **Pending** | Root shims (`config.py`, `database.py`, `data_fetcher.py`, `analyzer.py`, `report_generator.py`, `bot.py`, `scheduler.py`, `premarket_*.py`) still re-export for back-compat. Remove after verification. |

---

## 📝 License

MIT — see `LICENSE` (add if needed).

---

## 👤 Author

**Sujit Roy** (@notorious_thug)  
Repository: https://github.com/SujitRoy/MarketMeterBOT.git