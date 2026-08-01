# MarketMeterBOT — Modular Refactor Plan

**Branch:** `beta` (created from `main` @ `ebaf301`)
**Main:** untouched, production, frozen for the duration of this work
**Goal:** restructure `MarketMeterBOT` into a feature-wise modular `src/marketmeter/` package, with a fresh end-to-end test suite alongside the new code. Beta is greenfield — pre-existing baseline test failures do **not** block refactor; they get resolved as their owning module is rebuilt.

This document is the **single source of truth** for the refactor. If code ever drifts from this doc, the doc wins and code is corrected. Every phase must end with: doc updated if needed, code matches doc, commit message references phase number.

---

## 0. Branch & Working Rules

- Working branch: **`beta`** only. Never commit to `main` during this work.
- Commit per phase, message prefix: `phase(N): <verb> <scope>` (e.g. `phase(1): scaffold src/marketmeter + extract core/`).
- `beta` merges back to `main` only after **all six phases GREEN** and your explicit approval.
- `data/`, `logs/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` stay gitignored — do not commit runtime state.
- No `console.log` / `print()` debug. Use `core/logging.py` structured logger.
- Every phase ends with: `git status --porcelain` clean (or only tracked changes), syntax check (`python -m py_compile`), relevant subset of tests runnable.

---

## 1. Target Layout (Final State)

```
MarketMeterBOT/
├── main.py                              # thin CLI entry — argparse + asyncio
├── requirements.txt
├── README.md
├── .env / .env.example
├── data/                                # runtime, gitignored
├── logs/                                # runtime, gitignored
├── tests/                               # mirrors src/marketmeter/
│
└── src/
    └── marketmeter/                     # installable package
        ├── core/                        # cross-cutting infra
        │   ├── config.py                # moved from /config.py
        │   ├── logging.py               # NEW — structured logger, rotation, correlation IDs
        │   ├── time.py                  # NEW — IST clock, trading-day utils, NSE_HOLIDAYS
        │   ├── retry.py                 # NEW — async retry/backoff decorator
        │   ├── concurrency.py           # NEW — single-instance lock, semaphores
        │   └── errors.py                # NEW — typed exceptions
        │
        ├── db/                          # persistence layer
        │   ├── __init__.py              # re-exports public surface
        │   ├── connection.py            # get_connection() + row factory + pragmas
        │   ├── schema.py                # ALL CREATE TABLE / CREATE INDEX / migrations
        │   ├── bhavcopy_repo.py         # bhavcopy CRUD
        │   ├── analysis_repo.py         # daily_analysis CRUD
        │   ├── sync_repo.py             # sync_log + retry state
        │   ├── cache_repo.py            # report_cache CRUD + invalidate + warm
        │   ├── subscriber_repo.py       # subscribers CRUD
        │   ├── intraday_repo.py         # candles, alerts, tracked_symbols
        │   ├── stats_repo.py            # get_db_stats, init_stats_cache, vacuum_db
        │   └── migrations/              # versioned SQL
        │       └── 001_initial.sql
        │
        ├── sources/                     # external data providers
        │   ├── base.py                  # NEW — abstract Provider protocol
        │   ├── nse.py                   # BhavCopy download + classification + sync + backfill
        │   └── tradingview.py           # tv lookup, live snapshot, 5-min aggregate, ingest
        │
        ├── analysis/                    # pure compute
        │   ├── indicators.py            # SMA/EMA/RSI/MACD/ATR/ADX/BB/OBV
        │   ├── scoring.py               # BUY/SELL/HOLD logic
        │   ├── analyzer.py              # analyze_stock() per-symbol pipeline
        │   ├── batch.py                 # run_batch_analysis (memory-bounded)
        │   └── outlook.py               # market outlook + aggregate
        │
        ├── reports/                     # human-readable output
        │   ├── formatters.py            # NEW — shared _fmt/_signed_pct/_fmt_price/_fmt_num/etc.
        │   ├── labels.py                # NEW — shared _rvol_signal/_tv_rating_label/_gap_emoji/etc.
        │   ├── morning.py               # generate_morning_report + single-pass render
        │   ├── premarket_live.py        # 09:00 live-only
        │   ├── premarket_open.py        # 09:15 cross-check
        │   ├── premarket_combined.py    # combined historical+live
        │   ├── status.py                # /status + sync status + sync failure alert
        │   ├── reference.py             # /indicators + /help + /welcome
        │   └── cache.py                 # warm_report_cache + _no_data_report
        │
        ├── telegram/                    # telegram transport
        │   ├── app.py                   # create_application (handler registration)
        │   ├── menu.py                  # menu button setup
        │   ├── delivery.py              # send_to_owner, broadcast_to_subscribers, send_report_to_all
        │   ├── rich/
        │   │   ├── detect.py            # _needs_rich
        │   │   ├── split.py             # _split_rich_markdown, _split_message
        │   │   └── send.py              # _send_rich_message, _send_rich_chunks, _send_report_in_chunks, _reply
        │   ├── search/
        │   │   ├── lookup.py            # tv_symbol_lookup, fuzzy
        │   │   ├── keyboards.py         # build_search_keyboard, _build_candidate_keyboard, _chart_keyboard
        │   │   └── detail.py            # fetch_live_for_symbol, format_live_detail, _build_detail_body, send_live_stock_detail
        │   └── handlers/
        │       ├── core.py              # /start /help /status /indicators /subscribe /unsubscribe
        │       ├── report.py            # /report
        │       └── search.py            # /search + on_search_select
        │
        ├── scheduler/                   # scheduled jobs
        │   ├── app.py                   # setup_scheduled_jobs
        │   ├── jobs.py                  # all cron job handlers
        │   ├── sync_cycle.py            # _run_sync_cycle, _schedule_sync_retry, confirm_bhavcopy_insertion
        │   └── timeparse.py             # _parse_time
        │
        └── cli/                         # operator entrypoints
            ├── main.py                  # moved from /main.py
            ├── cmd_sync.py              # cmd_sync, cmd_backfill
            ├── cmd_analyze.py           # cmd_analyze, cmd_report
            └── cmd_status.py            # cmd_status
```

