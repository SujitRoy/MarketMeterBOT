"""
Data Fetchers Package
All data source fetchers for MarketMeter.
"""
from src.data.fetchers.base import BaseFetcher, FetchResult, RateLimitedFetcher
from src.data.fetchers.nse_bhavcopy import (
    NSEBhavCopyFetcher,
    classify_sync_status,
    get_trading_days,
    is_nse_holiday,
    is_trading_day,
)
from src.data.fetchers.paytm_money import PaytmMoneyFetcher
from src.data.fetchers.tradingview_scanner import (
    TradingViewScannerFetcher,
    build_query,
    fetch_live_snapshot,
)

__all__ = [
    # Base
    "BaseFetcher",
    "FetchResult",
    "RateLimitedFetcher",

    # NSE BhavCopy
    "NSEBhavCopyFetcher",
    "is_nse_holiday",
    "is_trading_day",
    "get_trading_days",
    "classify_sync_status",

    # TradingView
    "TradingViewScannerFetcher",
    "fetch_live_snapshot",
    "build_query",

    # Paytm Money
    "PaytmMoneyFetcher",
]
