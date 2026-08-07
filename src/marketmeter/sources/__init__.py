"""
MarketMeter — external data sources.

Phase 3 split: the original /data_fetcher.py (NSE) and /intraday_fetcher.py
(TradingView) plus tv_symbol_lookup from /search_handler.py became:

    sources/
    ├── nse.py          — NSE BhavCopy download, sync, backfill
    ├── tradingview.py  — TradingView scanner + symbol search
    └── __init__.py     — this file (re-exports the public surface)

The /data_fetcher.py and /intraday_fetcher.py shims at the project root
re-export from here so existing callers keep working through Phase 6.
"""
from __future__ import annotations

from . import nse
from . import tradingview

# Re-export the trading-calendar symbols through sources.nse so a caller that
# says `from marketmeter.sources import is_trading_day, NSE_HOLIDAYS` works.
# data_fetcher.py's shim also exposes them, but going through sources makes
# the canonical chain explicit.
from marketmeter.core.time import (
    NSE_HOLIDAYS,
    is_nse_holiday,
    is_trading_day,
    is_weekend_or_holiday,
    get_trading_days,
)

__all__ = [
    # sub-modules (callers can use `from marketmeter.sources import nse`)
    "nse", "tradingview",
    # trading calendar (re-exported from core.time)
    "NSE_HOLIDAYS", "is_nse_holiday", "is_trading_day",
    "is_weekend_or_holiday", "get_trading_days",
]