"""
data_fetcher.py — Phase 3 backward-compatibility shim.

Phase 3 of the modular refactor moved every function in this file to
src/marketmeter/sources/nse.py. This shim re-exports the full public surface
so existing call sites that still do `from data_fetcher import X`
continue to work without changes.

Phase 6 (final cleanup) removes this shim once every caller is updated to
import from marketmeter.sources.nse directly.

No behaviour change. This file is a pure re-export module.
"""
from __future__ import annotations

from datetime import date, datetime  # noqa: F401  (test-back-compat: `df.date` and `df.datetime`)

# Re-import the trading calendar and NSE core functions from their canonical
# home. Anything that did `from data_fetcher import NSE_HOLIDAYS,
# is_trading_day, ...` still resolves; the names point at the same objects.
from marketmeter.core.errors import BhavcopyNotPublished  # noqa: F401
from marketmeter.core.time import (  # noqa: F401  (re-export)
    NSE_HOLIDAYS,
    is_nse_holiday,
    is_trading_day,
    is_weekend_or_holiday,
    get_trading_days,
)
from marketmeter.sources.nse import (  # noqa: F401  (re-export)
    classify_sync_status,
    fetch_bhavcopy_csv,
    transform_bhavcopy,
    download_bhavcopy_for_date,
    download_and_store_date,
    sync_incremental_data,
    backfill_historical_data,
)
# These are NOT used inside data_fetcher.py itself anymore — they were
# imported by the original module purely so `data_fetcher.X` worked as a
# patchable attribute for tests (e.g. test_fixes_b56 mocks
# `data_fetcher.insert_bhavcopy_batch`). Phase 6 retires the mocks; for
# now, the shim re-exposes them so the test suite stays GREEN.
from marketmeter.db import (  # noqa: F401  (test-back-compat only)
    insert_bhavcopy_batch,
    log_sync,
    get_last_synced_date,
    get_latest_trade_date,
    get_failed_syncs,
)

__all__ = [
    "BhavcopyNotPublished",
    "NSE_HOLIDAYS",
    "is_nse_holiday",
    "is_trading_day",
    "is_weekend_or_holiday",
    "get_trading_days",
    "classify_sync_status",
    "fetch_bhavcopy_csv",
    "transform_bhavcopy",
    "download_bhavcopy_for_date",
    "download_and_store_date",
    "sync_incremental_data",
    "backfill_historical_data",
    "insert_bhavcopy_batch",
    "log_sync",
    "get_last_synced_date",
    "get_latest_trade_date",
    "get_failed_syncs",
]