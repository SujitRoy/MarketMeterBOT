"""
reports — public surface for the reports package.

Layout:
    reports/
    ├── formatters.py        — None-safe numeric/string helpers
    ├── morning.py           — 8:30 AM morning report
    ├── premarket.py         — unified pre-market (live/open/combined)
    ├── status.py            — /status, sync status, sync failure
    └── cache.py             — warm_report_cache + no-data report
"""
from __future__ import annotations

from .formatters import (
    fmt, price_rupees, price_rupees_compact, signed_pct,
    fmt_int, fmt_mcap, gap_pct, vol_ratio, _has,
    NA_DASH, NA_EMDASH,
)
from . import morning, cache, status, premarket
from .morning import generate_morning_report
from .cache import warm_report_cache, _no_data_report
from marketmeter.analysis import get_analysis_aggregate  # for test patchability via reports
from .status import (
    generate_sync_status_message, generate_sync_failure_alert,
    generate_status_message,
)
from .premarket import send_premarket_report, OPEN_REPORT_TOP_N

__all__ = [
    # formatters
    "fmt", "price_rupees", "price_rupees_compact", "signed_pct",
    "fmt_int", "fmt_mcap", "gap_pct", "vol_ratio", "_has",
    "NA_DASH", "NA_EMDASH",
    # sub-modules
    "morning", "cache", "status", "premarket",
    # morning
    "generate_morning_report",
    "get_analysis_aggregate",
    # cache
    "warm_report_cache", "_no_data_report",
    # status
    "generate_sync_status_message", "generate_sync_failure_alert",
    "generate_status_message",
    # premarket
    "send_premarket_report", "OPEN_REPORT_TOP_N",
]