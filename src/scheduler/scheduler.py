"""
Scheduler
APScheduler integration for recurring jobs.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import time
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Optional SQLAlchemy jobstore
try:
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLAlchemyJobStore = None
    SQLALCHEMY_AVAILABLE = False

from src.core.config import PREMARKET_TIME, REPORT_TIME, SYNC_TIME, TIMEZONE
from src.reports.premarket import send_combined_premarket_report, send_open_crosscheck_report

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """Definition of a scheduled job."""
    id: str
    func: Callable
    trigger: CronTrigger
    args: tuple = ()
    kwargs: dict = None
    replace_existing: bool = True
    max_instances: int = 1


class SchedulerManager:
    """Manages APScheduler for recurring jobs."""

    def __init__(self, jobstore_url: str = None):
        self.scheduler = AsyncIOScheduler(timezone=TIMEZONE)
        self._jobs: list[ScheduledJob] = []

        if jobstore_url and SQLALCHEMY_AVAILABLE and SQLAlchemyJobStore:
            self.scheduler.add_jobstore(SQLAlchemyJobStore(url=jobstore_url))
        elif jobstore_url:
            logger.warning("SQLAlchemy not available, skipping persistent jobstore")

    def add_job(self, job: ScheduledJob) -> None:
        """Add a job definition."""
        self._jobs.append(job)

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        hour: int,
        minute: int,
        days_of_week: str = "mon-fri",
        args: tuple = (),
        kwargs: dict = None,
    ) -> None:
        """Add a cron-style job."""
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=days_of_week,
            timezone=TIMEZONE,
        )
        job = ScheduledJob(
            id=job_id,
            func=func,
            trigger=trigger,
            args=args,
            kwargs=kwargs or {},
        )
        self.add_job(job)

    def start(self) -> None:
        """Start the scheduler and register all jobs."""
        for job in self._jobs:
            self.scheduler.add_job(
                job.func,
                trigger=job.trigger,
                id=job.id,
                args=job.args,
                kwargs=job.kwargs,
                replace_existing=job.replace_existing,
                max_instances=job.max_instances,
            )
            logger.info("Scheduled job: %s at %s", job.id, job.trigger)

        self.scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler."""
        self.scheduler.shutdown(wait=wait)
        logger.info("Scheduler shut down")

    def get_jobs(self) -> list[dict[str, Any]]:
        """Get list of scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
            })
        return jobs

    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        try:
            self.scheduler.pause_job(job_id)
            return True
        except Exception:
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            return True
        except Exception:
            return False

    def remove_job(self, job_id: str) -> bool:
        """Remove a job."""
        try:
            self.scheduler.remove_job(job_id)
            return True
        except Exception:
            return False


def parse_time(time_str: str) -> time:
    """Parse HH:MM time string to time object."""
    return time.fromisoformat(time_str)


def get_sync_time() -> time:
    """Get sync time from config."""
    return parse_time(SYNC_TIME)


def get_report_time() -> time:
    """Get report time from config."""
    return parse_time(REPORT_TIME)


def get_premarket_time() -> time:
    """Get pre-market time from config."""
    return parse_time(PREMARKET_TIME)


def setup_scheduled_jobs(app) -> None:
    """
    Setup all scheduled jobs for the bot.
    Called from main.py after bot initialization.
    """
    from src.data.sync import SyncEngine

    sync_engine = SyncEngine()

    # Parse times
    sync_time = get_sync_time()
    report_time = get_report_time()
    premarket_time = get_premarket_time()

    scheduler = app.job_queue.scheduler

    # ─── Sync Job (18:30 IST daily) ───
    scheduler.add_job(
        _sync_job_wrapper,
        trigger=CronTrigger(
            hour=sync_time.hour,
            minute=sync_time.minute,
            timezone=TIMEZONE,
        ),
        id="daily_sync",
        name="Daily BhavCopy Sync",
        max_instances=1,
    )
    logger.info("Scheduled daily sync at %s IST", SYNC_TIME)

    # ─── Analysis Job (runs after sync, same schedule) ───
    scheduler.add_job(
        _analysis_job_wrapper,
        trigger=CronTrigger(
            hour=sync_time.hour,
            minute=sync_time.minute,
            timezone=TIMEZONE,
        ),
        id="daily_analysis",
        name="Daily Technical Analysis",
        max_instances=1,
    )
    logger.info("Scheduled daily analysis at %s IST", SYNC_TIME)

    # ─── Morning Report Job (08:30 IST daily) ───
    scheduler.add_job(
        _morning_report_job,
        trigger=CronTrigger(
            hour=report_time.hour,
            minute=report_time.minute,
            timezone=TIMEZONE,
        ),
        id="morning_report",
        name="Morning Report",
        max_instances=1,
    )
    logger.info("Scheduled morning report at %s IST", REPORT_TIME)

    # ─── Pre-Market Report Job (09:00 IST Mon-Fri) ───
    scheduler.add_job(
        _premarket_report_job,
        trigger=CronTrigger(
            hour=premarket_time.hour,
            minute=premarket_time.minute,
            day_of_week="mon-fri",
            timezone=TIMEZONE,
        ),
        id="premarket_report",
        name="Pre-Market Report",
        max_instances=1,
    )
    logger.info("Scheduled pre-market report at %s IST (Mon-Fri)", PREMARKET_TIME)

    # ─── Open Cross-Check Job (09:15 IST Mon-Fri) ───
    open_check_time = time(9, 15)
    scheduler.add_job(
        _open_crosscheck_job,
        trigger=CronTrigger(
            hour=open_check_time.hour,
            minute=open_check_time.minute,
            day_of_week="mon-fri",
            timezone=TIMEZONE,
        ),
        id="open_crosscheck_report",
        name="Market-Open Cross-Check",
        max_instances=1,
    )
    logger.info("Scheduled market-open cross-check at 09:15 IST (Mon-Fri)")


# ─── Job Wrappers ───

async def _sync_job_wrapper(context):
    """Wrapper for sync job."""
    engine = SyncEngine()
    result = engine.run_incremental_sync()

    from src.reports import generate_sync_status_message
    from src.bot.bot import send_to_owner
    msg = generate_sync_status_message({
        'status': result.status,
        'success': result.success,
        'failed': result.failed,
        'holidays': result.holidays,
        'not_available': result.not_available,
        'total_records': result.total_records,
        'dates_processed': result.dates_processed,
    })

    await send_to_owner(context.application, msg)


async def _analysis_job_wrapper(context):
    """Wrapper for analysis job."""
    from src.analysis import run_batch_analysis
    from src.bot.bot import send_to_owner

    result = run_batch_analysis()

    msg = f"""✅ **Analysis Complete**

