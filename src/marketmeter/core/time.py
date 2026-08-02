"""
core/time — timezone-aware IST clock and NSE trading calendar.

Centralised here so that:
- `is_trading_day` / `is_nse_holiday` / `NSE_HOLIDAYS` are the single source
  of truth (Phase 2 promotion; previously re-exported from data_fetcher.py).
- `now_ist()` is the single source of "wall clock time" for the whole app.
- Callers stop importing from `datetime` directly for "what time is it" questions.

The NSE_HOLIDAYS set is a static roster CM segment holidays (2024-2026
window). Keeping it here makes this package a leaf: it depends only on stdlib
+ marketmeter.core.errors, never on data_fetcher.py. That breaks the
original Phase 1 circular import (data_fetcher -> database -> marketmeter.db
-> marketmeter.core -> data_fetcher) at its root.

Phase 3 will retire data_fetcher.py's local copies of these symbols and have
it import from marketmeter.core.time directly.
"""
from __future__ import annotations

import datetime as dt
from datetime import date, datetime, timezone
from typing import List

# IST = UTC+5:30. No DST in India. Working in fixed offset avoids a zoneinfo
# dependency on this 954 MB host and survives container restarts.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")


# NSE trading holidays (CM segment), kept as iso-strings so the "does NSE
# publish today?" decision is data-driven and never reaches the network on a
# known closed day. Without this, a closed Monday/Friday was downloaded,
# 404'd, then misclassified 'not_available' and retried forever.
# Populate one rolling year ahead; covers 2024-2026 sync window.
NSE_HOLIDAYS = {
    # 2024
    "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29", "2024-04-11",
    "2024-04-17", "2024-04-21", "2024-05-23", "2024-06-17", "2024-07-17",
    "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15", "2024-12-25",
    # 2025
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-18", "2025-05-01", "2025-08-15", "2025-10-01", "2025-10-02",
    "2025-10-21", "2025-10-22", "2025-11-05", "2025-12-25",
    # 2026 (extend each year; a date not listed falls back to the 404 path)
    "2026-01-26", "2026-02-17", "2026-03-10", "2026-03-20", "2026-03-31",
    "2026-04-02", "2026-04-13", "2026-05-01", "2026-06-26", "2026-08-15",
    "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-09", "2026-12-25",
}


def is_nse_holiday(d: date) -> bool:
    """True when NSE is closed and publishes no BhavCopy that day."""
    return d.weekday() >= 5 or d.isoformat() in NSE_HOLIDAYS


def is_trading_day(d: date) -> bool:
    """Check if a date is an NSE trading day (weekday and not a holiday)."""
    return not is_nse_holiday(d)


def is_weekend_or_holiday(d: date) -> bool:
    """True for weekends and NSE holidays (both closed)."""
    return is_nse_holiday(d)


def get_trading_days(start_date: date, end_date: date) -> List[date]:
    """Get list of all weekdays between start and end (inclusive)."""
    current = start_date
    trading_days = []
    while current <= end_date:
        if is_trading_day(current):
            trading_days.append(current)
        current += dt.timedelta(days=1)
    return trading_days


# ── Wall-clock helpers (Phase 2) ──────────────────────────────────────

def now_ist() -> datetime:
    """Wall-clock time in IST, tz-aware. Use this instead of datetime.now()."""
    return datetime.now(tz=IST)


def today_ist() -> date:
    """Today's date in IST (not UTC)."""
    return now_ist().date()


def to_ist(d: datetime) -> datetime:
    """Convert a tz-aware datetime to IST. Naive datetimes are assumed UTC."""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(IST)


def ist_hour_minute() -> tuple[int, int]:
    """Return (hour, minute) of the current IST wall clock."""
    n = now_ist()
    return n.hour, n.minute


def parse_ist_time(time_str: str) -> dt.time:
    """Parse 'HH:MM' into an IST-aware datetime.time.

    Returning a tz-aware time is what tells PTB's JobQueue to fire at that
    wall-clock hour in IST rather than in UTC (the scheduler's default).
    """
    t = datetime.strptime(time_str, "%H:%M").time()
    return t.replace(tzinfo=IST)


def is_market_open_now() -> bool:
    """True when current IST time falls within 09:15-15:30 on a trading day."""
    if not is_trading_day(today_ist()):
        return False
    h, m = ist_hour_minute()
    minutes = h * 60 + m
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30


def trading_days_between(start: date, end: date) -> List[date]:
    """List of NSE trading days in [start, end] inclusive. Alias for
    get_trading_days; kept here so callers don't need to import from
    data_fetcher."""
    return get_trading_days(start, end)


__all__ = [
    "IST",
    "NSE_HOLIDAYS",
    "now_ist",
    "today_ist",
    "to_ist",
    "ist_hour_minute",
    "parse_ist_time",
    "is_trading_day",
    "is_nse_holiday",
    "is_weekend_or_holiday",
    "is_market_open_now",
    "trading_days_between",
    "get_trading_days",
]