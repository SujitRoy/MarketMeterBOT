# MarketMeterBOT — NSE Stock Analysis Telegram Bot

A production-grade Telegram bot that downloads daily NSE BhavCopy data, runs technical analysis on 2,900+ stocks, and delivers curated morning reports with BUY/WATCH/AVOID signals.

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MarketMeterBOT System                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────┐  │
│  │ NSE Archive │───▶│ data_fetcher│───▶│  SQLite DB  │◀───│analyzer │  │
│  │ (CSV over   │    │ (sync,      │    │  (2.3M rows │    │(indic,  │  │
│  │  HTTPS)     │    │  retry,     │    │   3K syms)  │    │ score)  │  │
│  └─────────────┘    │  backfill)  │    └──────┬──────┘    └────┬────┘  │
│                     └─────────────┘           │              │       │
│                                                ▼              ▼       │
│                     ┌──────────────────────────────────────────────┐  │
│                     │           report_generator                    │  │
│                     │  (Rich Markdown tables, <details>, cache)    │  │
│                     └──────────────────────────┬───────────────────┘  │
│                                                ▼                       │
│                     ┌──────────────────────────────────────────────┐  │
│                     │              bot.py (python-telegram-bot)    │  │
│                     │  /start /subscribe /report /status /indicators│  │
│                     └──────────────────────────┬───────────────────┘  │
│                                                ▼                       │
│                     ┌──────────────────────────────────────────────┐  │
│                     │           scheduler.py (APScheduler)         │  │
│                     │  18:30 IST sync  •  08:30 IST report         │  │
│                     │  15-min retry until NSE publishes (until 23:00)│  │
│                     └──────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 Codebase Structure

```
MarketMeterBOT/
├── main.py              # Entry point: bot, CLI commands (--sync, --backfill, --report, --analyze, --status)
├── config.py            # All configuration (env vars, constants, paths, schedules)
├── database.py          # SQLite layer: schema, CRUD, indexes, migrations, caching
├── data_fetcher.py      # NSE BhavCopy download, transform, incremental sync, retry logic
├── analyzer.py          # Technical indicators (RSI, ADX, MACD, SMA/EMA, ATR, BB, OBV), scoring, recommendations
├── report_generator.py  # Rich Markdown reports: top picks, scan table, collapsible legends, cache
├── bot.py               # Telegram handlers, Rich Message delivery (Bot API 10.1+), broadcasting
├── scheduler.py         # APScheduler jobs: daily sync, daily report, retry loop
├── requirements.txt     # Pinned dependencies
├── .env.example         # Environment variable template
├── data/
│   ├── marketmeter.db   # Main SQLite database (~620 MB, 2.3M rows)
│   └── marketmeter.lock # Single-instance advisory lock
├── logs/
│   └── bot.log          # Rotating log (5 MB × 3 backups)
└── venv/                # Python virtual environment
```

---

## ⚙️ Configuration (config.py)

All secrets from environment variables; constants centralized.

