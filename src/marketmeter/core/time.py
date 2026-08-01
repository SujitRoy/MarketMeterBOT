"""
core/time — timezone-aware IST clock and NSE trading calendar.

Centralised here so that:
- `is_trading_day` / `is_nse_holiday` / `NSE_HOLIDAYS` are no longer scattered
  across data_fetcher.py (Phase 3 will physically move them; Phase 1 re-exports).
- `now_ist()` is the single source of "wall clock time" for the whole app.
- Callers stop importing from `datetime` directly for "what time is it" questions.

The original NSE_HOLIDAYS set and is_trading_day/is_nse_holiday/is_weekend_or_holiday/get_trading_days
are imported from data_fetcher for backward compatibility, but canonical
locations live here. data_fetcher is unchanged in Phase 1.
"""
from __future__ import annotations

import datetime as dt
from datetime import date, datetime, timezone
from typing import List

# Re-export the trading-calendar symbols from data_fetcher so any new code
# can `from marketmeter.core.time import is_trading_day, NSE_HOLIDAYS` while
# Phase 3 hasn't physically moved them yet.
#
# Keeping the source-of-truth in data_fetcher for Phase 1 means a single
# PR moves them; risk is limited to "two import paths work, same answer".
from data_fetcher import (  # noqa: F401  (re-export)
    NSE_HOLIDAYS,
    is_nse_holiday,
    is_trading_day,
    is_weekend_or_holiday,
    get_trading_days,
)

# IST = UTC+5:30. No DST in India. Working in fixed offset avoids a zoneinfo
# dependency on this 954 MB host and survives container restarts.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")


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
    """Parse 'HH:MM' into a datetime.time. Used by scheduler job registration."""
    return datetime.strptime(time_str, "%H:%M").time()


def is_market_open_now() -> bool:
    """True when current IST time falls within 09:15-15:30 on a trading day."""
    if not is_trading_day(today_ist()):
        return False
    h, m = ist_hour_minute()
    minutes = h * 60 + m
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30


def trading_days_between(start: date, end: date) -> List[date]:
    """List of NSE trading days in [start, end] inclusive. Alias for
    data_fetcher.get_trading_days; kept here so callers don't need to import
    from data_fetcher."""
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
