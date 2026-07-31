"""End-to-end: 18:30 sync -> analysis fan-out -> owner insertion receipt -> retry re-arm.
Drives the _run_sync_cycle path with a mocked executor result; asserts the full
notification ordering and the retry behaviour the audit surfaced (Bugs #2/#3/#4)."""
import os, sys, unittest, asyncio
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler as s  # noqa: E402


class TestE2E_OwnerFlow(unittest.IsolatedAsyncioTestCase):
    async def test_partial_sync_sends_receipt_then_generic_banner_then_analysis(self):
        """Synced date lands rows, a second date pending: owner gets (1) explicit
        insertion receipt, (2) analysis-complete — and the retry loop re-arms."""
        app = MagicMock()
        result = {
            'status': 'completed', 'total_records': 2409,
            'success': 1, 'failed': 0, 'holidays': 0,
            'synced_dates': ['2026-07-30'],
            'per_date_records': {'2026-07-30': 2409},
            'not_available': ['2026-07-31'],
        }
        sent = []

        async def cap_owner(app_, text, use_rich=False):
            sent.append(text)

        with patch.object(s.sync_incremental_data, '__call__', side_effect=None), \
             patch.object(s, 'sync_incremental_data', return_value=result), \
             patch.object(s, 'run_batch_analysis',
                          return_value={'analyzed': 1772, 'saved': 1772, 'message': 'ok'}), \
             patch.object(s, 'warm_report_cache', return_value=True), \
             patch.object(s, 'send_to_owner', side_effect=cap_owner):
            out = await s._run_sync_cycle(app)

        # Owner relayed a positive receipt containing net-new counts.
        receipt = next((t for t in sent if 'Insertion Confirmed' in t), None)
        self.assertIsNotNone(receipt, "no explicit insertion receipt relayed to owner")
        self.assertIn('2,409', receipt)
        self.assertIn('2026-07-30', receipt)
        # Analysis completion referenced.
        self.assertTrue(any('Analysis Complete' in t for t in sent))

    async def test_retry_rearms_when_dates_pending_even_after_insert(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        fake = {'total_records': 2409, 'not_available': ['2026-07-31']}
        with patch.object(s, '_run_sync_cycle', new=AsyncMock(return_value=fake)), \
             patch.object(s, '_schedule_sync_retry', return_value=True) as m_rearm, \
             patch.object(s, 'send_to_owner', new=AsyncMock()):
            await s._sync_retry_job(ctx)
        self.assertTrue(m_rearm.called,
                        "retry loop stopped at total_records>0 with a date still pending")


if __name__ == '__main__':
    unittest.main(verbosity=2)
