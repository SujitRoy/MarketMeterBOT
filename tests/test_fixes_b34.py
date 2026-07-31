"""Bugs #3/#4 — sync_retry re-arm gating and tz-aware clock. RED pre-fix."""
import os, sys, unittest, inspect, asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler as s  # noqa: E402


class TestBug3_RetryKeepsRearming(unittest.TestCase):
    """If NSE still hasn't published (not_available non-empty) after a partial sync,
    the retry loop must re-arm — even if some rows did land (total_records > 0)."""

    def test_rearm_despite_positive_total_records_when_dates_still_pending(self):
        async def run():
            ctx = MagicMock()
            ctx.application = MagicMock()
            # Simulate _run_sync_cycle returning inserted rows AND pending dates.
            fake_result = {'total_records': 2407, 'success': 1,
                           'not_available': ['2026-07-31']}
            with patch.object(s, '_run_sync_cycle',
                              new=AsyncMock(return_value=fake_result)), \
                 patch.object(s, '_schedule_sync_retry', return_value=True) as m_rearm, \
                 patch.object(s, 'send_to_owner', new=AsyncMock()):
                await s._sync_retry_job(ctx)
            return m_rearm.called

        rearmed = asyncio.run(run())
        self.assertTrue(rearmed,
                        "retry gave up at total_records>0 while dates were still pending "
                        "— will never fetch them until tomorrow's 18:30")


class TestBug4_TzAwareRetryClock(unittest.TestCase):
    def test_retry_cutoff_uses_ist_not_naive_local_clock(self):
        src = inspect.getsource(s._schedule_sync_retry)
        # The naive `datetime.now()` breaks if the host is ever not IST.
        self.assertNotIn("datetime.now().hour", src,
                         "retry cutoff reads the naive local clock; must be IST-aware")
        self.assertIn("IST", src, "_schedule_sync_retry should reference the IST tz")


if __name__ == '__main__':
    unittest.main(verbosity=2)
