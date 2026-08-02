"""
tests/db/test_bhavcopy_repo.py — DB CRUD tests for db/bhavcopy_repo.py.

Phase 7 §3 mandate: "repo tests against :memory: SQLite."

The DB layer doesn't accept a `conn` parameter on read functions — they
open their own connection via `get_connection()`. We monkey-patch
`get_connection` in the module under test so the reads hit our
`:memory:` SQLite instead.

Tests run in milliseconds.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

# The functions open their own connection via get_connection(). We monkey-patch
# it so they hit our :memory: SQLite fixture instead of the live DB.
import marketmeter.db.bhavcopy_repo as repo


@pytest.fixture
def in_memory_bhavcopy_repo(conn):
    """Patch get_connection in bhavcopy_repo so reads hit :memory:."""
    with patch.object(repo, "get_connection", lambda: conn):
        yield conn


class TestEmptyDbReads:
    """All read functions on an empty DB must return sensible empty values,
    not crash with NoneType errors."""

    def test_get_total_records_empty(self, in_memory_bhavcopy_repo):
        result = repo.get_total_records()
        assert result == 0

    def test_get_unique_symbols_count_empty(self, in_memory_bhavcopy_repo):
        result = repo.get_unique_symbols_count()
        assert result == 0

    def test_get_latest_trade_date_empty(self, in_memory_bhavcopy_repo):
        result = repo.get_latest_trade_date()
        assert result is None

    def test_get_date_range_empty(self, in_memory_bhavcopy_repo):
        mn, mx = repo.get_date_range()
        assert mn is None
        assert mx is None


class TestGetAllSymbolsEmpty:
    """get_all_symbols filters symbols by record count; on an empty DB
    it returns an empty list."""

    def test_returns_empty_list(self, in_memory_bhavcopy_repo):
        result = repo.get_all_symbols(min_records=50)
        assert result == []


class TestGetStockHistoryEmpty:
    """get_stock_history returns [] for unknown symbols, never errors."""

    def test_unknown_symbol_returns_empty(self, in_memory_bhavcopy_repo):
        result = repo.get_stock_history("NONEXISTENT", min_days=50)
        assert result == []
