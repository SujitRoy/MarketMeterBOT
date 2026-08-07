"""
core/time — timezone-aware IST clock and NSE trading calendar.

Centralised here so that:
- `is_trading_day` / `is_nse_holiday` / `NSE_HOLIDAYS` are the single source
  of truth.
- `now_ist()` is the single source of "wall clock time" for the whole app.
- Callers stop importing from `datetime` directly for "what time is it" questions.

NSE_HOLIDAYS is loaded from data/nse_holidays.json (data, not code).
Uses stdlib zoneinfo (Python 3.9+) for IST timezone.
"""
from __future__ import annotations

import json
import datetime as dt
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import List, Set

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Load NSE holidays from JSON file (CM segment)
_HOLIDAYS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "nse_holidays.json"
_NSE_HOLIDAYS: Set[str] = set()
if _HOLIDAYS_PATH.exists():
    try:
        with _HOLIDAYS_PATH.open() as f:
            data = json.load(f)
        for year_list in data.values():
            _NSE_HOLIDAYS.update(year_list)
    except Exception:
        pass  # fall back to empty set; is_nse_holiday will rely on weekend check


def is_nse_holiday(d: date) -> bool:
    """True when NSE is closed and publishes no BhavCopy that day."""
    return d.weekday() >= 5 or d.isoformat() in _NSE_HOLIDAYS


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


# ── Wall-clock helpers ────────────────────────────────────────────────

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


def parse_ist_time(time_str: str) -> time:
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


# Expose the loaded holiday set for callers that need it
NSE_HOLIDAYS = _NSE_HOLIDAYS


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