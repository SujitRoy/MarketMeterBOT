"""
MarketMeter — persistence layer.

Phase 2 split: the original 921-LoC /database.py became 8 focused modules:

    db/
    ├── connection.py     — get_connection() factory (single SQLite connection owner)
    ├── schema.py         — init_db, init_intraday_tables, _migrate_analysis_columns
    ├── bhavcopy_repo.py  — bhavcopy CRUD
    ├── analysis_repo.py  — daily_analysis CRUD
    ├── sync_repo.py      — sync_log CRUD
    ├── cache_repo.py     — report_cache CRUD
    ├── subscriber_repo.py — subscribers CRUD
    ├── stats_repo.py     — stats_cache + vacuum_db
    ├── intraday_repo.py  — intraday_candles / intraday_alerts / tracked_symbols CRUD
    └── migrations/       — future home for versioned .sql files (Phase 6)

This __init__.py re-exports the full public surface so:

    from marketmeter.db import init_db, get_db_stats, ...

works exactly the same as the old

    from database import init_db, get_db_stats, ...

The /database.py shim at the project root also re-exports from here so legacy
callers like `from database import insert_bhavcopy_batch` keep working
through Phase 6, when the shim is retired.
"""
from __future__ import annotations

from .connection import get_connection
from .schema import init_db, init_intraday_tables, _migrate_analysis_columns
from .bhavcopy_repo import (
    insert_bhavcopy_batch,
    get_stock_history,
    get_all_symbols,
    get_latest_trade_date,
    get_date_range,
    get_total_records,
    get_unique_symbols_count,
)
from .analysis_repo import (
    save_daily_analysis,
    get_latest_analysis,
    get_resolved_analysis_date,
    get_analysis_by_recommendation,
)
from .sync_repo import (
    log_sync,
    get_last_synced_date,
    get_sync_status,
    get_failed_syncs,
    get_holiday_dates,
)
from .cache_repo import (
    get_cached_report,
    put_cached_report,
    invalidate_report_cache,
)
from .subscriber_repo import (
    add_subscriber,
    remove_subscriber,
    get_active_subscribers,
    get_all_subscribers,
    get_subscriber_count,
)
from .stats_repo import (
    update_stats_cache_after_insert,
    init_stats_cache,
    _init_stats_cache_impl,
    get_db_stats,
    vacuum_db,
)
from .intraday_repo import (
    upsert_intraday_candles,
    get_intraday_candles,
    add_tracked_symbol,
    get_tracked_symbols,
    remove_tracked_symbol,
    log_intraday_alert,
    get_recent_alerts,
    prune_old_intraday,
)

__all__ = [
    # connection
    "get_connection",
    # schema
    "init_db", "init_intraday_tables", "_migrate_analysis_columns",
    # bhavcopy
    "insert_bhavcopy_batch", "get_stock_history", "get_all_symbols",
    "get_latest_trade_date", "get_date_range",
    "get_total_records", "get_unique_symbols_count",
    # analysis
    "save_daily_analysis", "get_latest_analysis",
    "get_resolved_analysis_date", "get_analysis_by_recommendation",
    # sync
    "log_sync", "get_last_synced_date",
    "get_sync_status", "get_failed_syncs", "get_holiday_dates",
    # cache
    "get_cached_report", "put_cached_report", "invalidate_report_cache",
    # subscribers
    "add_subscriber", "remove_subscriber",
    "get_active_subscribers", "get_all_subscribers", "get_subscriber_count",
    # stats
    "update_stats_cache_after_insert", "init_stats_cache",
    "_init_stats_cache_impl", "get_db_stats", "vacuum_db",
    # intraday
    "upsert_intraday_candles", "get_intraday_candles",
    "add_tracked_symbol", "get_tracked_symbols", "remove_tracked_symbol",
    "log_intraday_alert", "get_recent_alerts", "prune_old_intraday",
]