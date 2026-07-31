"""
Data Package
Data fetching, transformation, and sync modules.
"""
from src.data.fetchers import (
    BaseFetcher,
    FetchResult,
    NSEBhavCopyFetcher,
    PaytmMoneyFetcher,
    RateLimitedFetcher,
    TradingViewScannerFetcher,
    classify_sync_status,
    fetch_live_snapshot,
    get_trading_days,
    is_nse_holiday,
    is_trading_day,
)
from src.data.sync import (
    BackfillEngine,
    BackfillResult,
    RetryConfig,
    RetryHandler,
    SyncEngine,
    SyncResult,
)
from src.data.transformers import (
    add_derived_columns,
    filter_by_gap,
    filter_by_rsi_shift,
    filter_by_volume_surge,
    filter_valid_rows,
    merge_historical_live,
    prepare_for_analysis,
    transform_bhavcopy,
    transform_live_snapshot,
)

__all__ = [
    # Fetchers
    "BaseFetcher",
    "FetchResult",
    "RateLimitedFetcher",
    "NSEBhavCopyFetcher",
    "TradingViewScannerFetcher",
    "fetch_live_snapshot",
    "is_nse_holiday",
    "is_trading_day",
    "get_trading_days",
    "classify_sync_status",
    "PaytmMoneyFetcher",

    # Transformers
    "transform_bhavcopy",
    "prepare_for_analysis",
    "filter_valid_rows",
    "add_derived_columns",
    "transform_live_snapshot",
    "merge_historical_live",
    "filter_by_gap",
    "filter_by_volume_surge",
    "filter_by_rsi_shift",

    # Sync
    "SyncEngine",
    "SyncResult",
    "BackfillEngine",
    "BackfillResult",
    "RetryHandler",
    "RetryConfig",
]
