"""
Time Utilities
Timezone-aware time handling for IST.
"""
import datetime
from datetime import date, datetime, time, timedelta

import pytz

# IST timezone
IST = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    """Get current time in IST."""
    return datetime.now(IST)


def today_ist() -> date:
    """Get today's date in IST."""
    return now_ist().date()


def parse_time_str(time_str: str) -> time:
    """Parse HH:MM time string."""
    return time.fromisoformat(time_str)


def is_market_hours(dt: datetime = None) -> bool:
    """Check if datetime is within market hours (09:15-15:30 IST)."""
    dt = dt or now_ist()
    if dt.tzinfo is None:
        dt = IST.localize(dt)

    market_open = time(9, 15)
    market_close = time(15, 30)
    current_time = dt.time()

    return market_open <= current_time <= market_close


def is_pre_market(dt: datetime = None) -> bool:
    """Check if datetime is pre-market (09:00-09:15 IST)."""
    dt = dt or now_ist()
    if dt.tzinfo is None:
        dt = IST.localize(dt)

    pre_open = time(9, 0)
    market_open = time(9, 15)
    current_time = dt.time()

    return pre_open <= current_time < market_open


def is_trading_day(dt: date = None) -> bool:
    """Check if date is a trading day (weekday, not holiday)."""
    from src.data.fetchers import is_trading_day as check_trading_day
    dt = dt or today_ist()
    return check_trading_day(dt)


def next_trading_day(dt: date = None) -> date:
    """Get next trading day after given date."""
    dt = dt or today_ist()
    next_day = dt + timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += timedelta(days=1)
    return next_day


def previous_trading_day(dt: date = None) -> date:
    """Get previous trading day before given date."""
    dt = dt or today_ist()
    prev_day = dt - timedelta(days=1)
    while not is_trading_day(prev_day):
        prev_day -= timedelta(days=1)
    return prev_day


def format_ist(dt: datetime, fmt: str = "%d %b %Y, %H:%M IST") -> str:
    """Format datetime in IST."""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime(fmt)


def time_until(target_time: time, dt: datetime = None) -> timedelta:
    """Get time until target time today (or tomorrow if passed)."""
    dt = dt or now_ist()
    if dt.tzinfo is None:
        dt = IST.localize(dt)

    target_dt = dt.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)

    if target_dt <= dt:
        target_dt += timedelta(days=1)

    return target_dt - dt


def get_market_schedule() -> dict:
    """Get today's market schedule."""
    today = today_ist()
    is_trading = is_trading_day(today)

    return {
        "date": today.isoformat(),
        "is_trading_day": is_trading,
        "market_open": "09:15",
        "market_close": "15:30",
        "pre_market_start": "09:00",
        "time_until_open": str(time_until(time(9, 15))) if is_trading else None,
        "time_until_close": str(time_until(time(15, 30))) if is_trading and is_market_hours() else None,
    }
