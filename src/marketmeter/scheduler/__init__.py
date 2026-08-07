"""
scheduler — scheduled job registration.
"""
from __future__ import annotations

from marketmeter.core.time import parse_ist_time
from .jobs import (
    _daily_sync_job,
    _premarket_report_job,
    _open_crosscheck_job,
    _daily_report_job,
)
from .sync_cycle import (
    _schedule_sync_retry,
    _run_sync_cycle,
    confirm_bhavcopy_insertion,
    _sync_retry_job,
)

from marketmeter.core.config import (
    SYNC_TIME, REPORT_TIME, PREMARKET_TIME,
)

from marketmeter.core.logging import get_logger

logger = get_logger(__name__)


def setup_scheduled_jobs(app):
    """
    Register all scheduled jobs with the bot's JobQueue.
    Jobs run in IST timezone.
    """
    job_queue = app.job_queue

    sync_time = parse_ist_time(SYNC_TIME)
    report_time = parse_ist_time(REPORT_TIME)
    premarket_time = parse_ist_time(PREMARKET_TIME)

    # Daily sync at 6:30 PM IST
    job_queue.run_daily(
        _daily_sync_job,
        time=sync_time,
        days=(0, 1, 2, 3, 4, 5, 6),  # Every day (job checks trading day internally)
        name="daily_sync",
    )
    logger.info("Scheduled daily sync at %s IST", SYNC_TIME)

    # Daily report at 8:00 AM IST
    job_queue.run_daily(
        _daily_report_job,
        time=report_time,
        days=(0, 1, 2, 3, 4, 5, 6),  # Every day
        name="daily_report",
    )
    logger.info("Scheduled daily report at %s IST", REPORT_TIME)

    # Pre-market live prices at 9:00 AM IST (Mon-Fri)
    job_queue.run_daily(
        _premarket_report_job,
        time=premarket_time,
        days=(1, 2, 3, 4, 5),  # Mon-Fri only (cron: 1=Mon, 5=Fri)
        name="premarket_report",
    )
    logger.info("Scheduled pre-market report at %s IST (Mon-Fri)", PREMARKET_TIME)

    # Market-open cross-check at 9:15 AM IST (Mon-Fri)
    open_check_time = parse_ist_time("09:15")
    job_queue.run_daily(
        _open_crosscheck_job,
        time=open_check_time,
        days=(1, 2, 3, 4, 5),  # Mon-Fri only (cron: 1=Mon, 5=Fri)
        name="open_crosscheck_report",
    )
    logger.info("Scheduled market-open cross-check at 09:15 IST (Mon-Fri)")

    logger.info("All scheduled jobs registered")


__all__ = [
    "setup_scheduled_jobs",
    "_daily_sync_job",
    "_premarket_report_job",
    "_open_crosscheck_job",
    "_daily_report_job",
    "_schedule_sync_retry",
    "_run_sync_cycle",
    "confirm_bhavcopy_insertion",
    "_sync_retry_job",
]