| Variable | Default | Description |
|----------|---------|-------------|
| `MARKETMETER_BOT_TOKEN` | **required** | Bot token from @BotFather |
| `MARKETMETER_OWNER_CHAT_ID` | **required** | Owner's Telegram chat ID (notifications) |
| `MARKETMETER_SYNC_TIME` | `18:30` | Daily sync time (IST) |
| `MARKETMETER_REPORT_TIME` | `08:30` | Daily report time (IST) |
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
```

---

## 🗄 Database Schema (database.py)

### Core Tables

| Table | Rows | Purpose | Key Indexes |
|-------|------|---------|-------------|
| `bhavcopy` | 2,317,954 | Daily OHLCV + avg_price per symbol | `idx_bhavcopy_symbol_date (symbol, trade_date)` — covering index includes `close, high, low, volume, avg_price, value_lakh` |
| `daily_analysis` | 3,927 | Pre-computed indicators + score per symbol/date | `idx_analysis_date (analysis_date)`, `idx_analysis_rec (analysis_date, recommendation)`, `idx_daily_analysis_symbol_date (symbol, analysis_date)` |
| `sync_log` | 264 | Per-date sync status | `trade_date` UNIQUE |
| `report_cache` | 1 | Rendered Rich Markdown payloads | `PRIMARY KEY (kind, analysis_date, version)` — `WITHOUT ROWID` |
| `stats_cache` | 5 | Aggregated counts (avoids COUNT(*)) | `key` PRIMARY KEY |
| `subscribers` | 1 | Telegram chat_ids | `chat_id` PRIMARY KEY |

### `bhavcopy` Schema
```sql
CREATE TABLE bhavcopy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    series TEXT DEFAULT 'EQ',
    open REAL, high REAL, low REAL, close REAL, last REAL, prevclose REAL,
    volume INTEGER, value_lakh REAL, del_pct REAL, avg_price REAL,
    trade_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, analysis_date)
);
```

### Connection Settings (Optimized for 1 GB RAM)
```python
PRAGMA journal_mode = WAL
PRAGMA synchronous = NORMAL
PRAGMA cache_size = -32768        # 32 MB
PRAGMA temp_store = MEMORY
PRAGMA mmap_size = 134217728      # 128 MB
PRAGMA page_size = 4096
PRAGMA auto_vacuum = INCREMENTAL
PRAGMA secure_delete = OFF
PRAGMA foreign_keys = ON
```

---

## 🔑 Key Functions & Handlers

### `main.py` — Entry Points

| Command | Function | Description |
|---------|----------|-------------|
| (none) | `run_bot()` | Starts bot + scheduler (systemd service) |
| `--sync` | `cmd_sync()` | One-shot incremental sync + analysis |
| `--backfill` | `cmd_backfill()` | Full historical backfill from 2022-01-01 |
| `--report` | `cmd_report()` | Generate and print morning report |
| `--analyze` | `cmd_analyze()` | Run technical analysis on all symbols |
| `--status` | `cmd_status()` | Print DB statistics |

**Single-instance lock**: Advisory `fcntl.flock` on `data/marketmeter.lock` prevents concurrent DB corruption.

### `config.py` — Constants
Centralized configuration. All secrets from `os.getenv()`. Validates required vars at import.

### `database.py` — SQLite Layer

| Function | Purpose | Performance |
|----------|---------|-------------|
| `get_connection()` | Context manager with optimized PRAGMAs | — |
| `init_db()` | Creates tables, indexes, runs migrations | Idempotent |
| `insert_bhavcopy_batch(rows)` | Bulk `INSERT OR IGNORE` via `executemany` | Uses `conn.total_changes` (O(1)) not `COUNT(*)` |
| `get_stock_history(symbol, min_days, window)` | Fetches OHLCV for analysis | Covering index seek |
| `get_all_symbols(min_records)` | Symbols with sufficient history | ~4 s (full scan) — cached in `stats_cache` |
| `log_sync(date, status, records, error)` | Upsert sync_log | — |
| `save_daily_analysis(rows)` | Bulk `INSERT OR REPLACE` analysis | Uses `total_changes` counter |
| `get_latest_analysis(date?)` | All analysis for a date | Index seek on `analysis_date` |
| `get_resolved_analysis_date()` | Latest date with analysis rows | Never uses `date.today()` |
| `get_cached_report(kind, date)` | Report cache lookup | PK seek on `WITHOUT ROWID` table (~0.1 ms) |
| `put_cached_report(kind, date, payload)` | Store + prune old versions | — |
| `add_subscriber(chat_id, ...)` | Upsert subscriber | — |
| `get_active_subscribers()` | Broadcast target list | Tiny table |
| `get_db_stats()` | Cached stats (records, symbols, range, subs) | No `COUNT(*)` on big tables |
| `init_stats_cache(conn)` | One-time cold cache build | Runs once |
| `vacuum_db()` | Reclaim space | Manual/maintenance |

**Migration Strategy**: `ALTER TABLE ADD COLUMN` is metadata-only in SQLite. New columns (`ema_100`, `ema_200`, `avg_price`) added idempotently at startup.

### `data_fetcher.py` — NSE Sync

| Function | Purpose |
|----------|---------|
| `fetch_bhavcopy_csv(date, session)` | Downloads CSV from `nsearchives.nseindia.com`; raises `BhavcopyNotPublished` on 404 |
| `transform_bhavcopy(df, date)` | Maps NSE columns → schema; keeps `AVG_PRICE` (nsefin drops it) |
| `download_bhavcopy_for_date(date, session)` | Retries up to `MAX_RETRIES` with exponential backoff |
| `download_and_store_date(date, session)` | Download → transform → `insert_bhavcopy_batch` → log sync |
| `sync_incremental_data()` | Main entry: finds missing dates + last N failed → downloads → stores → analysis trigger |
| `backfill_historical_data(start, end)` | Full historical load (1100+ trading days) |

**Sync Classification Logic** (`classify_sync_status`):
- **Weekend** → `holiday`
- **Weekday + 404 / "not published"** → `not_available` (retryable)
- **Weekday + network error** → `failed` (retry next day)

**Market-close guard**: Skips today's date if `datetime.now().hour < 16` (IST) to avoid logging 404 as failure.

**Retry Loop** (scheduler): Re-attempts every 15 min until 23:00 IST, then defers to next 18:30 run.

### `analyzer.py` — Technical Analysis

**Indicators** (pure pandas/numpy, no TA-Lib dependency):
| Indicator | Function | Parameters |
|-----------|----------|------------|
| SMA | `calc_sma(series, window)` | 20, 50, 100, 200 |
| EMA | `calc_ema(series, window)` | 20, 50, 100, 200 |
| RSI | `calc_rsi(series, 14)` | Wilder's smoothing |
| MACD | `calc_macd(series, 12, 26, 9)` | line, signal, histogram |
| ATR | `calc_atr(high, low, close, 14)` | True Range SMA |
| ADX | `calc_adx(high, low, close, 14)` | +DI, -DI, DX, smoothed |
| Bollinger | `calc_bollinger_bands(series, 20, 2)` | upper, middle, lower |
| OBV | `calc_obv(close, volume)` | Cumulative signed volume |

**`analyze_stock(df, symbol)` → dict**  
Filters: `close >= 20`, `volume >= 10_000`, `len(df) >= 50`.  
Returns all indicators + `composite_score` + `recommendation` + narrative fields.

**Scoring Rules** (max 18 points):
| Factor | Points |
|--------|--------|
| RSI 60–75 | +3 |
| RSI > 75 | +2 |
| RSI > 50 | +1 |
| ADX > 50 | +3 |
| ADX > 30 | +2 |
| ADX > 20 | +1 |
| RelVol > 3× | +3 |
| RelVol > 2× | +2 |
| RelVol > 1.5× | +1 |
| MACD bullish | +2 |
| Price > SMA20 | +2 |
| Price > SMA50 | +2 |
| Price > SMA100 | +1 |
| Price > 5% above SMA20 | +1 |
| OBV rising | +1 |

**Recommendation Mapping**:
| Score | RSI Gate | ADX Gate | Label |
|-------|----------|----------|-------|
| ≥12 | <70 | >30 | STRONG_BUY |
| ≥10 | <75 | >25 | BUY |
| ≥8 | <80 | — | ACCUMULATE |
| ≥6 | — | — | WATCH |
| — | >80 | — | CAUTION |
| else | — | — | AVOID |

**`run_batch_analysis(date?)`**  
Processes all 2,959 qualified symbols in batches of 200, writes to `daily_analysis`, warms report cache.

**`get_market_outlook(date?)`** — Aggregate bullish/bearish/neutral percentages, avg RSI/ADX.

### `report_generator.py` — Rich Markdown Reports

**Report Structure** (≈5.4 KB, fits in single Rich Message):
1. Header: date, market outlook, category tally
2. **Top 3 Picks** — full indicator breakdown (SMA/EMA/RSI/ADX/MACD/BB/RelVol/OBV)
3. **Top 25 Scan Table** — compact columns: `#, Symbol, LTP, AvgPrice, RSI, ADX, RelVol, OBV, BB, MACD, Rec`
4. Collapsible `<details>` Column Guide
5. Collapsible `<details>` Data Summary (DB stats)
6. Footer: commands, disclaimer

