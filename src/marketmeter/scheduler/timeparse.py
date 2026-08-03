"""
scheduler/timeparse — time parsing utilities.
"""
from __future__ import annotations

from datetime import timezone, timedelta

# IST = UTC+5:30. No DST in India.
IST = timezone(timedelta(hours=5, minutes=30))


def _parse_time(time_str: str):
    """Parse 'HH:MM' string to a time object stamped with IST.

    Returning a tz-aware time is what tells PTB's JobQueue to fire at that
    wall-clock hour in IST rather than in UTC (the scheduler's default).
    """
    hour, minute = map(int, time_str.split(':'))
    from datetime import time as dt_time
    return dt_time(hour=hour, minute=minute, tzinfo=IST)


__all__ = ["_parse_time"]