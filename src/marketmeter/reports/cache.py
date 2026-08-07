"""
reports/cache — report-cache management + no-data report.

Inlined _no_data_report, removed _NO_DATA_MARKER sentinel.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from marketmeter.core.config import BOT_DISPLAY_NAME
from marketmeter.core.logging import get_logger
from marketmeter.db import get_resolved_analysis_date, put_cached_report

logger = get_logger(__name__)


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
    """
    if analysis_date is None:
        analysis_date = get_resolved_analysis_date()
    if analysis_date is None:
        logger.info("Nothing analysed yet; report cache not warmed")
        return False

    from marketmeter.reports.morning import _render_morning_report

    report = _render_morning_report(analysis_date)
    # Don't cache the "no data" fallback report
    if "No analysis data available" in report:
        logger.info("No analysis rows for %s; report cache not warmed", analysis_date)
        return False

    put_cached_report('morning', analysis_date, report)
    return True


__all__ = [
    "warm_report_cache",
    "_no_data_report",
]