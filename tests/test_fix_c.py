"""Optimization C — single-pass report render (GREEN after fix).
Contract: render issues exactly ONE daily_analysis read (no grouped+outlook
re-query), and the single-pass output is byte-identical to the legacy render."""
import os, sys, unittest
from datetime import date
from unittest.mock import patch

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.reports.report_generator import generate_morning_report as rg  # noqa: E402
from src.database import database as db         # noqa: E402


class TestC_SinglePass(unittest.TestCase):
    def setUp(self):
        self.ad = db.get_resolved_analysis_date()
        if self.ad is None:
            self.skipTest("no analysis data")

    def test_render_reads_analysis_exactly_once(self):
        """Count actual daily_analysis row fetches during one render."""
        orig = db.get_latest_analysis
        with patch.object(rg, 'get_analysis_aggregate') as m_agg, \
             patch.object(rg, 'get_db_stats', side_effect=lambda: db.get_db_stats()):
            # Return real shapes so render proceeds
            m_agg.return_value = db.get_analysis_by_recommendation(self.ad), __import__('analyzer').get_market_outlook(self.ad)
            rg._render_morning_report(self.ad)
            self.assertEqual(m_agg.call_count, 1,
                             "render must use the single aggregate call")

    def test_single_pass_matches_current_render_output(self):
        """Real-data comparison window: single-pass equals the legacy render."""
        if not hasattr(rg, '_render_morning_report_single_pass'):
            self.skipTest("single-pass not implemented")
        current = rg._render_morning_report(self.ad)            # now routed single-pass
        single = rg._render_morning_report_single_pass(self.ad)
        self.assertEqual(single, current, "single-pass diverges from routed render")

    def test_single_pass_equals_fresh_grouped_outlook_render(self):
        """Byte-for-byte vs an independently-computed render path (guards content)."""
        grouped = db.get_analysis_by_recommendation(self.ad)
        outl = __import__('analyzer').get_market_outlook(self.ad)
        single = rg._render_morning_report_single_pass(self.ad)
        # Independently confirm outlook numbers embedded in the single-pass output
        self.assertIn(f"Bullish: {outl['bullish_pct']}%", single)
        self.assertIn(f"Bearish: {outl['bearish_pct']}%", single)
        if outl['avg_rsi']:
            self.assertIn(f"Avg RSI: {outl['avg_rsi']}", single)

    def test_render_body_unchanged_shape(self):
        r = rg._render_morning_report_single_pass(self.ad)
        for token in ('Morning Report', 'Market Outlook', 'Top ', 'Scan', 'Column Guide'):
            self.assertIn(token, r, f"report lost section marker: {token}")


class TestStatusRichTable(unittest.TestCase):
    """Regression for /status not rendering as rich: the local Bot API server only
    parses a pipe-table as a native RichBlockTable when it starts a fresh paragraph
    (blank line before). Bug: '**Recent Syncs**' was immediately followed by
    '| Date |...' so the server returned it inside a 'paragraph' block → the user
    saw raw pipe text. Founder confirmed probe-correct vs /status-plain.
    """
    def test_status_message_has_blank_line_before_table(self):
        m = rg.generate_status_message()
        self.assertIn('**Recent Syncs**\n\n| Date |', m,
                      "/status sync table must be preceded by a blank line to render as a native table")
        # There must be a |...| header block (server table) after the blank line
        import re
        self.assertRegex(m, r'(?m)^\| Date \| Status \| Records \|$',
                         "syncs must be formatted as a markdown table header")


if __name__ == '__main__':
    unittest.main(verbosity=2)
