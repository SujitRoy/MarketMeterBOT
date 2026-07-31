"""09:15 Market-Open Cross-Check report — design + send. RED pre-implementation."""
import os, sys, unittest, asyncio
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOpenCrossCheckReport(unittest.TestCase):
    def setUp(self):
        import importlib
        self.mod = importlib.import_module('premarket_open_report')

    def test_module_and_entrypoints_exist(self):
        self.assertTrue(hasattr(self.mod, 'send_open_crosscheck_report'))
        self.assertTrue(hasattr(self.mod, 'build_open_crosscheck'))

    def test_merges_historical_and_live_with_gap_and_score(self):
        historical = [{'symbol': 'AAA', 'close': 100.0, 'rsi_14': 70.0,
                       'composite_score': 15, 'recommendation': 'BUY', 'volume': 1000},
                      {'symbol': 'BBB', 'close': 50.0, 'rsi_14': 40.0,
                       'composite_score': 12, 'recommendation': 'WATCH', 'volume': 500}]
        live = [{'symbol': 'AAA', 'close': 103.0, 'volume': 900, 'RSI': 72.0},
                {'symbol': 'BBB', 'close': 48.0, 'volume': 400, 'RSI': 41.0}]
        txt = self.mod.build_open_crosscheck(historical, live, date(2026, 7, 31))
        # Must contain the merge columns and derived gap
        self.assertIn('AAA', txt)
        self.assertIn('BBB', txt)
        self.assertIn('+3.00%', txt)          # AAA gap = (103-100)/100
        self.assertIn('-4.00%', txt)          # BBB gap
        self.assertIn('EOD Close', txt)
        self.assertIn('9:15', txt or '9:15')
        # sane: AAA scored as ✓ (up on BUY), BBB as ✗ (down on WATCH is fine/neutral)
        self.assertIsInstance(txt, str)

    def test_send_skips_when_no_analysis(self):
        async def run():
            app = MagicMock()
            with patch.object(self.mod, 'get_resolved_analysis_date', return_value=None):
                return await self.mod.send_open_crosscheck_report(app)
        r = asyncio.run(run())
        self.assertEqual(r.get('sent'), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