**Caching**: `report_cache` keyed by `(kind, analysis_date, REPORT_CACHE_VERSION)`. Invalidate by bumping `REPORT_CACHE_VERSION` in `config.py`. Retains last 7 dates per kind.

**Chunking**: `_split_rich_markdown()` respects:
- Never splits inside `<details>` blocks
- Repeats table header/separator rows on chunk boundaries
- Hard cap: 4,096 chars/message; 32,768 chars total payload

### `bot.py` — Telegram Bot (python-telegram-bot 21.x)

**Commands**:
| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | `cmd_start` | Welcome message |
| `/help` | `cmd_help` | Command list |
| `/subscribe` | `cmd_subscribe` | Add to broadcast list |
| `/unsubscribe` | `cmd_unsubscribe` | Soft-delete |
| `/report` | `cmd_report` | On-demand latest report |
| `/status` | `cmd_status` | DB + sync status |
| `/indicators` | `cmd_indicators` | Full indicator glossary + scoring |

**Rich Message Delivery** (`_send_rich_chunks`):
- Uses `sendRichMessage` via local Bot API server (`localhost:8082`)
- Auto-detects Rich syntax (`**bold**`, `|table|`, `<details>`)
- Falls back to `send_message` with Markdown for plain text

**Broadcast** (`broadcast_to_subscribers`):
- Iterates active subscribers
- Handles `Forbidden` (blocks bot) → deactivates subscriber
- Rate-limits: 25 msg → 1 s pause