📅 Date: {result['analysis_date']}
📊 Analyzed: {result['analyzed']} stocks
⏭️ Skipped: {result['skipped']}
💾 Saved: {result['saved']} rows

{result['message']}"""

    await send_to_owner(context.application, msg)


async def _morning_report_job(context):
    """Morning report job."""
    from src.database.repositories import AnalysisReadRepository, SyncReadRepository
    from src.reports import MorningReport, ReportContext
    from src.bot.bot import send_report_to_all

    sync_repo = SyncReadRepository()
    analysis_date = sync_repo.get_last_synced_date()

    if not analysis_date:
        logger.warning("No analysis date for morning report")
        return

    analysis_repo = AnalysisReadRepository()
    grouped = analysis_repo.get_analysis_by_recommendation(analysis_date)

    all_stocks = [s for v in grouped.values() for s in v]

    report = MorningReport(ReportContext(
        analysis_date=analysis_date,
        grouped_data={"all_stocks": all_stocks},
        outlook={},
    ))
    result = report.build()

    await send_report_to_all(context.application, result.content)


async def _premarket_report_job(context):
    """Pre-market report job (09:00)."""
    result = await send_combined_premarket_report(context.application)
    logger.info("Pre-market report job completed: %s", result)


async def _open_crosscheck_job(context):
    """Open cross-check job (09:15)."""
    result = await send_open_crosscheck_report(context.application)
    logger.info("Open cross-check job completed: %s", result)
