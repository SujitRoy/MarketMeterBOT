"""Regression: premarket job callback must be invocable the way JobQueue fires it
(i.e. with a CallbackContext), and must notify the owner on failure. On 2026-07-31
the job never executed (no 'Running job premarket_report' in logs) after a restart;
this test pins the fix regardless of the underlying scheduler edge."""
import os, sys, unittest, asyncio, inspect
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler as s           # noqa: E402
import premarket_report as pmr  # noqa: E402


class TestPremarketJobFires(unittest.TestCase):
    def test_job_callback_accepts_context_not_app(self):
        """JobQueue.run_daily always invokes callback(context). The callback must
        accept that context and reach the owner-notification send. If the module
        registered premarket by pointing at an `(app)`-shaped callback, a silent
        execution failure/exception path can swallow the run."""
        src_job = inspect.getsource(s._premarket_report_job) \
            if hasattr(s, '_premarket_report_job') else None
        self.assertIsNotNone(src_job,
                             "scheduler must define _premarket_report_job(context) — "
                             "it was missing, so JobQueue fired the (app)-shaped "
                             "send_premarket_report in a way that produced no execution trace")
        self.assertIn('context.application', src_job,
                      "premarket job callback must pull the app off context, like every other job")


class TestPremarketWrapperBehaviour(unittest.IsolatedAsyncioTestCase):
    async def test_wrapper_calls_reporter_with_app(self):
        ctx = MagicMock(); ctx.application = MagicMock()
        with patch.object(s, 'send_premarket_report', new=AsyncMock(return_value={'sent': 1})) as m, \
             patch.object(s, 'send_to_owner', new=AsyncMock()):
            await s._premarket_report_job(ctx)
        m.assert_awaited_once_with(ctx.application)

    async def test_wrapper_notifies_owner_when_zero_sent(self):
        ctx = MagicMock(); ctx.application = MagicMock()
        with patch.object(s, 'send_premarket_report', new=AsyncMock(return_value={'sent': 0})), \
             patch.object(s, 'send_to_owner', new=AsyncMock()) as m_owner:
            await s._premarket_report_job(ctx)
        self.assertTrue(m_owner.await_count >= 1,
                        "zero-send must still notify the owner (no silent miss)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
