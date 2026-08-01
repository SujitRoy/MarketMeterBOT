"""
core/errors — typed exception hierarchy for the MarketMeter stack.

Phase 1 introduces the base hierarchy and moves `BhavcopyNotPublished` from
data_fetcher.py into here. data_fetcher.py adopts a back-compat alias so
existing `except BhavcopyNotPublished` blocks continue to work in Phase 1.
Phase 3 retires the alias.

Hierarchy:
    MarketMeterError
    ├── DataSourceError
    │   ├── BhavcopyNotPublished
    │   ├── BhavcopyFetchError
    │   └── TradingViewError
    │       ├── TradingViewAuthError
    │       └── TradingViewRateLimitError
    ├── AnalysisError
    │   └── InsufficientDataError
    └── ReportError
        └── NoDataForDateError
"""
from __future__ import annotations


class MarketMeterError(Exception):
    """Base for every error raised by MarketMeter code. Catch this to trap
    any in-process failure, but prefer the more specific subclasses below."""


class DataSourceError(MarketMeterError):
    """Any external data source (NSE, TradingView) failed to deliver data."""


class BhavcopyNotPublished(DataSourceError):
    """NSE returned 404: the file does not exist yet (or the date is a holiday).

    Moved from data_fetcher.py on 2026-08-01 (Phase 1). Original module
    re-exports the same class object so `except BhavcopyNotPublished` keeps
    matching across both locations.
    """


class BhavcopyFetchError(DataSourceError):
    """Network/HTTP failure while fetching the BhavCopy."""


class TradingViewError(DataSourceError):
    """Base for TradingView-specific failures."""


class TradingViewAuthError(TradingViewError):
    """TradingView session cookie rejected / expired."""


class TradingViewRateLimitError(TradingViewError):
    """TradingView rate-limited or temporarily blocked."""


class AnalysisError(MarketMeterError):
    """Analysis pipeline failure (input data bad, math overflow, etc.)."""


class InsufficientDataError(AnalysisError):
    """Not enough bars to compute the requested indicator."""


class ReportError(MarketMeterError):
    """Report rendering failure."""


class NoDataForDateError(ReportError):
    """No analysis rows for the requested date — triggers the no-data report."""


__all__ = [
    "MarketMeterError",
    "DataSourceError",
    "BhavcopyNotPublished",
    "BhavcopyFetchError",
    "TradingViewError",
    "TradingViewAuthError",
    "TradingViewRateLimitError",
    "AnalysisError",
    "InsufficientDataError",
    "ReportError",
    "NoDataForDateError",
]
