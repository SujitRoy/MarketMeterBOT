"""
Regression: dangling-shim imports removed in Phase 4-6.

Bugs B1-B5 were production crashes caused by lazy imports inside function
bodies that still pointed at deleted root shims (``bot``, ``scheduler``,
``premarket_open_report``, ...). The failure mode was silent: the functions
*compiled*, the suite was green, and the jobs crashed only at runtime.

These tests deliberately exercise the REAL import lines (no mocking of the
import statement itself) with realistic mockable seams elsewhere, so any
future dangling shim import will turn these RED immediately.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.run(coro)


# ─── B1: _run_sync_cycle must not import the deleted `scheduler` shim ───

class TestSyncCycleNoDanglingImport:
    def test_run_sync_cycle_import_paths_resolve(self):
        """The 18:30 sync body used to do `from scheduler import ...`.
        `scheduler` was deleted; importing it raised ModuleNotFoundError and
        the whole sync silently never ran. This test forces the import to
        execute by mocking the *functions* it imports (not the import line)."""
        from marketmeter.scheduler import sync_cycle as sc

        # Patch the *source modules* the function now imports from.
        with patch("marketmeter.sources.nse.sync_incremental_data",
                   return_value={"status": "up_to_date", "total_records": 0}), \
             patch("marketmeter.telegram.send_to_owner", new=AsyncMock()):
            app = MagicMock()
            result = _run(sc._run_sync_cycle(app))
        assert result["status"] == "up_to_date"

    def test_daily_sync_job_alerts_owner_on_failure(self):
        """When sync raises, owner must get a failure alert (not just a log)."""
        import marketmeter.scheduler.jobs as jobs
        ctx = MagicMock()
        ctx.application = MagicMock()
        with patch.object(jobs, "_run_sync_cycle", side_effect=RuntimeError("boom")), \
             patch("marketmeter.telegram.send_to_owner", new=AsyncMock()) as mo:
            _run(jobs._daily_sync_job(ctx))
        assert mo.await_count >= 1


# ─── B2/B3/B4: report senders must not import the deleted `bot`/
#               `premarket_*` shims at call time ─────────────────────────

class _FakeBot:
    """Minimal PTB Bot stand-in that captures the rich-message transport."""
    def __init__(self):
        self._post = AsyncMock(return_value={"ok": True, "result": {"message_id": 1}})
        self.messages: list[dict] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return True


class _App:
    def __init__(self):
        self.bot = _FakeBot()


def _seed_analysis(rec="STRONG_BUY"):
    return [{"symbol": "X", "composite_score": 1, "close": 100.0, "recommendation": rec}]


class TestPremarketUnifiedSendNoDanglingImport:
    """Test the unified send_premarket_report with all three modes."""

    def test_send_premarket_live_reaches_transport(self):
        import marketmeter.reports.premarket as pm
        pm.get_resolved_analysis_date = lambda: dt.date(2026, 7, 31)
        pm.get_latest_analysis = lambda d: _seed_analysis()
        pm.fetch_live_snapshot = lambda syms: [{
            "symbol": "X", "close": 101.0, "change_abs": 1.0,
            "change": 1.0, "VWAP": 100.5, "volume": 10, "RSI": 55.0,
        }]
        app = _App()
        result = _run(pm.send_premarket_report(app, mode="live"))
        # Must reach the actual send path (not bail with failed=1 from ImportError)
        assert result["sent"] == 1 and result["failed"] == 0

    def test_send_premarket_open_reaches_transport(self):
        import marketmeter.reports.premarket as pm
        pm.get_resolved_analysis_date = lambda: dt.date(2026, 7, 31)
        pm.get_latest_analysis = lambda d: _seed_analysis()
        pm.fetch_live_snapshot = lambda syms: [{
            "symbol": "X", "close": 101.0, "RSI": 55.0, "volume": 99,
        }]
        app = _App()
        result = _run(pm.send_premarket_report(app, mode="open"))
        assert result["sent"] == 1 and result["failed"] == 0

    def test_send_premarket_combined_reaches_transport(self):
        import marketmeter.reports.premarket as pm
        pm.get_resolved_analysis_date = lambda: dt.date(2026, 7, 31)
        pm.get_latest_analysis = lambda d: _seed_analysis()
        pm.fetch_live_snapshot = lambda syms: [{"symbol": "X", "close": 101.0, "RSI": 55.0}]
        app = _App()
        result = _run(pm.send_premarket_report(app, mode="combined"))
        assert result["sent"] == 1 and result["failed"] == 0

    def test_combined_with_none_recommendation_does_not_crash(self):
        """B6: merge_historical_live sets hist_rec=h.get('recommendation'),
        which may be None. `.get(key, default)` returns None in that case, so
        `(m.get('hist_rec') or NA_EMDASH).replace(...)` is the only safe form."""
        import marketmeter.reports.premarket as pm
        pm.get_resolved_analysis_date = lambda: dt.date(2026, 7, 31)
        pm.get_latest_analysis = lambda d: _seed_analysis(rec=None)  # None rec
        pm.fetch_live_snapshot = lambda syms: [{"symbol": "X", "close": 101.0}]
        app = _App()
        result = _run(pm.send_premarket_report(app, mode="combined"))
        # Would have raised AttributeError: 'NoneType' has no attribute 'replace'
        assert result["sent"] == 1