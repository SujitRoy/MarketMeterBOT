"""
reports — public surface for the reports package.

Phase 4 layout:
    reports/
    ├── formatters.py        — None-safe numeric/string helpers
    ├── labels.py            — categorical signal labels (emoji, words)
    ├── morning.py           — 8:30 AM morning report
    ├── premarket_live.py    — 09:00 IST live snapshot
    ├── premarket_open.py    — 09:15 IST cross-check
    ├── premarket_combined.py — 09:00 historical + live merge
    ├── status.py            — /status, sync status, sync failure
    ├── reference.py         — /indicators, /welcome, /help
    └── cache.py             — warm_report_cache + no-data report

This __init__.py re-exports the public surface so callers can do:

    from marketmeter.reports import generate_morning_report, warm_report_cache
    from marketmeter.reports.formatters import fmt
    from marketmeter.reports.labels import obv_label
"""
from __future__ import annotations

from .formatters import (
    fmt, price_rupees, price_rupees_compact, signed_pct,
    fmt_int, fmt_mcap, gap_pct, vol_ratio, _has,
    NA_DASH, NA_EMDASH,
)
from .labels import (
    obv_label, macd_label, bb_pos, narrative,
    rvol_signal, tv_rating_label,
    rsi_signal, gap_emoji, vol_emoji, verdict,
    market_state, position_in_range, position_label,
)
from . import morning, cache, status, reference, premarket_live, premarket_open, premarket_combined
from .morning import generate_morning_report
from .cache import warm_report_cache, _no_data_report, _NO_DATA_MARKER
from marketmeter.analysis import get_analysis_aggregate  # for test patchability via reports
from .status import (
    generate_sync_status_message, generate_sync_failure_alert,
    generate_status_message,
)
from .reference import (
    generate_indicators_message, generate_welcome_message, generate_help_message,
)
from .premarket_live import build_premarket_message, send_premarket_report
from .premarket_open import (
    build_open_crosscheck, send_open_crosscheck_report, OPEN_REPORT_TOP_N,
)
from .premarket_combined import (
    merge_historical_live, build_combined_report,
    send_combined_premarket_report,
    HISTORICAL_COLS, LIVE_COLS, MERGED_TABLE_COLS,
)

__all__ = [
    # formatters
    "fmt", "price_rupees", "price_rupees_compact", "signed_pct",
    "fmt_int", "fmt_mcap", "gap_pct", "vol_ratio", "_has",
    "NA_DASH", "NA_EMDASH",
    # labels
    "obv_label", "macd_label", "bb_pos", "narrative",
    "rvol_signal", "tv_rating_label",
    "rsi_signal", "gap_emoji", "vol_emoji", "verdict",
    "market_state", "position_in_range", "position_label",
    # sub-modules
    "morning", "cache", "status", "reference",
    "premarket_live", "premarket_open", "premarket_combined",
    # morning
    "generate_morning_report",
    "get_analysis_aggregate",
    # cache
    "warm_report_cache", "_no_data_report", "_NO_DATA_MARKER",
    # status
    "generate_sync_status_message", "generate_sync_failure_alert",
    "generate_status_message",
    # reference
    "generate_indicators_message", "generate_welcome_message", "generate_help_message",
    # premarket
    "build_premarket_message", "send_premarket_report",
    "build_open_crosscheck", "send_open_crosscheck_report", "OPEN_REPORT_TOP_N",
    "merge_historical_live", "build_combined_report",
    "send_combined_premarket_report",
    "HISTORICAL_COLS", "LIVE_COLS", "MERGED_TABLE_COLS",
]