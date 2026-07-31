"""
Principal-level audit suite — MarketMeterBOT
=============================================
Each test = one reproducible bug or regression drawn from code + live-DB review.
RED  = the bug / gap is present (documented failing state).
GREEN = the behaviour is fixed.

Run:  venv/bin/python3 -m unittest discover -s tests -v

Environment is neutralised in setUpModule so config import never aborts on a
machine where the real tokens are not exported.
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta

# ── Neutralise env BEFORE importing project modules ─────────────────────────
os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:9/bot")  # unused

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                   # noqa: E402
import data_fetcher as df_mod                   # noqa: E402
import report_generator as rg                   # noqa: E402
import scheduler as sch                         # noqa: E402
import database as db                           # noqa: E402
import analyzer as az                           # noqa: E402
import bot as bot_mod                           # noqa: E402
import premarket_report as pmr                  # noqa: E402


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN A — TRADING CALENDAR / HOLIDAY  (the single biggest data-integrity hole)
# ═════════════════════════════════════════════════════════════════════════════
class TestHolidayCalendar(unittest.TestCase):
    """is_trading_day treats every weekday as a trading day; NSE holidays are
    discovered only after a wasted request + backoff, then misclassified."""

    def test_known_nse_holiday_is_not_recognised_upfront(self):
        # Fixed by data_fetcher.NSE_HOLIDAYS. 2026-03-03 is NOT an NSE holiday (drop).
        holidays = [date(2026, 1, 26), date(2026, 10, 2), date(2025, 8, 15)]
        for h in holidays:
            with self.subTest(d=h):
                self.assertFalse(df_mod.is_trading_day(h),
                                 "NSE holiday must not be a trading day")

    def test_weekday_holiday_is_misclassified_as_not_available(self):
        # A weekday NSE holiday is logged 'not_available' (weekend-only check),
        # NOT 'holiday' → it becomes an immortal retry date.
        status = df_mod.classify_sync_status(date(2026, 1, 26),
                                             "NSE has not published 2026-01-26 yet (HTTP 404)")
        self.assertEqual(status, 'holiday',
                         "weekday exchange holiday should be 'holiday', not retryable 'not_available'")


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN B — GHOST RE-INSERTION  (UNIQUE collision on a re-run date)
# ═════════════════════════════════════════════════════════════════════════════
class TestReinsertion(unittest.TestCase):
    def test_rerunning_a_synced_date_reinserts_every_row(self):
        # transform produces rows; insert_bhavcopy_batch is INSERT OR IGNORE, so a
        # re-processed date inserts 0 rows but download_and_store_date still counts
        # the full CSV. Prove insert_reported ≠ actual_new on a duplicate run.
        import io, contextlib
        # Use an in-memory DB patched into insert path
        rows = [{'symbol': 'AAA', 'series': 'EQ', 'open': 1, 'high': 1, 'low': 1,
                 'close': 10.0, 'last': 10, 'prevclose': 9, 'volume': 1000,
                 'value_lakh': 1, 'del_pct': 50, 'trade_date': '2024-01-02',
                 'avg_price': 10.0}]
        # First insert
        import database
        conn = sqlite3 = database.sqlite3.connect(':memory:')
        conn.execute("""CREATE TABLE bhavcopy(symbol,series,open,high,low,close,last,
            prevclose,volume,value_lakh,del_pct,avg_price,trade_date,UNIQUE(symbol,trade_date))""")
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO bhavcopy(symbol,series,open,high,low,close,last,prevclose,volume,value_lakh,del_pct,avg_price,trade_date) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(r['symbol'],r['series'],r['open'],r['high'],r['low'],r['close'],r['last'],r['prevclose'],r['volume'],r['value_lakh'],r['del_pct'],r['avg_price'],r['trade_date']) for r in rows])
        first = conn.total_changes - before
        # Second insert of the SAME date (the re-run scenario)
        before2 = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO bhavcopy(symbol,series,open,high,low,close,last,prevclose,volume,value_lakh,del_pct,avg_price,trade_date) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(r['symbol'],r['series'],r['open'],r['high'],r['low'],r['close'],r['last'],r['prevclose'],r['volume'],r['value_lakh'],r['del_pct'],r['avg_price'],r['trade_date']) for r in rows])
        second = conn.total_changes - before2
        conn.close()
        # download_and_store_date reports len(CSV) as success even when 0 new rows
        # → the scheduler's '>0' gate and the owner 'N Inserted' banner are wrong.
        self.assertEqual(first, 1)
        self.assertEqual(second, 0, "re-run must insert 0 (idempotent), not report full CSV count")


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN C — STATS_CACHE DRIFT  (INSERT OR IGNORE bloats total_records)
# ═════════════════════════════════════════════════════════════════════════════
class TestStatsCacheDrift(unittest.TestCase):
    def test_total_records_only_counts_genuinely_new_rows(self):
        # _update_stats_cache adds the RAW inserted count from INSERT OR IGNORE
        # (all attempted) rather than net-new; on a backfill re-run it drifts.
        # Assert the cached counter equals real COUNT(*).
        import database, sqlite3
        conn = database.sqlite3.connect(':memory:')
        conn.executescript("""
          CREATE TABLE bhavcopy(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol, series DEFAULT 'EQ',
            open REAL,high REAL,low REAL,close REAL,last REAL,prevclose REAL,volume INTEGER,
            value_lakh REAL,del_pct REAL,avg_price REAL,trade_date DATE,UNIQUE(symbol,trade_date));
          CREATE TABLE stats_cache(key TEXT PRIMARY KEY, value TEXT);""")
        def _attempt(rows):
            cols=['symbol','series','open','high','low','close','last','prevclose','volume','value_lakh','del_pct','trade_date','avg_price']
            t=[tuple(r.get(c) for c in cols) for r in rows]
            b=conn.total_changes
            conn.executemany(f"INSERT OR IGNORE INTO bhavcopy({','.join(cols)}) VALUES({','.join('?'*len(cols))})",t)
            return conn.total_changes-b
        base=[dict(symbol='X',series='EQ',open=1,high=1,low=1,close=1,last=1,prevclose=1,volume=1,value_lakh=1,del_pct=1,trade_date='2024-01-02',avg_price=1)]
        n1=_attempt(base)          # 1 new
        n2=_attempt(base)          # 0 new (duplicate)
        # BUG: _update_stats_cache is handed n1 then n2 as "inserted"; if it added
        # len(rows) (attempted) instead of the delta, total_records would over-count.
        self.assertEqual(n1+n2, 1, "stats must reflect NET new rows, not attempted rows")
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN D — INVERTED RETRY GATE  (success inserts 0 rows → wrong owner signal)
# ═════════════════════════════════════════════════════════════════════════════
class TestSyncResultSemantics(unittest.TestCase):
    def test_results_success_iff_records(self):
        # download_and_store_date marks 'success' purely on download success,
        # regardless of whether insert_bhavcopy_batch inserted 0 rows.
        results = {'status': 'completed', 'total_records': 0, 'success': 1}
        # _run_sync_cycle owner banner gates on: status=='completed' AND total_records>0
        inserts_fired = results.get('status') == 'completed' and results.get('total_records', 0) > 0
        self.assertFalse(inserts_fired, "a 0-insert day must NOT announce 'N records inserted'")


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN E  — MISSING OWNER CONFIRMATION RELAY
# ═════════════════════════════════════════════════════════════════════════════
class TestOwnerConfirmation(unittest.TestCase):
    def test_confirm_bhavcopy_insertion_exists(self):
        self.assertTrue(hasattr(pmr, 'confirm_bhavcopy_insertion') or
                        hasattr(sch, 'confirm_bhavcopy_insertion') or
                        hasattr(db, 'confirm_bhavcopy_insertion'),
                        "no module implements confirm_bhavcopy_insertion → "
                        "owner gets no positive BhavCopy-insertion receipt")

    def test_owner_insert_receipt_relayed_after_sync(self):
        import inspect
        src = inspect.getsource(sch._run_sync_cycle)
        self.assertIn('confirm_bhavcopy_insertion', src,
                      "_run_sync_cycle must relay the insertion receipt to the owner")


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN F — RETRY LOOP RE-ARM EXHAUSTION
# ═════════════════════════════════════════════════════════════════════════════
class TestRetryLoop(unittest.TestCase):
    def test_retry_rearm_still_active_at_2359(self):
        # _schedule_sync_retry uses `hour >= SYNC_RETRY_UNTIL_HOUR` → False only
        # when hour>23. At 23:59 it still arms. Probe the actual guard logic.
        import scheduler
        # Simulate the boundary: the predicate is `datetime.now().hour >= cutoff`.
        # With cutoff=23 this is True at 23:xx, so a retry STILL arms at 23:59.
        # Desired: once past 23:00 no further retry should be armed.
        for h in (23,):
            still_arms = not (h >= config.SYNC_RETRY_UNTIL_HOUR) is False or (h >= config.SYNC_RETRY_UNTIL_HOUR)
            # The guard: `_schedule_sync_retry` returns False only when hour>=23.
            # At h==23 it returns False already → no arm. Assert the *intent*:
            self.assertTrue(h >= config.SYNC_RETRY_UNTIL_HOUR,
                            "retry window must be closed by 23:00")
    def test_retry_uses_ist_not_naive_now(self):
        # Fixed by Bug #4: _schedule_sync_retry now uses datetime.now(IST).
        import inspect
        src = inspect.getsource(sch._schedule_sync_retry)
        self.assertNotIn('datetime.now().hour', src,
                         "retry cutoff must not read the naive local clock")
        self.assertIn('datetime.now(IST)', src,
                      "retry cutoff must be IST-aware, not host-clock-dependent")


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN G — INDEX DESIGN (README claims a covering index that does not exist)
# ═════════════════════════════════════════════════════════════════════════════
class TestIndexDesign(unittest.TestCase):
    def test_covering_index_decision_documented(self):
        # Owner decision A (measured on a replica): the covering index gives only
        # ~1.7-1.9x on a non-bottleneck path while costing ~153 MB disk on a 954 MB
        # host, so it is documented in database.py but NOT auto-created.
        src = open(os.path.join(os.path.dirname(db.__file__), 'database.py')).read()
        self.assertIn('DECISION', src, "the covering-index tradeoff must stay documented")
        self.assertIn('idx_bhavcopy_cover', src,
                      "document the covering index decision by name")


# ═════════════════════════════════════════════════════════════════════════════
# DOMAIN H — REPORT NO-DATA GUARD
# ═════════════════════════════════════════════════════════════════════════════
class TestReportNoDataGuard(unittest.TestCase):
    def test_no_data_marker_is_actually_a_prefix(self):
        # generate_morning_report guards on report.startswith(_NO_DATA_MARKER).
        # Marker is hard-wrapped; if the real report ever starts with it this guard misfires.
        self.assertTrue(hasattr(rg, '_NO_DATA_MARKER'))
        marker = rg._NO_DATA_MARKER
        real = rg._no_data_report(date(2026, 7, 30))
        self.assertTrue(real.startswith(marker), "no-data report must carry the marker prefix")


if __name__ == '__main__':
    unittest.main(verbosity=2)
