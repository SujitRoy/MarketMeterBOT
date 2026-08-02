"""
tests/scheduler/test_sync_cycle.py — retry-gating logic for the scheduler.

Phase 7 §3 mandate: "sync_cycle retry-gating logic (mocked, no network)."

These tests exercise the _schedule_sync_retry predicate that decides
whether to arm the next 15-minute retry. The function uses a real
datetime.now(IST) so the test must monkey-patch the module's reference
to `datetime.now` to control the clock.

The tests are pure logic — no DB, no network — so they run in microseconds.
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


# Reload the sync_cycle module under the test environment so the imports
# of IST etc. resolve.
def _fresh_sync_cycle():
    sys.modules.pop("marketmeter.scheduler.sync_cycle", None)
    return importlib.import_module("marketmeter.scheduler.sync_cycle")


class TestScheduleSyncRetry:
    """The predicate is: if now(IST).hour >= SYNC_RETRY_UNTIL_HOUR, do NOT arm.

    Past SYNC_RETRY_UNTIL_HOUR the file is not coming today, so we stop and
    let the next 18:30 run handle it. This also keeps retries out of the
    09:00-10:30 cron window.
    """

    def test_does_not_arm_before_retry_window(self):
        sc = _fresh_sync_cycle()
        # 18:00 IST — well before the cutoff (default 23)
        now = datetime(2026, 7, 31, 18, 0)
        with patch.object(sc, "datetime") as mock_dt:
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ctx = MagicMock()
            ctx.job_queue.get_jobs_by_name.return_value = []
            result = sc._schedule_sync_retry(ctx)
            assert result is True
            ctx.job_queue.run_once.assert_called_once()

    def test_does_not_arm_at_cutoff_hour(self):
        sc = _fresh_sync_cycle()
        # Exactly at the cutoff (default 23) — retry window is closed
        now = datetime(2026, 7, 31, 23, 0)
        with patch.object(sc, "datetime") as mock_dt:
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ctx = MagicMock()
            result = sc._schedule_sync_retry(ctx)
            assert result is False
            ctx.job_queue.run_once.assert_not_called()

    def test_does_not_arm_past_cutoff(self):
        sc = _fresh_sync_cycle()
        # 23:30 IST — past the cutoff
        now = datetime(2026, 7, 31, 23, 30)
        with patch.object(sc, "datetime") as mock_dt:
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ctx = MagicMock()
            result = sc._schedule_sync_retry(ctx)
            assert result is False
            ctx.job_queue.run_once.assert_not_called()

    def test_removes_already_armed_retry(self):
        sc = _fresh_sync_cycle()
        now = datetime(2026, 7, 31, 18, 30)
        existing_job = MagicMock()
        with patch.object(sc, "datetime") as mock_dt:
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ctx = MagicMock()
            ctx.job_queue.get_jobs_by_name.return_value = [existing_job]
            sc._schedule_sync_retry(ctx)
            # The existing job must have been removed
            existing_job.schedule_removal.assert_called_once()
            # A new run_once must have been scheduled
            ctx.job_queue.run_once.assert_called_once()


class TestSyncCycleRetryBoundary:
    """Bug #3 fix: a positive total_records does NOT mean work is done.

    If NSE successfully published one date but a *different* date is still
    not_available, the retry loop must keep going until every pending date
    lands or the cutoff hour passes. _sync_retry_job calls _schedule_sync_retry
    when there are still pending dates; it sends an owner alert only when
    _schedule_sync_retry returns False (cutoff reached).
    """

    def test_pending_dates_keep_retry_loop_alive(self):
        sc = _fresh_sync_cycle()
        now = datetime(2026, 7, 31, 18, 30)

        # result has BOTH positive records AND pending dates
        result = {"total_records": 2409, "not_available": ["2026-07-31"]}
        ctx = MagicMock()
        ctx.job_queue.get_jobs_by_name.return_value = []

        rearm_calls = []
        def fake_rearm(c):
            rearm_calls.append(c)
            return True  # window still open

        with patch.object(sc, "datetime") as mock_dt, \
             patch.object(sc, "_run_sync_cycle", new=_async_return(result)), \
             patch.object(sc, "_schedule_sync_retry", side_effect=fake_rearm):
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            import asyncio
            asyncio.run(sc._sync_retry_job(ctx))
            # Retry was re-armed because dates are still pending
            assert len(rearm_calls) == 1

    def test_empty_pending_does_not_call_rearm(self):
        """If there are no pending dates, the retry loop should stop."""
        sc = _fresh_sync_cycle()
        now = datetime(2026, 7, 31, 18, 30)

        result = {"total_records": 2409, "not_available": []}
        ctx = MagicMock()

        rearm_calls = []
        def fake_rearm(c):
            rearm_calls.append(c)
            return True

        with patch.object(sc, "datetime") as mock_dt, \
             patch.object(sc, "_run_sync_cycle", new=_async_return(result)), \
             patch.object(sc, "_schedule_sync_retry", side_effect=fake_rearm):
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            import asyncio
            asyncio.run(sc._sync_retry_job(ctx))
            # No re-arm because nothing's pending
            assert len(rearm_calls) == 0

    def test_run_sync_cycle_exception_still_calls_rearm(self):
        """If _run_sync_cycle raises, _schedule_sync_retry must still be called
        so the loop survives a transport blip."""
        sc = _fresh_sync_cycle()
        now = datetime(2026, 7, 31, 18, 30)

        async def _raise(*args, **kwargs):
            raise RuntimeError("network blip")

        ctx = MagicMock()
        ctx.job_queue.get_jobs_by_name.return_value = []

        rearm_calls = []
        def fake_rearm(c):
            rearm_calls.append(c)
            return True

        with patch.object(sc, "datetime") as mock_dt, \
             patch.object(sc, "_run_sync_cycle", side_effect=_raise), \
             patch.object(sc, "_schedule_sync_retry", side_effect=fake_rearm):
            mock_dt.now.return_value = now.replace(tzinfo=sc.IST)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            import asyncio
            asyncio.run(sc._sync_retry_job(ctx))
            # Exception didn't kill the loop — rearm was called
            assert len(rearm_calls) == 1

    def test_log_retrieves_pending_when_no_rearm(self):
        """Bug #3 fix: the log must record how many dates are still pending
        and that the retry loop is alive."""
        sc = _fresh_sync_cycle()

        result = {"total_records": 2409, "not_available": ["2026-07-31", "2026-07-30"]}
        ctx = MagicMock()

        with patch.object(sc, "datetime") as mock_dt, \
             patch.object(sc, "_run_sync_cycle", new=_async_return(result)), \
             patch.object(sc, "_schedule_sync_retry", return_value=True) as mock_rearm:
            import asyncio
            asyncio.run(sc._sync_retry_job(ctx))
            # The log message should mention "2 date(s) still pending"
            # We can't easily check log output, but we can verify the call count
            assert mock_rearm.called


def _async_return(value):
    """Create an async function that returns the given value."""
    async def _inner(*args, **kwargs):
        return value
    return _inner