---

## 2. Dependency Direction (Allowed Edges Only)

```
core  ──┬──► db
        ├──► sources ──┬──► analysis ──┐
        │              │               ├──► reports ──┐
        │              └──► (live)                   │
        ├──► telegram ──────────────────────────────┤
        │       ├──► handlers ──► reports
        │       ├──► search ────► sources + reports
        │       └──► rich
        └──► scheduler ──► sources + analysis + reports + telegram.delivery
                                  cli/main ──► scheduler + telegram + db
```

**Forbidden:** back-edges, sibling-to-sibling imports between feature packages, anything reaching into another package's private helpers (leading underscore).

---

## 3. Test Layout (Mirrors Source)

```
tests/
├── core/        test_logging.py test_retry.py test_time.py
├── db/          test_bhavcopy_repo.py test_cache_repo.py test_intraday_repo.py …
├── sources/     test_nse.py test_tradingview.py
├── analysis/    test_indicators.py test_scoring.py test_batch.py
├── reports/     test_morning.py test_premarket_combined.py test_formatters.py
├── telegram/    test_rich_split.py test_search_lookup.py test_handlers.py
├── scheduler/   test_sync_cycle.py test_retry_gating.py
├── cli/         test_main_lock.py
├── conftest.py  # shared fixtures (DB connection, in-memory db, sample bhavcopy rows)
└── e2e/         test_full_sync_to_report.py test_search_flow.py test_premarket_pipeline.py
```

**Test principles for beta:**
- Fresh test suite, not a port of the old tests. Old tests can inform coverage but new tests are written against new module APIs.
- `db/connection.py` must support an in-memory `:memory:` SQLite for fast unit tests.
- Snapshot tests for reports: byte-equal output given identical inputs (determinism).
- `pytest` is the runner. `unittest` allowed inside but `pytest`-compatible.

---

## 4. Phased Rollout (Six Phases)

Each phase is a separate commit on `beta`. Stop after each phase and wait for explicit "go" before next.

