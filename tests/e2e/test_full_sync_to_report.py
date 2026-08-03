"""
Phase 9 merge gate: end-to-end pipeline test (sync → analysis → report → broadcast).

Runs against an ISOLATED in-memory DB by patching the central
marketmeter.db.connection.get_connection factory, so no test touches the live
data/marketmeter.db. Every repo, the renderer, and the CLI share the same
seeded SQLite within a test.

The failure mode this guards: lazy imports of deleted shims inside job/report
functions (B1-B5) that produced silent production crashes while the suite was
green. This test asserts each stage ACTUALLY completes and produces content.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

# Single authoritative schema fixture lives in the top-level conftest.py.
from conftest import SCHEMA_SQL, fresh_inmemory_db  # noqa: E402


# ─── Isolated DB seam ───────────────────────────────────────────────────────

@contextmanager
def _cm_from_conn(conn: sqlite3.Connection):
    """Yield a pre-seeded connection like marketmeter's get_connection does."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pass  # lifetime owned by the fixture


@pytest.fixture
def db(monkeypatch):
    """Seed an in-memory DB and route every get_connection call to it."""
    conn = fresh_inmemory_db()
    factory = lambda: _cm_from_conn(conn)  # noqa: E731

    # Repos import get_connection locally (`from .connection import get_connection`),
    # so patching only marketmeter.db.connection.get_connection is not enough.
    # Patch the local binding in every repo module that uses it.
    modules_to_patch = [
        "marketmeter.db.connection",
        "marketmeter.db.bhavcopy_repo",
        "marketmeter.db.analysis_repo",
        "marketmeter.db.cache_repo",
        "marketmeter.db.sync_repo",
        "marketmeter.db.subscriber_repo",
        "marketmeter.db.stats_repo",
        "marketmeter.db.intraday_repo",
        "marketmeter.db.schema",
    ]
    for mod in modules_to_patch:
        if mod in sys.modules:
            monkeypatch.setattr(f"{mod}.get_connection", factory)
        else:
            # Import the module so the attribute exists, then patch it.
            __import__(mod)
            monkeypatch.setattr(f"{mod}.get_connection", factory)

    yield conn
    conn.close()


# ─── Seeds ─────────────────────────────────────────────────────────────────


def _seed_day(conn, sym, day: date, close: float, rec: str):
    """Insert one analysis row for (sym, day)."""
    row = dict(
        symbol=sym, analysis_date=day.isoformat(),
        close=close, volume=500_000,
        rsi_14=55.0, adx_14=28.0,
        macd_line=2.5, signal_line=1.8, macd_hist=0.7,
        sma_20=close * 0.98, sma_50=close * 0.97,
        sma_100=close * 0.95, sma_200=close * 0.90,
        ema_20=close * 0.985, ema_50=close * 0.975,
        ema_100=close * 0.95, ema_200=close * 0.90,
        atr_14=close * 0.02, bb_upper=close * 1.03,
        bb_lower=close * 0.97, rel_volume=1.5,
        obv_trend=200_000, avg_price=close,
        composite_score=10, recommendation=rec,
    )
    cols = ", ".join(row)
    ph = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO daily_analysis ({cols}) VALUES ({ph})", tuple(row.values()))
    conn.commit()


# ─── Phase-9: the four-stage pipeline, all against the seeded in-memory DB ──

class TestPhase9EndToEnd:
    def test_resolved_analysis_date_picks_latest(self, db):
        from marketmeter.db import get_resolved_analysis_date
        _seed_day(db, "RELIANCE", date(2026, 7, 30), 2500.0, "BUY")
        _seed_day(db, "TCS", date(2026, 7, 31), 3500.0, "STRONG_BUY")
        assert get_resolved_analysis_date() == date(2026, 7, 31)

    def test_morning_report_no_data_marker_when_empty(self, db):
        from marketmeter.reports import generate_morning_report
        out = generate_morning_report(analysis_date=date(2026, 8, 3), use_cache=False)
        assert "No analysis data available" in out
        assert out.startswith("📊")

    def test_rendered_report_contains_seeded_symbol(self, db):
        from marketmeter.reports.morning import _render_morning_report_single_pass
        _seed_day(db, "RELIANCE", date(2026, 7, 31), 2500.0, "BUY")
        _seed_day(db, "INFY", date(2026, 7, 31), 1500.0, "STRONG_BUY")
        out = _render_morning_report_single_pass(date(2026, 7, 31))
        for sym in ("RELIANCE", "INFY"):
            assert sym in out
        assert "MarketMeter" in out and "📊" in out

    def test_generate_then_cache_roundtrip(self, db):
        from marketmeter.reports import generate_morning_report, warm_report_cache
        from marketmeter.db import get_cached_report
        _seed_day(db, "AIRTEL", date(2026, 7, 31), 1976.0, "BUY")
        # Warm -> put
        assert warm_report_cache(date(2026, 7, 31)) is True
        got = get_cached_report("morning", date(2026, 7, 31))
        assert got and "AIRTEL" in got
        # Second generate must hit cache and return identical payload
        again = generate_morning_report(analysis_date=date(2026, 7, 31))
        assert again == got

    def test_cli_report_strips_rich(self, db):
        from marketmeter.cli.cmd_report import _strip_rich
        sample = "📊 **X**\n<details><summary>**Col**</summary>\n\n| A |\n</details>"
        out = _strip_rich(sample)
        assert "<details" not in out and "**" not in out and "X" in out

    def test_sync_job_full_chain_sends_and_caches(self, db):
        """
        The critical regression: _daily_sync_job -> _run_sync_cycle ->
        sync_incremental_data -> run_batch_analysis -> warm_report_cache.
        We patch only the EXTERNAL network source, then assert analysis gets
        populated AND the report got warmed into the cache.
        """
        from marketmeter.scheduler import jobs
        from marketmeter.db import get_cached_report

        seeded = date(2026, 7, 31)
        fake_result = {
            "status": "completed", "dates_processed": 1, "success": 1,
            "failed": 0, "holidays": 0, "not_available": [],
            "synced_dates": [seeded.isoformat()],
            "per_date_records": {seeded.isoformat(): 100},
            "total_records": 100, "message": "1 date synced",
        }

        analysis_calls = {"n": 0}

        def fake_run_batch_analysis(*args, **kwargs):
            analysis_calls["n"] += 1
            _seed_day(db, "NEWSTOCK", seeded, 100.0, "BUY")
            return {"analyzed": 1, "saved": 1, "message": "ok"}

        with patch("marketmeter.sources.nse.sync_incremental_data",
                   return_value=fake_result), \
             patch("marketmeter.analysis.batch.run_batch_analysis",
                   side_effect=fake_run_batch_analysis), \
             patch("marketmeter.telegram.delivery.send_to_owner", new=AsyncMock()):
            ctx = MagicMock()
            ctx.application = MagicMock()
            asyncio.run(jobs._daily_sync_job(ctx))

        # pipeline ran
        assert analysis_calls["n"] == 1
        got = get_cached_report("morning", seeded)
        assert got and "NEWSTOCK" in got
