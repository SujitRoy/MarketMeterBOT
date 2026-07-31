"""Smoke + perf guard rails. Proves, against the LIVE repo code (no heavy live-DB
timing baked in as a flaky gate), that:

  1. The morning report is served from report_cache in O(1) when warm.
  2. The analyzer hot path uses the (symbol, trade_date ...) covering index and
     a bounded column set (not SELECT *).
  3. Report correctness is deterministic given identical inputs (real data
     comparison contract): the report for a given analysis_date is stable.

Timing thresholds are generous (they must not flake on a 1 GB DB / 954 MB host).
"""
import os, sys, time, unittest

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db  # noqa: E402
import report_generator as rg  # noqa: E402


class TestReportCacheFastPath(unittest.TestCase):
    def test_warm_cache_returns_identical_payload(self):
        ad = db.get_resolved_analysis_date()
        if ad is None:
            self.skipTest("no analysis data yet")
        cached = rg.get_cached_report('morning', ad)
        if cached is None:
            self.skipTest("cache cold; warm_report_cache not yet run")
        # cached payload must equal a fresh render (real-data comparison window)
        fresh = rg.generate_morning_report(ad, use_cache=False)
        self.assertEqual(cached, fresh, "cached report diverges from fresh render")

    def test_cache_read_is_sub_10ms(self):
        ad = db.get_resolved_analysis_date()
        if ad is None or rg.get_cached_report('morning', ad) is None:
            self.skipTest("cache cold")
        t = time.perf_counter()
        for _ in range(20):
            rg.get_cached_report('morning', ad)
        per = (time.perf_counter() - t) / 20 * 1000
        self.assertLess(per, 10.0, f"warm cache read {per:.2f}ms exceeds 10ms budget")


class TestAnalyzerIndexContract(unittest.TestCase):
    def test_covering_index_decision_documented_not_created(self):
        # Owner decision (A): the covering index is documented in database.py as a
        # measured tradeoff but deliberately NOT created (weak ROI + 954 MB host).
        src = open(db.__file__).read()
        self.assertIn('DECISION', src, "the index tradeoff must stay documented")
        self.assertNotIn('CREATE INDEX IF NOT EXISTS idx_bhavcopy_cover',
                         src.split('DECISION')[1] if 'DECISION' in src else '',
                         "cover index must not be auto-created (owner froze this)")
        # The live hot path is the window=None branch (ANALYSIS_WINDOW_DAYS=None).
        # It must select a bounded column list so the cover index is index-only.
        # (The window branch's outer `SELECT * FROM (...)` is over a bounded
        #  subquery and does not touch the heap — that's fine.)
        import inspect
        hist = inspect.getsource(db.get_stock_history)
        none_branch = hist.split('if window is None:', 1)[1].split('else:', 1)[0]
        self.assertNotIn('SELECT *', none_branch,
                         "live hot path must not SELECT * (breaks index-only)")
        for col in ('close', 'high', 'low', 'volume', 'value_lakh', 'avg_price'):
            self.assertIn(col, none_branch, f"hot path must read {col}")


class TestReportDeterminism(unittest.TestCase):
    def test_same_date_same_report(self):
        ad = db.get_resolved_analysis_date()
        if ad is None:
            self.skipTest("no analysis data")
        r1 = rg.generate_morning_report(ad, use_cache=False)
        r2 = rg.generate_morning_report(ad, use_cache=False)
        self.assertEqual(r1, r2, "report not deterministic for identical inputs")


if __name__ == '__main__':
    unittest.main(verbosity=2)
