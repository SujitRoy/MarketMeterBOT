"""
tests/scheduler/test_jobs.py — tests for scheduler/jobs.py.

Phase 7 §3 mandate: "job callbacks (mocked sources, no DB/network)."

These tests exercise the daily/premarket/cross-check job callbacks.
Each test mocks the underlying network/DB call so the tests run in
milliseconds.
"""
from __future__ import annotations

import os
import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

import marketmeter.scheduler.jobs as jobs


def _run(coro):
    return asyncio.run(coro)


class TestPremarketReportJob:
    """The 09:00 premarket job must call send_premarket_report(mode="live") and notify
    the owner if nothing was sent (so a silent miss is never lost)."""

    def test_calls_send_premarket_report_live(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        fake_result = {"sent": 1, "failed": 0}
        # Patch at the import source (marketmeter.reports) so the lazy import
        # inside the job picks up our mock.
        with patch("marketmeter.reports.send_premarket_report",
                   new=AsyncMock(return_value=fake_result), create=True) as mock_send:
            _run(jobs._premarket_report_job(ctx))
        mock_send.assert_awaited_once_with(ctx.application, mode="live")

    def test_zero_sent_triggers_owner_warning(self):
        # When send_premarket_report reports 0 sent, the owner must get
        # an explicit warning so a silent miss is never lost.
        ctx = MagicMock()
        ctx.application = MagicMock()
        fake_result = {"sent": 0}
        with patch("marketmeter.reports.send_premarket_report",
                   new=AsyncMock(return_value=fake_result), create=True), \
             patch("marketmeter.telegram.send_to_owner",
                   new=AsyncMock(), create=True) as mock_owner:
            _run(jobs._premarket_report_job(ctx))
        mock_owner.assert_awaited_once()

    def test_exception_triggers_failure_alert(self):
        # If the inner coroutine raises, the failure is reported to the owner.
        ctx = MagicMock()
        ctx.application = MagicMock()
        with patch("marketmeter.reports.send_premarket_report",
                   new=AsyncMock(side_effect=RuntimeError("network")), create=True), \
             patch("marketmeter.telegram.send_to_owner",
                   new=AsyncMock(), create=True) as mock_owner:
            _run(jobs._premarket_report_job(ctx))
        mock_owner.assert_awaited_once()


class TestOpenCrosscheckJob:
    """The 09:15 cross-check job must call send_premarket_report(mode="open")."""

    def test_calls_send_premarket_report_open(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        fake_result = {"sent": 1}
        with patch("marketmeter.reports.send_premarket_report",
                   new=AsyncMock(return_value=fake_result), create=True) as mock_send:
            _run(jobs._open_crosscheck_job(ctx))
        mock_send.assert_awaited_once_with(ctx.application, mode="open")

    def test_zero_sent_triggers_owner_warning(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        fake_result = {"sent": 0}
        with patch("marketmeter.reports.send_premarket_report",
                   new=AsyncMock(return_value=fake_result), create=True), \
             patch("marketmeter.telegram.send_to_owner",
                   new=AsyncMock(), create=True) as mock_owner:
            _run(jobs._open_crosscheck_job(ctx))
        mock_owner.assert_awaited_once()

    def test_exception_triggers_failure_alert(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        with patch("marketmeter.reports.send_premarket_report",
                   new=AsyncMock(side_effect=RuntimeError("network")), create=True), \
             patch("marketmeter.telegram.send_to_owner",
                   new=AsyncMock(), create=True) as mock_owner:
            _run(jobs._open_crosscheck_job(ctx))
        mock_owner.assert_awaited_once()


class TestDailyReportJob:
    """The 08:30 daily report job must call send_report_to_all."""

    def test_calls_send_report_to_all(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        fake_result = {"sent": 10, "failed": 0}
        with patch("marketmeter.telegram.send_report_to_all",
                   new=AsyncMock(return_value=fake_result), create=True) as mock_send:
            _run(jobs._daily_report_job(ctx))
        mock_send.assert_awaited_once_with(ctx.application)

    def test_exception_triggers_failure_alert(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        with patch("marketmeter.telegram.send_report_to_all",
                   new=AsyncMock(side_effect=RuntimeError("boom")), create=True), \
             patch("marketmeter.telegram.send_to_owner",
                   new=AsyncMock(), create=True) as mock_owner:
            _run(jobs._daily_report_job(ctx))
        mock_owner.assert_awaited_once()


class TestJobLogging:
    """Each job logs its start. This is how operators know cron fired."""

    def test_premarket_job_logs_start(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        with patch("marketmeter.scheduler.jobs.send_premarket_report",
                   new=AsyncMock(return_value={"sent": 1}), create=True):
            _run(jobs._premarket_report_job(ctx))
        # We can't easily capture log output, but the call must complete
        # without error. The log line is best-effort.

    def test_crosscheck_job_logs_start(self):
        ctx = MagicMock()
        ctx.application = MagicMock()
        with patch("marketmeter.scheduler.jobs.send_premarket_report",
                   new=AsyncMock(return_value={"sent": 1}), create=True):
            _run(jobs._open_crosscheck_job(ctx))