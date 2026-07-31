# MarketMeterBOT — NSE Stock Analysis Telegram Bot

A production-grade Telegram bot that downloads daily NSE BhavCopy data, runs technical analysis on 3,066 tracked symbols (~2,900 with enough history), and delivers curated morning reports with BUY/WATCH/AVOID signals.

> **Current state (verified 2026-07-30):** pipeline live — BhavCopy synced through `2026-07-30`, 2.32 M rows, 5 active subscribers, report cache warm (`v4`).

## 🏗 Architecture Overview

MarketMeterBOT follows a clean, modular separation-of-concerns design. The codebase has been restructured into independent, testable packages:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MarketMeterBOT System                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐  │
│  │  NSE Archive │──▶│  NSE Fetcher │──▶│  SQLite DB   │◀──│Analysis  │  │
│  │ (CSV over    │   │ (src/data/)  │   │ (src/db/)    │   │engine    │  │
│  │   HTTPS)     │   └──────────────┘   └───────┬──────┘   │ (src/an)|  │
│  └──────────────┘                            ▼         │alyz.   │  │
│                   ┌─────────────────────┐            └─────────┘  │
│                   │  Report Cache       │                          │
│                   │   (src/cache/)      │                          │
│                   └──────────┬──────────┘                          │
│                              ▼                                    │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │               Report Registry / Dispatcher                  │    │
│  │   (src/reports/registry.py + registry)                      │    │
│  ├────────────────────────────────────────────────────────────┤    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │    │
│  │  │ Morning     │  │ Pre-Market  │  │ Technical   │          │    │
│  │  │ Report      │  │ Combined    │  │ Summary     │          │    │
│  │  │ (src/rpt/   │  │ (src/rpt/   │  │ (src/rpt/   │          │    │
│  │  │   morning)  │  │ premarket)  │  │ technical)  │          │    │
│  │  └────┬──────┘  └────┬──────┘  └────┬──────┘          │    │
│  │       │             │              │                 │    │
│  └───────▼─────────────▼──────────────▼─────────────────┘    │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                Telegram Bot Application                 │ │
│  │   (src/bot/application.py, src/bot/handlers/)           │ │
│  └─────────────────────────────────────────────────────────┘ │
│                   ▲                                       │
│  ┌────────────────┼───────────────────────────────────────┤ │
│  │ Scheduler                                      Admin CLI  │ │
│  │ (src/scheduler/)                       (src/cli/)       │ │
│  └────────────────┴───────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Principles:**
- **Single Responsibility**: Each module does one thing well
- **Dependency Injection**: Loosely coupled via repositories/interfaces
- **Testability**: Every function/unit isolated for testing
- **Extensibility**: Add reports by inheriting `BaseReport`
- **Production Ready**: Monitoring, logging, error handling built-in

---

## 📂 Codebase Structure (Modular Version)