### Phase 0 — Baseline capture & doc
- ✅ Created `docs/REFACTOR_PLAN.md` (this file).
- ✅ Documented current module map in §6 below.

**Gate:** doc committed to `beta`; `main` HEAD unchanged.

### Phase 1 — `src/marketmeter/` skeleton + `core/` extraction
- Add empty package skeleton with `__init__.py` files.
- Move `config.py` → `src/marketmeter/core/config.py`. Keep a thin shim `/config.py` that re-exports, so `main.py` keeps booting without a giant diff. Remove shim later.
- Add `core/logging.py`, `core/time.py`, `core/retry.py`, `core/concurrency.py`, `core/errors.py`.
- Extract `_acquire_lock` (from `main.py`) → `core/concurrency.py`.
- Extract `is_trading_day` / `is_nse_holiday` / `NSE_HOLIDAYS` (from `data_fetcher.py`) → `core/time.py`. Old call sites import from `core.time` until Phase 3 retires them.
- Wire `core/logging.py` into `main.py`; replace ad-hoc `logging.basicConfig` if any.

**Gate:** `python main.py` boots; `python main.py --status` returns; pre-existing tests (those that pass on main baseline) still pass.

### Phase 2 — Split `database.py` into `db/` repos
- `db/__init__.py` re-exports the full public surface — old `import database` keeps working during migration.
- `db/connection.py` (connection factory, row factory, pragmas).
- `db/schema.py` (all `CREATE TABLE` / `CREATE INDEX`, `_migrate_analysis_columns`).
- `db/bhavcopy_repo.py` (insert/get/list symbols/date range/total records).
- `db/analysis_repo.py` (save/get latest/get by recommendation/resolved date).
- `db/sync_repo.py` (sync_log CRUD + status + failed syncs + holidays).
- `db/cache_repo.py` (report_cache CRUD + invalidate + warm).
- `db/subscriber_repo.py` (subscriber CRUD + count).
- `db/intraday_repo.py` (candles, alerts, tracked symbols, prune, init_intraday_tables).
- `db/stats_repo.py` (get_db_stats, init_stats_cache, vacuum_db).
- Add `db/migrations/001_initial.sql` capturing the canonical schema (so fresh installs and tests can re-create from SQL).
- Add `tests/db/conftest.py` with `:memory:` SQLite fixture.

**Gate:** `get_db_stats()` returns identical output; `database.py` is a thin re-export shim or removed; all passing tests on `main` baseline still pass.

### Phase 3 — Split `sources/` (NSE + TradingView isolation)
- `data_fetcher.py` → `sources/nse.py`.
- `intraday_fetcher.py` → `sources/tradingview.py`.
- New `sources/base.py` defines `Provider` Protocol: `fetch_eod()`, `fetch_intraday(symbol)`, `name` property, `health()`.
- `NSEProvider` and `TradingViewProvider` implement it.
- Search's live fetch becomes a `Provider.fetch_intraday(symbol)` call — TradingView is the default; new providers (Zerodha Kite, Upstox, Angel One) plug in without touching search/report code.
- Move NSE holidays + is_trading_day fully into `core/time.py` (already started in Phase 1).

**Gate:** `/search` works; pre-market live report works; intraday ingest runs.

### Phase 4 — Split `analysis/` and `reports/` (the big one)
- Indicators → `analysis/indicators.py`. Scoring → `analysis/scoring.py`. Per-symbol → `analysis/analyzer.py`. Batch runner → `analysis/batch.py`. Outlook/aggregate → `analysis/outlook.py`.
- Reports:
  - `morning.py` — `generate_morning_report` + single-pass render
  - `premarket_live.py` — 09:00 live-only
  - `premarket_open.py` — 09:15 cross-check
  - `premarket_combined.py` — combined historical+live
  - `status.py` — `/status`, sync status, sync failure alert
  - `reference.py` — `/indicators`, `/help`, `/welcome`
  - `cache.py` — `warm_report_cache`, `_no_data_report`
