"""Fix-driven tests. One test bundle per bug, RED first, then GREEN after fix."""
import os, sys, unittest
from datetime import date

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_fetcher as df  # noqa: E402


class TestBug1_HolidayCalendar(unittest.TestCase):
    """Weekday NSE holidays must NOT be trading days and must classify as 'holiday'."""

    # NSE trading holidays that fall on Monday-Friday across 2024-2026
    WEEKDAY_HOLIDAYS = [
        date(2024, 3, 25),   # Holi (Mon)
        date(2024, 10, 2),   # Gandhi Jayanti (Wed)
        date(2025, 8, 15),   # Independence Day (Fri)
        date(2025, 10, 2),   # Dussehra (Thu)
        date(2026, 1, 26),   # Republic Day (Mon)
        date(2026, 10, 2),   # Gandhi Jayanti (Fri)
    ]

    def test_weekday_holidays_are_not_trading_days(self):
        for d in self.WEEKDAY_HOLIDAYS:
            with self.subTest(d=d, wd=d.weekday()):
                self.assertLess(d.weekday(), 5, "test premise: must be a weekday")
                self.assertFalse(df.is_trading_day(d),
                                 f"{d} is an NSE holiday but is_trading_day returned True")

    def test_weekday_holidays_classify_as_holiday_not_not_available(self):
        for d in self.WEEKDAY_HOLIDAYS:
            s = df.classify_sync_status(d, "NSE has not published (HTTP 404)")
            self.assertEqual(s, 'holiday',
                             f"{d} NSE holiday misclassified as '{s}' → becomes an immortal retry date")

    def test_normal_weekday_still_trading_day(self):
        self.assertTrue(df.is_trading_day(date(2026, 7, 30)))  # known synced trading day (Thu)
        s = df.classify_sync_status(date(2026, 7, 31), "NSE has not published (HTTP 404)")
        self.assertEqual(s, 'not_available', "a real open weekday pending publish must stay retryable")


if __name__ == '__main__':
    unittest.main(verbosity=2)