### `scheduler.py` — APScheduler Jobs

| Job | Trigger | Time (IST) | Function |
|-----|---------|------------|----------|
| `daily_sync` | `cron` daily | 18:30 | `_daily_sync_job` → sync → notify → analysis → warm cache |
| `daily_report` | `cron` daily | 08:30 | `_daily_report_job` → generate → broadcast → owner confirm |
| `sync_retry` | `interval` 15 min | dynamic | `_sync_retry_job` → re-sync pending dates → re-arm until 23:00 |

**Retry Logic**: `_schedule_sync_retry()` arms a one-shot job; `_sync_retry_job` re-arms itself on `not_available` until cutoff hour.

---

## 📈 Query Performance (Measured on 2.3M rows)

| Query | Index Used | Time |
|-------|------------|------|
| `get_stock_history` (full) | `idx_bhavcopy_cover` (covering) | 68 ms |
| `get_stock_history` (260-day window) | `idx_bhavcopy_cover` + LIMIT | 1.3 ms |
| `get_latest_analysis` | `idx_analysis_date` | 300 ms |
| `report_cache` lookup | PK `(kind, date, version)` | 0.1 ms |
| `stats_cache` lookup | PK `key` | 0.2 ms |
| `get_all_symbols` (GROUP BY) | `idx_bhavcopy_symbol_date` | 4.2 s (cached after first run) |

**Optimization Notes**:
- `idx_bhavcopy_cover` is a **covering index**: `(symbol, trade_date, close, high, low, volume, avg_price, value_lakh)` — analyzer queries never touch the heap.
- `stats_cache` avoids `COUNT(*)` on 2.3M rows (23 s each). Updated arithmetically on insert.
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

**Commands**:
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
```

---

## 📊 Data Flow Summary

```
18:30 IST  ──▶ sync_incremental_data()
                ├─ find missing dates since last success
                ├─ retry last 5 failed dates
                ├─ skip today if before 16:00
                ├─ download CSV per date (150 ms each)
                ├─ transform → insert_bhavcopy_batch()
                ├─ log_sync(status, records)
                └─ if new data: run_batch_analysis() → warm_report_cache()

08:30 IST  ──▶ send_report_to_all()
                ├─ generate_morning_report() (cache hit: 0.1 ms)
                ├─ broadcast_to_subscribers() (Rich chunks)
                └─ notify owner: sent/failed counts
```

---

## 🔐 Security & Hygiene

- **No secrets in code**: All tokens/IDs via `EnvironmentFile` (0600).
- **Single-instance lock**: Prevents concurrent DB writers.
- **Input validation**: NSE CSV columns validated; `INSERT OR IGNORE` prevents duplicates.
- **SQL injection**: All queries parameterized (`?` placeholders).
- **PII**: No user data logged; only `chat_id` (integer) stored.
- **Logging**: Rotating file handler (5 MB × 3), no stdout duplication.
- **Memory limits**: systemd `MemoryHigh`/`MemoryMax` prevent OOM.

---

## 📦 Dependencies (requirements.txt)

```txt
pandas>=2.2,<3.0
numpy>=1.26,<3.0
python-telegram-bot[job-queue]>=21.0,<22.0
requests>=2.31.0
```

Pinned to tested major versions. `python-telegram-bot[job-queue]` pulls APScheduler.

---

## 🛠 Extending / Customizing

| Change | Files to Edit |
|--------|---------------|
| Add indicator | `analyzer.py` (calc function + `analyze_stock`) |
| Change scoring | `analyzer.py` (`_get_recommendation`) |
| Modify report layout | `report_generator.py` (`_render_morning_report`) |
| Add command | `bot.py` (handler + `create_application`) |
| Change schedule | `config.py` (`SYNC_TIME`, `REPORT_TIME`) + systemd `Environment=` |
| Add DB column | `database.py` (`_ANALYSIS_ADDED_COLUMNS` + migration) |
| Change NSE source | `data_fetcher.py` (`NSE_BHAVCOPY_URL`, `transform_bhavcopy`) |

---

## 📝 License

MIT — see `LICENSE` (add if needed).

---

## 👤 Author

**Sujit Roy** (@notorious_thug)  
Repository: https://github.com/SujitRoy/MarketMeterBOT.git