- **De-duplication:** all `_fmt`, `_signed_pct`, `_fmt_price`, `_fmt_num`, `_fmt_int`, `_fmt_mcap`, `_fmt_pct`, `_obv_label`, `_macd_label`, `_bb_pos`, `_gap`, `_gap_pct`, `_vol_ratio`, `_vol_emoji`, `_rvol_signal`, `_tv_rating_label`, `_market_state`, `_position_label`, `_rsi_signal`, `_verdict` consolidated into:
  - `reports/formatters.py` — numeric/string formatters
  - `reports/labels.py` — categorical signal labels (rvol, gap emoji, verdict, etc.)
- **Fresh test suite for reports:** snapshot tests asserting byte-equality, determinism tests, formatter unit tests, label classifier tests. The old `test_fix_c.py`, `test_perf_smoke.py`, `test_open_report.py`, `test_premarket_job.py` get rewritten against the new module API.

**Gate:** new report snapshot tests pass; morning report byte-equal across same-date renders; pre-market pipeline (08:30 → 09:00 → 09:15) covered by e2e test.

### Phase 5 — Split `telegram/` (transport vs. handlers)
- Rich-message primitives → `telegram/rich/{detect,split,send}.py`.
- Handlers → `telegram/handlers/{core,report,search}.py`.
- Search → `telegram/search/{lookup,keyboards,detail}.py`.
- Delivery → `telegram/delivery.py` (send_to_owner, broadcast, send_report_to_all).
- Menu button → `telegram/menu.py`.
- Application factory → `telegram/app.py`.

**Gate:** all Telegram commands respond; bot menu button still appears; Rich Messages still render.

### Phase 6 — Split `scheduler/` + thin CLI + test reorg
- Scheduler jobs grouped into `scheduler/jobs.py`, retry logic into `scheduler/sync_cycle.py`, parsing into `scheduler/timeparse.py`.
- `main.py` shrinks to ~80 LoC: argparse + asyncio + lock.
- CLI subcommands → `cli/cmd_*.py`.
- Tests reorganized to mirror new layout under `tests/{core,db,sources,analysis,reports,telegram,scheduler,cli,e2e}/`.
- `conftest.py` with shared fixtures at top level.
- Old `tests/test_*.py` files deleted (their coverage is in the new layout).

**Gate:** every cron job runs on schedule; e2e test covers full pipeline (sync → analysis → morning report → broadcast); `python main.py --sync --backfill --report --analyze` all work.

---

## 5. Future-Feature Slot Map (Locked Empty Packages)

Reserved packages created in Phase 1 as empty `__init__.py` files so future features plug in without directory churn:

| Future feature | Reserved slot |
|---|---|
| Options chain (NSE) | `src/marketmeter/sources/nse_options.py` |
| Multi-broker live | `src/marketmeter/sources/{zerodha,upstox,angel}.py` |
| ML scoring overlay | `src/marketmeter/analysis/ml_scoring.py` |
| Watchlists / portfolios | `src/marketmeter/db/watchlist_repo.py` + `src/marketmeter/reports/watchlist.py` + `src/marketmeter/telegram/handlers/watchlist.py` |
| Backtesting | `src/marketmeter/analysis/backtest/` |
| Web dashboard | `src/marketmeter/web/` (or sibling at project root) |
| Portfolio P&L | `src/marketmeter/db/portfolio_repo.py` + `src/marketmeter/reports/portfolio.py` |
| Alert rules engine | `src/marketmeter/alerts/` |

---

## 6. Current Module Map (Snapshot @ `ebaf301`)

Source of truth for what each file does today. Used during refactor to make sure no symbol is dropped.

