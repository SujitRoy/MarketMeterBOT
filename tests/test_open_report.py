"""09:15 Market-Open Cross-Check report — design + send."""
import os, sys, unittest, asyncio
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOpenCrossCheckReport(unittest.TestCase):
    def setUp(self):
        import importlib
        self.mod = importlib.import_module('src.reports.premarket.premarket_report')

    def test_module_and_entrypoints_exist(self):
        self.assertTrue(hasattr(self.mod, 'send_open_crosscheck_report'))
        self.assertTrue(hasattr(self.mod, 'CombinedPreMarketReport'))

    def test_class_exists(self):
        self.assertTrue(hasattr(self.mod, 'OpenCrossCheckReport'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
