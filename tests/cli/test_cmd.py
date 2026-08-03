"""
tests/cli/test_cmd.py — CLI subcommand smoke tests.

Phase 7 §3 mandate: "CLI subcommand tests (mocked, no network)."

These tests prove each CLI subcommand:
  * Imports cleanly.
  * Calls the right underlying function with the right arguments.
  * Prints the right result on stdout.

All underlyings (sync, backfill, analyze, report, status) are patched
via monkeypatch, so the tests run in milliseconds without touching the
real DB or network.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from io import StringIO

# Ensure src/ is on sys.path before any marketmeter import.
_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Provide env vars before config.py is loaded.
os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from marketmeter.cli import cmd_sync, cmd_backfill, cmd_report, cmd_analyze, cmd_status


def _run(coro):
    """Run an async CLI coroutine and return its stdout."""
    import io
    import contextlib
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        asyncio.run(coro)
    return buf.getvalue()


class TestCmdSync:
    def test_calls_sync_incremental_data(self):
        fake_result = {"status": "completed", "total_records": 0}
        fake_report = "MOCK SYNC REPORT"
        with patch("marketmeter.cli.cmd_sync.sync_incremental_data",
                   return_value=fake_result), \
             patch("marketmeter.cli.cmd_sync.generate_sync_status_message",
                   return_value=fake_report):
            out = _run(cmd_sync())
        assert fake_report in out

    def test_runs_analysis_when_records_inserted(self):
        fake_result = {"status": "completed", "total_records": 100}
        with patch("marketmeter.cli.cmd_sync.sync_incremental_data",
                   return_value=fake_result), \
             patch("marketmeter.cli.cmd_sync.generate_sync_status_message",
                   return_value="sync ok"), \
             patch("marketmeter.analysis.run_batch_analysis",
                   return_value={"message": "analyzed 100"}) as mock_analyze:
            out = _run(cmd_sync())
        mock_analyze.assert_called_once()
        assert "analyzed 100" in out


class TestCmdBackfill:
    def test_aborts_on_user_decline(self):
        # User types 'n' → should abort without doing work
        with patch("builtins.input", return_value="n"), \
             patch("marketmeter.cli.cmd_backfill.backfill_historical_data") as mock_bb:
            _run(cmd_backfill())
        mock_bb.assert_not_called()


class TestCmdReport:
    def test_prints_morning_report(self):
        with patch("marketmeter.cli.cmd_report.generate_morning_report",
                   return_value="MORNING REPORT CONTENT") as mock_report:
            out = _run(cmd_report())
        mock_report.assert_called_once()
        assert "MORNING REPORT CONTENT" in out


class TestCmdAnalyze:
    def test_runs_batch_analysis(self):
        fake_result = {"message": "analyzed 1772"}
        with patch("marketmeter.cli.cmd_analyze.run_batch_analysis",
                   return_value=fake_result) as mock_analyze:
            out = _run(cmd_analyze())
        mock_analyze.assert_called_once()
        assert "analyzed 1772" in out


class TestCmdStatus:
    def test_prints_db_stats(self):
        fake_stats = {
            "total_records": 2325181,
            "unique_symbols": 3068,
            "active_subscribers": 5,
            "date_from": "2022-01-03",
            "date_to": "2026-07-31",
        }
        with patch("marketmeter.cli.cmd_status.get_db_stats",
                   return_value=fake_stats):
            out = _run(cmd_status())
        # Status prints raw dict values; assert that the numeric values are present
        assert "2325181" in out
        assert "3068" in out
        assert "MarketMeter Database Status" in out


class TestCliModuleExports:
    """Pin the public CLI surface so callers can rely on these names."""

    def test_cli_exports_all_commands(self):
        from marketmeter.cli import (
            cmd_sync, cmd_backfill, cmd_report, cmd_analyze, cmd_status,
        )
        for name in ("cmd_sync", "cmd_backfill", "cmd_report", "cmd_analyze", "cmd_status"):
            assert callable(globals()[name])
