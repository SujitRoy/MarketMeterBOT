"""Bugs #2/#6 — owner confirmation after insertion + net-new accounting.
After a >0-record sync, the owner must receive a positive receipt relay.
RED pre-fix: no confirm/final delivery from the sync cycle's insert path."""
import os, sys, unittest, inspect, asyncio
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "audit-dummy-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "620150504")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler as s   # noqa: E402


class TestBug2_OwnerConfirmAfterInsert(unittest.TestCase):
    def test_owner_gets_explicit_bhavcopy_insertion_receipt(self):
        """After real inserts, a dedicated confirm_delivery to owner must fire."""
        src = inspect.getsource(s._run_sync_cycle)
        self.assertIn('confirm_bhavcopy_insertion', src,
                      "no explicit owner receipt exists after BhavCopy insert rows > 0")


class TestBug6b_ZeroNetNewIsVisible(unittest.TestCase):
    def test_zero_net_new_date_is_not_flat_success(self):
        """A date that downloads but lands 0 net-new rows must surface, not vanish
        into 'success'. It produces no bhavcopy rows for that date → analysis and
        the owner banner would otherwise treat it as complete."""
        import pandas as pd
        from unittest.mock import patch
        import data_fetcher as df
        rowish = pd.DataFrame([{'symbol': 'X', 'series': 'EQ', 'open': 1, 'high': 1,
                               'low': 1, 'close': 10.0, 'last': 10, 'prevclose': 9,
                               'volume': 1000, 'value_lakh': 1, 'del_pct': 50,
                               'avg_price': 10.0, 'trade_date': '2026-07-30'}])
        with patch.object(df, 'download_bhavcopy_for_date', return_value=(True, rowish, "ok")), \
             patch.object(df, 'insert_bhavcopy_batch', return_value=0), \
             patch.object(df, 'log_sync') as mlog:
            out = df.download_and_store_date(date(2026, 7, 30))
        # status stays 'success' (sync_log CHECK constraint) but net-new is visible.
        self.assertEqual(out['records'], 0)
        self.assertFalse(out['net_new'], "0 net-new rows must report net_new=False")

    def test_zero_net_new_date_not_in_synced_dates(self):
        """A 0-net-new date must not appear in the owner's inserted-dates banner."""
        import pandas as pd
        from unittest.mock import patch
        import data_fetcher as df
        from datetime import timedelta
        rowish = pd.DataFrame([{'symbol': 'X', 'series': 'EQ', 'open': 1, 'high': 1,
                               'low': 1, 'close': 10.0, 'last': 10, 'prevclose': 9,
                               'volume': 1000, 'value_lakh': 1, 'del_pct': 50,
                               'avg_price': 10.0, 'trade_date': '2026-07-29'}])
        today = date(2026, 7, 30)
        with patch.object(df, 'get_last_synced_date', return_value=today - timedelta(days=2)), \
             patch.object(df, 'get_latest_trade_date', return_value=today - timedelta(days=2)), \
             patch.object(df, 'get_failed_syncs', return_value=[]), \
             patch.object(df, 'date') as _d, \
             patch.object(df, 'download_and_store_date', return_value={
                 'date': today, 'status': 'success', 'records': 0, 'net_new': False}):
            _d.today.return_value = today
            _d.fromisoformat = date.fromisoformat
            res = df.sync_incremental_data()
        self.assertNotIn(today.isoformat(), res.get('synced_dates', []),
                         "0-net-new date leaked into synced_dates (receipt/banner lie)")
        self.assertEqual(res['total_records'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
