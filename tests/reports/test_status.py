"""
tests/reports/test_status.py — tests for reports/status.py.

These are pure-function tests for the status message generators. No DB,
no network, runs in microseconds.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

from marketmeter.reports.status import (
    generate_sync_status_message,
    generate_sync_failure_alert,
    generate_status_message,
)


class TestSyncStatusMessage:
    """The sync status message includes dates, counts, and pending dates."""

    def test_up_to_date_status(self):
        result = {"status": "up_to_date"}
        msg = generate_sync_status_message(result)
        assert "MarketMeter" in msg
        assert "up to date" in msg.lower() or "already" in msg.lower()

    def test_completed_status_includes_counts(self):
        result = {
            "status": "completed",
            "success": 1, "failed": 0, "holidays": 0,
            "total_records": 2409,
            "not_available": [],
            "synced_dates": ["2026-07-31"],
        }
        msg = generate_sync_status_message(result)
        assert "2,409" in msg
        assert "Success: 1" in msg or "success: 1" in msg.lower()

    def test_completed_with_pending_dates(self):
        result = {
            "status": "completed",
            "success": 1, "failed": 0, "holidays": 0,
            "total_records": 2409,
            "not_available": ["2026-07-31"],
            "synced_dates": ["2026-07-30"],
        }
        msg = generate_sync_status_message(result)
        # Pending dates are mentioned
        assert "2026-07-31" in msg or "Pending" in msg or "pending" in msg

    def test_failed_status_returns_failure_message(self):
        result = {"status": "failed", "message": "Connection refused"}
        msg = generate_sync_status_message(result)
        assert "failed" in msg.lower() or "Failed" in msg
        assert "Connection refused" in msg or "refused" in msg.lower()


class TestSyncFailureAlert:
    def test_includes_error_message(self):
        msg = generate_sync_failure_alert("Network unreachable")
        assert "Network unreachable" in msg
        assert "MarketMeter" in msg

    def test_truncates_long_errors(self):
        long_err = "x" * 1000
        msg = generate_sync_failure_alert(long_err)
        # Long errors are truncated to 500 chars per the original implementation
        assert len(msg) < 1000


class TestStatusMessage:
    """The /status command message includes DB stats and schedule info."""

    def test_uses_db_stats(self):
        from unittest.mock import patch
        fake_stats = {
            "total_records": 1000,
            "unique_symbols": 50,
            "active_subscribers": 3,
            "date_from": "2024-01-01",
            "date_to": "2026-07-31",
        }
        fake_logs = []
        with patch("marketmeter.reports.status.get_db_stats",
                   return_value=fake_stats), \
             patch("marketmeter.reports.status.get_sync_status",
                   return_value=fake_logs):
            msg = generate_status_message()
        assert "1,000" in msg
        assert "50" in msg
        assert "MarketMeter" in msg

    def test_includes_sync_table_when_logs_present(self):
        from unittest.mock import patch
        fake_stats = {
            "total_records": 100, "unique_symbols": 10,
            "active_subscribers": 1, "date_from": "2024-01-01",
            "date_to": "2026-07-31",
        }
        fake_logs = [
            {"trade_date": "2026-07-31", "status": "success", "records_count": 100},
            {"trade_date": "2026-07-30", "status": "failed", "records_count": 0},
        ]
        with patch("marketmeter.reports.status.get_db_stats",
                   return_value=fake_stats), \
             patch("marketmeter.reports.status.get_sync_status",
                   return_value=fake_logs):
            msg = generate_status_message()
        # The sync table must be present
        assert "2026-07-31" in msg
        assert "2026-07-30" in msg
