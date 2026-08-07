"""
tests/core/test_time.py — tests for marketmeter/core/time.py.

Phase 7 §3 mandate: "Timezone handling tests (core/time.py central; IST-only)."

These tests pin the IST timezone definition and the trading-calendar
helpers (is_trading_day, is_nse_holiday, get_trading_days).

The tests are pure — no DB, no network — so they run in microseconds.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# Ensure src/ is on sys.path before any marketmeter import.
_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Env vars BEFORE config.py is imported.
os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

from marketmeter.core.time import (
    IST, NSE_HOLIDAYS,
    is_trading_day, is_nse_holiday, is_weekend_or_holiday,
    get_trading_days, parse_ist_time,
)


class TestIstTimezone:
    """IST = UTC+5:30, no DST. Pin the offset value."""

    def test_ist_offset_is_5_30(self):
        # ZoneInfo.utcoffset(None) returns None; pass a datetime
        dt = datetime(2026, 1, 1, tzinfo=IST)
        assert dt.utcoffset() == timedelta(hours=5, minutes=30)

    def test_ist_is_fixed_offset(self):
        # No DST in India
        july = datetime(2026, 7, 15, tzinfo=IST)
        january = datetime(2026, 1, 15, tzinfo=IST)
        assert july.utcoffset() == january.utcoffset() == timedelta(hours=5, minutes=30)


class TestNseHolidays:
    """The NSE_HOLIDAYS set must contain at least the 2024-2026 window
    holidays. It is a static set — adding a new holiday means editing the
    source."""

    def test_nse_set_is_nonempty(self):
        # 44 holidays were seeded in Phase 1 (2024-2026 window)
        assert len(NSE_HOLIDAYS) >= 40

    def test_nse_dates_are_iso_strings(self):
        for h in list(NSE_HOLIDAYS)[:5]:
            # ISO format: YYYY-MM-DD
            assert len(h) == 10
            assert h[4] == "-" and h[7] == "-"

    def test_republic_day_2026_is_holiday(self):
        # 2026-01-26 is Republic Day per the NSE_HOLIDAYS set
        assert "2026-01-26" in NSE_HOLIDAYS

    def test_independence_day_2026_is_holiday(self):
        assert "2026-08-15" in NSE_HOLIDAYS


class TestIsNseHoliday:
    def test_weekend_is_holiday(self):
        # 2026-01-03 is a Saturday
        assert is_nse_holiday(date(2026, 1, 3)) is True
        assert is_nse_holiday(date(2026, 1, 4)) is True  # Sunday

    def test_weekday_in_set_is_holiday(self):
        # 2026-01-26 (Monday) is Republic Day → holiday
        assert is_nse_holiday(date(2026, 1, 26)) is True

    def test_weekday_not_in_set_is_not_holiday(self):
        # 2026-03-04 is a Wednesday not in NSE_HOLIDAYS
        assert is_nse_holiday(date(2026, 3, 4)) is False


class TestIsTradingDay:
    """is_trading_day = NOT (weekend OR NSE holiday)."""

    def test_normal_weekday_is_trading_day(self):
        # 2026-08-03 is a Monday not in NSE_HOLIDAYS
        assert is_trading_day(date(2026, 8, 3)) is True

    def test_weekend_is_not_trading_day(self):
        assert is_trading_day(date(2026, 8, 1)) is False  # Saturday
        assert is_trading_day(date(2026, 8, 2)) is False  # Sunday

    def test_holiday_is_not_trading_day(self):
        # 2026-01-26 is Republic Day (Monday)
        assert is_trading_day(date(2026, 1, 26)) is False

    def test_consistency_with_is_nse_holiday(self):
        # is_trading_day(v) == NOT is_nse_holiday(v)
        for d in [date(2026, 7, 1), date(2026, 8, 15), date(2026, 1, 26), date(2026, 7, 4)]:
            assert is_trading_day(d) is (not is_nse_holiday(d))


class TestIsWeekendOrHoliday:
    """is_weekend_or_holiday is an alias for is_nse_holiday."""

    def test_alias_behavior(self):
        for d in [date(2026, 1, 1), date(2026, 1, 26), date(2026, 8, 15)]:
            assert is_weekend_or_holiday(d) == is_nse_holiday(d)


class TestGetTradingDays:
    """Returns every weekday in [start, end] that is not an NSE holiday."""

    def test_one_week_returns_five_days(self):
        # 2026-08-03 (Mon) to 2026-08-07 (Fri) → 5 trading days
        days = get_trading_days(date(2026, 8, 3), date(2026, 8, 7))
        assert len(days) == 5

    def test_excludes_weekends(self):
        days = get_trading_days(date(2026, 8, 1), date(2026, 8, 31))
        for d in days:
            assert d.weekday() < 5  # Mon=0..Fri=4

    def test_excludes_holidays(self):
        # 2026-01-26 is Republic Day (a Monday holiday)
        days = get_trading_days(date(2026, 1, 26), date(2026, 1, 26))
        assert days == []

    def test_empty_range(self):
        # start > end → empty
        days = get_trading_days(date(2026, 8, 10), date(2026, 8, 1))
        assert days == []


class TestParseIstTime:
    """Parse 'HH:MM' strings into an IST-aware time."""

    def test_basic(self):
        t = parse_ist_time("09:30")
        assert t == time(9, 30, tzinfo=IST)

    def test_has_correct_timezone(self):
        t = parse_ist_time("15:45")
        assert t.tzinfo == IST
        # time.utcoffset() returns None without a datetime; check via datetime
        dt = datetime.combine(date.today(), t)
        assert dt.utcoffset() == timedelta(hours=5, minutes=30)

    def test_midnight(self):
        t = parse_ist_time("00:00")
        assert t == time(0, 0, tzinfo=IST)

    def test_end_of_day(self):
        t = parse_ist_time("23:59")
        assert t == time(23, 59, tzinfo=IST)