```
MarketMeterBOT/
├── src/                              # All source code (Python package)
│   ├── core/                         # Foundation infrastructure
│   │   ├── __init__.py
│   │   ├── config.py                 # Centralized config & env vars
│   │   ├── constants.py              # Enums, shared constants
│   │   ├── exceptions.py             # Custom exception hierarchy
│   │   └── logging.py               # Structured logging setup
│   │
│   ├── database/                     # Data persistence layer
│   │   ├── __init__.py
│   │   ├── connection.py            # Connection management
│   │   ├── models.py                # Dataclass ORM models
│   │   ├── queries.py               # Parameterized SQL templates
│   │   ├── migrations.py            # Schema version control
│   │   └── repositories/            # DAO pattern per domain
│   │       ├── __init__.py
│   │       ├── bhavcopy_repo.py
│   │       ├── analysis_repo.py
│   │       ├── sync_repo.py
│   │       ├── subscriber_repo.py
│   │       └── report_cache_repo.py
│   │
│   ├── data/                         # Data fetching & processing
│   │   ├── __init__.py
│   │   ├── fetchers/                # External APIs/sources
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Abstract fetcher class
│   │   │   ├── nse_bhavcopy.py      # NSE EOD CSV downloader
│   │   │   ├── tradingview_scanner.py Live intraday data
│   │   │   └── paytm_money.py       # Broker API (placeholder)
│   │   ├── transformers/            # Data conversion
│   │   │   ├── __init__.py
│   │   │   ├── bhavcopy_transformer.py
│   │   │   └── live_data_transformer.py
│   │   └── sync/                    # Orchestration engine
│   │       ├── __init__.py
│   │       ├── sync_engine.py       # Incremental sync
│   │       ├── backfill_engine.py   # Full historical load
│   │       └── retry_handler.py     # Retry loop management
│   │
│   ├── analysis/                     # Technical analysis engine
│   │   ├── __init__.py
│   │   ├── indicators/              # Individual indicator impls
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # BaseIndicator ABC
│   │   ├── momentum.py              # RSI, MACD, Stochastic
│   │   ├── trend.py                 # SMA, EMA, ADX, Parabolic SAR
│   │   ├── volatility.py            # ATR, Bollinger, Keltner
│   │   └── volume.py                # OBV, RelVolume, VWAP
│   │   ├── scorer.py                # Composite scoring + recommendation
│   │   └── analyzer.py              # Batch processing engine
│   │   └── backtest/                # Backtesting framework
│   │       ├── __init__.py
│   │       ├── engine.py            # Strategy backtesting
│   │       ├── metrics.py           # Performance statistics
│   │       └── fastbt_adapter.py    # Integration point for fastbt
│   │
│   ├── reports/                      # Report generation system
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseReport, TemplateReport
│   │   ├── registry.py              # Global report registry
│   │   ├── morning/                 # Daily morning report
│   │   │   ├── __init__.py
│   │   │   └── morning_report.py    # Main report builder
│   │   ├── premarket/               # Pre-market live data reports
│   │   │   ├── __init__.py
│   │   │   ├── premarket_report.py  # Combined & cross-check
│   │   ├── technical/               # Symbol-specific details
│   │   │   ├── __init__.py
│   │   │   └── technical_report.py
│   │   ├── sector/                  # Sector-level aggregation
│   │   │   ├── __init__.py
│   │   │   └── sector_report.py
│   │   ├── scanner/                 # Custom search/scanner results
│   │   │   ├── __init__.py
│   │   │   └── scanner_report.py
│   │   ├── backtest/                # Backtest result reporting
│   │   │   ├── __init__.py
│   │   │   └── backtest_report.py
│   │   └── custom/                  # User-defined templates
│   │       ├── __init__.py
│   │       └── custom_report.py
│   │
│   ├── bot/                         # Telegram integration
│   │   ├── __init__.py
│   │   ├── application.py           # App creation + setup
│   │   ├── handlers/                # Command handlers
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # BaseHandler class
│   │   │   ├── start.py             # /start, /help
│   │   │   ├── subscribe.py         # /subscribe, /unsubscribe
│   │   │   ├── report.py            # /report on-demand
│   │   │   ├── status.py            # /status
│   │   │   ├── indicators.py        # /indicators glossary
│   │   │   ├── search.py            # /search fuzzy finder
│   │   │   └── admin.py             # Owner-only maintenance
│   │   ├── keyboards/               # Inline button builders
│   │   │   ├── __init__.py
│   │   │   ├── menu.py              # Main menu keyboard
│   │   │   └── pagination.py        # Large-list pagination
│   │   ├── middlewares/             # Request preprocessing
│   │   │   ├── __init__.py
│   │   │   ├── logging.py           # Update logging middleware
│   │   │   └── rate_limit.py        # Per-chat rate limiting
│   │   └── filters/                 # Custom Telegram filters
│   │       ├── __init__.py
│   │       └── chat_type.py         # Private/group/channel types
│   │
│   ├── scheduler/                   # APScheduler integration
│   │   ├── __init__.py
│   │   ├── scheduler.py             # Job manager + cron setup
│   │   └── jobs.py                  # Job definitions (internal)
│   │
│   ├── cache/                       # Caching layer
│   │   ├── __init__.py
│   │   ├── cache_manager.py         # In-memory LRU/TTL cache
│   │   ├── report_cache.py          # Persistent report cache DB
│   │   └── stats_cache.py           # Cached DB stats
│   │
│   ├── utils/                       # General utilities
│   │   ├── __init__.py
│   │   ├── time_utils.py            # IST timezone helpers
│   │   ├── formatting.py            # Number/price/emoji formatting
│   │   ├── validators.py            # Input validation funcs
│   │   ├── decorators.py            # @cached, @retry, @log_calls
│   │   └── helpers.py               # Hashing, chunking, etc.
│   │
│   └── cli/                         # Command-line tools
│       ├── __init__.py
│       ├── commands.py              # Click CLI commands
│       └── main.py                  # CLI entry point
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures
│   ├── unit/                        # Unit tests
│   │   ├── test_indicators.py
│   │   ├── test_scorer.py
│   │   └── test_reports.py
│   └── integration/                 # Integration tests
│       ├── test_database.py
│       ├── test_sync.py
│       └── test_bot.py
│
├── data/                            # Runtime data
│   ├── marketmeter.db
│   └── marketmeter.lock
├── logs/                            # Log files
│   ├── bot.log
│   ├── sync.log
│   └── error.log
├── docs/                            # Documentation
│   ├── README.md
│   ├── API.md
│   ├── REPORTS.md
│   └── DEPLOYMENT.md
├── scripts/                         # Maintenance scripts
│   ├── backup_db.py
│   ├── vacuum_db.py
│   └── migrate.py
├── .env.example                     # Environment template
├── .gitignore
├── requirements.txt                 # Production deps
├── pyproject.toml                 # Modern Python packaging
├── Makefile                         # Common tasks
└── main.py                         # Entry point (bot or CLI)
```

