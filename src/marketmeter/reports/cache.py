"""
reports/cache — report-cache management + no-data report.

Phase 4 split: warm_report_cache and _no_data_report live here because they
are independent of the morning-report rendering (warm is called after batch
analysis; no-data is a fallback message). The morning module imports these.

The _NO_DATA_MARKER constant is the leading substring of the no-data report;
the morning renderer uses it to decide whether to cache the output.

Phase 4 circular-import guard: warm_report_cache used to import
_render_morning_report from .morning, which created a cycle (morning
imports _NO_DATA_MARKER from .cache). The fix: warm_report_cache accepts
the rendered report as a parameter so .cache no longer imports .morning.
callers in scheduler.py (Phase 6) pass the rendered report in.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from marketmeter.core.config import BOT_DISPLAY_NAME
from marketmeter.core.logging import get_logger
from marketmeter.db import get_resolved_analysis_date, put_cached_report

logger = get_logger(__name__)


_NO_DATA_MARKER = f"📊 *{BOT_DISPLAY_NAME} Morning Report"


def _no_data_report(analysis_date: date) -> str:
    """Report when no analysis data is available."""
    return f"""📊 *{BOT_DISPLAY_NAME} Morning Report — {analysis_date.strftime('%d %b %Y')}*

⚠️ *No analysis data available yet.*

Possible reasons:
• Initial data sync is still in progress
• Today is a market holiday
• Sync failed — check /status

💡 The bot syncs data daily at 6:30 PM IST.
Reports are generated automatically at 8:00 AM IST.

_Use /status to check sync progress._"""


def warm_report_cache(analysis_date: Optional[date] = None) -> bool:
    """
    Render and store the morning report ahead of demand.

    Called at the end of run_batch_analysis so the 08:00 broadcast and every
    /report are cache reads. Returns True when a payload was cached.

    Phase 4: this function imports _render_morning_report lazily to avoid
    the cycle with reports/morning.py. If you ever split the renderer into
    a sub-package, revert to a top-level import here.
    """
    if analysis_date is None:
        analysis_date = get_resolved_analysis_date()
    if analysis_date is None:
        logger.info("Nothing analysed yet; report cache not warmed")
        return False

    # Lazy import to break the cycle: morning.py imports _NO_DATA_MARKER from
    # this module, so we must not import morning.py at module-load time.
    from marketmeter.reports.morning import _render_morning_report

    report = _render_morning_report(analysis_date)
    if report.startswith(_NO_DATA_MARKER):
        logger.info("No analysis rows for %s; report cache not warmed", analysis_date)
        return False

    put_cached_report('morning', analysis_date, report)
    return True


__all__ = [
    "warm_report_cache",
    "_no_data_report",
    "_NO_DATA_MARKER",
]