| File | LoC | Responsibility | Internal deps |
|---|---:|---|---|
| `main.py` | 304 | CLI entry, signal handling, single-instance lock, asyncio | config, database, bot, scheduler |
| `config.py` | 166 | Constants & env-driven settings | — |
| `database.py` | 921 | All SQL (schema, migrations, CRUD for 9 tables, stats, cache) | config |
| `data_fetcher.py` | 433 | NSE BhavCopy download, classification, sync, backfill | config, database |
| `analyzer.py` | 536 | Indicator math + per-symbol + batch + outlook | config, database |
| `report_generator.py` | 804 | All human-readable messages | config, database, analyzer |
| `bot.py` | 498 | Telegram app wiring, command handlers, menu, Rich transport | config, database, search_handler |
| `search_handler.py` | 724 | /search flow + TradingView lookup + detail rendering | config, intraday_fetcher |
| `intraday_fetcher.py` | 239 | TradingView snapshot, 5-min aggregate, ingest | config, database |
| `premarket_report.py` | 124 | 09:00 live pre-market | config, database, bot, intraday_fetcher |
| `premarket_open_report.py` | 164 | 09:15 cross-check | config, database, bot, intraday_fetcher |
| `premarket_combined_report.py` | 364 | Combined historical+live | config, database, bot, intraday_fetcher |
| `scheduler.py` | 366 | APScheduler wiring, all cron jobs, sync retry | config, data_fetcher, analyzer, bot, 3× premarket |
| **TOTAL** | **5643** | | |

**Known duplication hotspots (de-dup target in Phase 4):**
- `_fmt` / `_signed_pct` / `_fmt_price` / `_fmt_num` / `_fmt_int` / `_fmt_mcap` / `_fmt_pct` repeated across `premarket_report.py`, `premarket_open_report.py`, `premarket_combined_report.py`, `search_handler.py`, `report_generator.py`.
- `_gap` / `_gap_pct` / `_vol_ratio` / `_gap_emoji` / `_vol_emoji` repeated across `premarket_open_report.py`, `premarket_combined_report.py`.
- `_obv_label`, `_macd_label`, `_bb_pos`, `_verdict`, `_rsi_signal` in `report_generator.py` and `premarket_combined_report.py`.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Beta drift from main (merge conflicts later) | Periodic `git merge main` into beta; refactor is mostly file moves, low conflict |
| `bhavcopy.db` orphan at `data/bhavcopy.db` | Note in Phase 2; remove if confirmed dead |
| Loss of public API during migration | `db/__init__.py` re-exports; `core/config.py` shim re-exports; deprecation cycle |
| Report byte-equality drift | Snapshot tests in Phase 4; deterministic fixture inputs |
| Timezone handling regressions | `core/time.py` central; IST-only; tests assert `Asia/Kolkata` |
| SQLite WAL/lock issues with new modules | All DB access through single `db/connection.py` factory |
| Single-instance lock after refactor | `core/concurrency.py` is the only owner; tests assert it |
| Bot downtime during deployment of beta → main | Merge only when beta e2e suite is GREEN; deploy as atomic swap |

---

## 8. Status Tracker

| Phase | Status | Commit | Notes |
|---|---|---|---|
| 0 — baseline + this doc | 🟡 in progress | (this commit) | |
| 1 — skeleton + core/ | ⏸ pending | — | |
| 2 — db/ split | ⏸ pending | — | |
| 3 — sources/ split | ⏸ pending | — | |
| 4 — analysis/ + reports/ split | ⏸ pending | — | |
| 5 — telegram/ split | ⏸ pending | — | |
| 6 — scheduler/ + cli/ + tests reorg | ⏸ pending | — | |

Legend: ⏸ pending · 🟡 in progress · ✅ done · ❌ blocked

---

## 9. End-to-End Acceptance (Beta → Main Merge Gate)

Beta is mergeable to main when **all** are true:

1. `python main.py` boots the bot on beta without error.
2. `pytest tests/` is fully GREEN (the new suite, not the old one).
3. `python main.py --sync` performs one sync cycle against NSE and exits 0.
4. `python main.py --analyze` runs batch analysis and exits 0.
5. `python main.py --report` generates and broadcasts morning report and exits 0.
6. `python main.py --status` returns.
7. Every `/command` (`/start /help /status /indicators /subscribe /unsubscribe /report /search`) responds correctly when invoked in a real chat (manual smoke).
8. Scheduled cron jobs all run (verified by log markers for each).
9. `git diff main..beta --stat` shows only the intended file moves + new packages; no accidental logic edits on `main`.
10. You sign off after a live walkthrough.

---

**End of plan.** This file is the contract. If I forget anything mid-refactor, you can point me back here.