---

## ⚙️ New Configuration Architecture (src/core/config.py)

All secrets from environment variables; constants centralized. Key configuration points in the modular design:

| Variable | Source | Use Case |
|----------|--------|----------|
| `MARKETMETER_BOT_TOKEN` | env | Bot authentication |
| `MARKETMETER_OWNER_CHAT_ID` | env | Admin notifications |
| `TELEGRAM_API_BASE_URL` | env (opt) | Local Bot API server for Rich Messages |
| `TRADINGVIEW_SESSION_ID` | env (opt) | Live data auth |
| `MARKETMETER_LOG_LEVEL` | env (INFO/DEBUG) | Logging verbosity |

---

## 🗄 Database Layer (src/database/)

### Repository Pattern Separation

Each domain object has its own repository interface:

```python
from src.database.repositories import BhavCopyRepository, AnalysisRepository, SubscriberRepository

bhavcopy = BhavCopyRepository()
analysis = AnalysisRepository()
subs = SubscriberRepository()

# Example usage
bhavcopy.insert_batch(rows)  # Bulk insert EOD data
history = bhavcopy.get_history("RELIANCE", min_days=50)  # For analysis
analysis.save_batch(daily_analysis_rows)  # Persist indicators
active_subs = subs.get_active_subscribers()  # For broadcast
```

This makes dependency injection straightforward and allows mocking in tests.

---

## 📊 Data Pipeline (src/data/)

### Fetchers Hierarchy

```
BaseFetcher (ABC)
├── NSEBhavCopyFetcher    # Download daily EOD
├── TradingViewScannerFetcher # Live intraday
└── PaytmMoneyFetcher    # Future broker integration
```

### Transformers

Convert raw fetcher output to domain models:
- `transform_bhavcopy(df)` → normalized format for DB
- `transform_live_snapshot(raw)` → standardized dict schema

### Sync Engines

```python
from src.data.sync import SyncEngine, BackfillEngine

engine = SyncEngine()
result = engine.run_incremental_sync()  # Daily run
# or
backfill = BackfillEngine()
backfill.run_backfill(start_date, end_date)  # One-time init
```

Retry logic handles network failures, market holidays, and NSE publishing delays.

---

## 📈 Analysis Engine (src/analysis/)

### Modular Indicators

Each indicator is pluggable:

```python
from src.analysis.indicators import RSIIndicator, MACDIndicator, SMAIndicator

rsi = RSIIndicator(14)
macd = MACDIndicator(12, 26, 9)
sma20 = SMAIndicator(20)

df = pd.DataFrame(historical_data)
rsi_values = rsi.calculate(df)
macd_vals = macd.calculate(df)
sma20_val = sma20.calculate(df)[-1]  # Latest
```

### Scoring & Recommendations

The `CompositeScorer` combines multiple indicators into a single score (0-18) with automatic recommendation mapping. Runs batch analysis efficiently.

### Backtesting Framework (src/analysis/backtest/)

Future-proofed with support for `fastbt` adapter:

```python
from src.analysis.backtest import BacktestEngine

engine = BacktestEngine()
result = engine.run_backtest(strategy, symbols, start, end)
print(print_metrics(result))
```

---

## 📰 Reports System (src/reports/)

### Registry-Based Dispatch

Reports auto-register via decorator:

```python
@register_report("morning")
class MorningReport(BaseReport):
    kind = "morning"
    name = "Morning Report"
    
    def build(self, context):
        # Build report content
        return ReportResult(content=..., chunks=[...])
```

Registry looks up by string key and builds dynamically. Easy to add new report types without modifying code.

### Available Report Types

| Kind | Trigger | Description |
|------|---------|-------------|
| `morning` | 08:30 daily | Top 3 picks + top 25 scan |
| `combined_premarket` | 09:00 daily | Historical + live merge |
| `open_crosscheck` | 09:15 daily | Morning vs open comparison |
| `technical` | On command | Single-symbol deep dive |
| `sector` | TBD | By-sector aggregation |
| `scanner` | On command | Search/filter results |
| `backtest` | On demand | Backtest result display |
| `custom` | User-defined | Template-based |

---

## 🤖 Telegram Bot (src/bot/)

### Handler Architecture

Each command is its own handler class implementing `BaseHandler.handle()`:

```python
class StartHandler(BaseHandler):
    @property
    def command(self): return "start"
    
    async def handle(self, update, context):
        await send_welcome_message(update)
```

