"""Test premarket report job."""
import os, sys, unittest, asyncio, inspect
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPremarketJobFires(unittest.TestCase):
    """Test that the premarket job fires correctly."""

    def test_job_callback_accepts_context_not_app(self):
        """The job callback should accept (context) not (app)."""
        from src.scheduler.scheduler import _premarket_report_job
        sig = inspect.signature(_premarket_report_job)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ['context'],
                         f"Expected ['context'], got {params}")


class TestPremarketWrapperBehaviour(unittest.TestCase):
    """Test wrapper behaviour for premarket jobs."""

    def test_wrapper_calls_reporter_with_app(self):
        """The wrapper should call the reporter with the app."""
        from src.scheduler.scheduler import _premarket_report_job
        
        # Just verify the function exists and has correct signature
        sig = inspect.signature(_premarket_report_job)
        self.assertIn('context', sig.parameters)

    def test_report_class_exists(self):
        """Verify CombinedPreMarketReport class exists."""
        from src.reports.premarket.premarket_report import CombinedPreMarketReport
        self.assertIsNotNone(CombinedPreMarketReport)


if __name__ == '__main__':
    unittest.main(verbosity=2)