Handlers registered automatically via `register_handlers(app)`.

### Rich Message Support

The local Bot API server enables native tables and `<details>` collapsible sections via `sendRichMessage`. Chunking ensures large reports stay within limits.

---

## ⏰ Scheduler (src/scheduler/)

```python
def setup_scheduled_jobs(app):
    """Register all cron-style jobs."""
    from src.data.sync import SyncEngine
    from src.reports.premarket import send_combined_premarket_report, send_open_crosscheck_report
    
    # Get time utilities from config
    sync_time = get_sync_time()    # 18:30
    report_time = get_report_time()# 08:30
    premarket_time = get_premarket_time() # 09:00
    
    app.job_queue.run_daily(_sync_job_wrapper, hour=sync_time.hour, minute=sync_time.minute)
    app.job_queue.run_daily(_report_job_wrapper, hour=report_time.hour, minute=report_time.minute)
    app.job_queue.run_daily(_premarket_job, hour=premarket_time.hour, minute=premarket_time.minute, days="mon-fri")
```

Uses `asyncio` event loop integration for non-blocking scheduling.

---

## 🧪 Testing

All modules are independently testable. Run the full test suite:

```bash
cd /home/ubuntu/MarketMeterBOT
python3 -m pytest tests/ -v
pytest tests/unit/       # Unit tests only
pytest tests/integration/  # Integration tests
```

Each test verifies isolation from external dependencies (mocked DB, network).

---

## 🛠 Development Commands

With the modern `pyproject.toml` and `Makefile`:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Format code (black)
python3 -m black src/

# Check imports/types (ruff)
python3 -m ruff check src/

# Type checking (mypy)
python3 -m mypy src/

# Run tests
python3 -m pytest tests/

# Clean up
make clean

# Start the bot
python3 -m src.main

# Run one-shot operations
python3 -m src.main --sync
python3 -m src.main --backfill
python3 -m src.main --analyze
python3 -m src.main --report
python3 -m src.main --status
```

---

## 🚀 Deployment

Run as a systemd service (user-level):

```ini
[Unit]
Description=MarketMeterBOT - NSE Stock Analysis Telegram Bot
After=network.target

[Service]
Type=exec
WorkingDirectory=/home/ubuntu/MarketMeterBOT
EnvironmentFile=/home/ubuntu/.config/marketmeter/env
ExecStart=/home/ubuntu/MarketMeterBOT/venv/bin/python3 -m src.main
Restart=on-failure
RestartSec=10
MemoryHigh=500M
MemoryMax=600M

[Install]
WantedBy=default.target
```

Requires a local Bot API server on `http://localhost:8082/bot` for Rich Messages (Bot API 10.1+ table/collapsible support).

---

## 🔐 Security Best Practices

- **Never commit `.env`** — it's in `.gitignore`
- Use `os.getenv()` validation in `config.py` — missing required vars raise at startup
- All database queries use parameterized placeholders (`?`)
- No user input written to DB without sanitization
- Bot token never logged (mask via config validation)
- File permissions on `.env` set to `0600`

---

## 📦 Dependencies (requirements.txt)

Pinned to tested versions. Full list in `requirements.txt`:

```txt
# Core
pandas>=2.2,<3.0
numpy>=1.26,<3.0
python-telegram-bot[job-queue]>=21.0,<22.0
requests>=2.31.0

# Fuzzy search (for /search)
rapidfuzz>=3.0,<4.0

# Templates
jinja2>=3.1,<4.0

# Environment
python-dotenv>=1.0,<2.0

# Timezone
pytz>=2024.1,<2025.0

# Testing
pytest>=8.0,<9.0
pytest-asyncio>=0.23,<1.0

# Code quality
black>=24.0,<25.0
mypy>=1.9,<2.0
ruff>=0.4,<1.0
```

---

## 📑 License

MIT — see [LICENSE](LICENSE) file.

---

## 👤 Author

**Sujit Roy** (@notorious_thug)  
Telegram: [@notorious_thug](https://t.me/notorious_thug)  
Repository: https://github.com/SujitRoy/MarketMeterBOT.git

---

## 🔄 Migration Notes (Monolithic → Modular)

If upgrading from an older version, note these key changes:

1. All top-level Python files moved to `src/` subdirectories matching their logical domain
2. Relative imports updated accordingly (use absolute imports like `from src.core.config import *`)
3. `main.py` now imports from `src.main` package entry point
4. Database access goes through repositories (`src/database/repositories/`) instead of direct file imports
5. All new modules have type hints and docstrings matching the existing style
6. Tests remain in `tests/` but may need import path updates if they used relative paths

The migration preserves behavioral compatibility — all reported functionality works identically after refactoring.