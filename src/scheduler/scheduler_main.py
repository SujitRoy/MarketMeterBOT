"""
Scheduler for MarketMeter.
Uses python-telegram-bot's JobQueue for async scheduled tasks.
Runs within the bot's event loop — no external cron needed.
"""
import asyncio
import logging
from datetime import datetime, time, timezone, timedelta

from telegram.ext import Application

# PTB's JobQueue defaults to UTC unless `time.tzinfo` is set or the bot's
# Defaults.tzinfo is configured. The server's clock is IST, but the scheduler
# is timezone-agnostic — without this offset, SYNC_TIME="18:30" would fire at
# 18:30 UTC (midnight IST) and REPORT_TIME="08:30" at 14:00 IST, not 08:30.
# See: PTB JobQueue.scheduler_configuration hardcodes timezone = UTC.
IST = timezone(timedelta(hours=5, minutes=30))

from src.core.config import (
    SYNC_TIME, REPORT_TIME, TIMEZONE, OWNER_CHAT_ID,
    SYNC_RETRY_INTERVAL_MINUTES, SYNC_RETRY_UNTIL_HOUR,
    PREMARKET_TIME,
)
from data_fetcher import sync_incremental_data
from src.analysis.analyzer import run_batch_analysis
from report_generator import (
    generate_sync_status_message, generate_sync_failure_alert,
    warm_report_cache,
)
from src.bot.bot import send_to_owner, send_report_to_all
from premarket_report import send_premarket_report
from premarket_open_report import send_open_crosscheck_report
from premarket_combined_report import send_combined_premarket_report

logger = logging.getLogger(__name__)

RETRY_JOB_NAME = "sync_retry"


async def confirm_bhavcopy_insertion(app, result: dict) -> None:
    """
    Explicit owner receipt after a real (>0-record) BhavCopy insert.

    Each trading day the owner needs a positive confirmation that the 18:30
    job actually landed rows — the generic sync banner double-counts a re-run
    date as 'inserted' and says nothing about net-new. This receipt lists the
    per-date record counts so a partial sync (some dates landed, some pending)
    is visible at a glance instead of inferred from failures.
    """
    inserted = result.get('total_records', 0)
    if inserted <= 0:
        return
    breakdown = result.get('per_date_records') or {}
    lines = [
        f"{result.get('synced_dates', []) and '📥' or '📥'} "
        f"**BhavCopy Insertion Confirmed**",
        "",
        f"✅ **{inserted:,} net-new records** written",
    ]
    if breakdown:
        lines.append("")
        for d, n in breakdown.items():
            lines.append(f"   • {d}: {n:,} rows")
    pending = result.get('not_available') or []
    if pending:
        lines.append("")
        lines.append(f"⏳ Still pending (NSE not published): {', '.join(pending)}")
    await send_to_owner(app, "\n".join(lines), use_rich=True)
    logger.info("Owner insertion receipt sent: %d records across %d dates",
                inserted, len(breakdown) or len(result.get('synced_dates') or []))


def _parse_time(time_str: str) -> time:
    """Parse 'HH:MM' string to a time object stamped with IST.

    Returning a tz-aware time is what tells PTB's JobQueue to fire at that
    wall-clock hour in IST rather than in UTC (the scheduler's default).
    """
    hour, minute = map(int, time_str.split(':'))
    return time(hour=hour, minute=minute, tzinfo=IST)


async def _run_sync_cycle(app, *, is_retry: bool = False) -> dict:
    """
    Run one sync pass, notify the owner, and analyse anything new.

    Shared by the 18:30 job and the 15-minute retry job so both paths behave
    identically. Returns the sync result dict.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sync_incremental_data)

    inserted = result.get('total_records', 0)

    if result.get('status') == 'completed' and inserted > 0:
        await confirm_bhavcopy_insertion(app, result)
        prefix = "🔁 **Retry Succeeded — BhavCopy Inserted**" if is_retry \
                 else "✅ **BhavCopy Data Inserted**"
        dates = result.get('synced_dates') or []
        date_line = f"📅 Dates: {', '.join(str(d) for d in dates)}\n" if dates \
                    else f"📅 Dates processed: {result.get('dates_processed', 0)}\n"
        await send_to_owner(app, (
            f"{prefix}\n\n"
            f"{date_line}"
            f"📥 **{inserted:,} records** added to database\n"
            f"🎯 Success: {result.get('success', 0)} | "
            f"❌ Failed: {result.get('failed', 0)} | "
            f"🏖️ Holidays: {result.get('holidays', 0)}"
        ), use_rich=True)
        logger.info("Notified owner: %d records inserted", inserted)

        logger.info("New data synced. Running batch analysis...")
        analysis_result = await loop.run_in_executor(None, run_batch_analysis)
        await loop.run_in_executor(None, warm_report_cache)

        await send_to_owner(app, (
            f"📊 **Analysis Complete**\n"
            f"• {analysis_result['analyzed']} stocks analyzed\n"
            f"• {analysis_result['saved']} results cached\n"
            f"• {analysis_result['message']}"
        ), use_rich=True)

    return result


def _schedule_sync_retry(context) -> bool:
    """
    Arm the 15-minute retry job if there is still time left today.

    Returns True when a retry was scheduled. Past SYNC_RETRY_UNTIL_HOUR the file
    is not arriving today, so we stop and let the next 18:30 run handle it --
    this also keeps retries out of the 09:00-10:30 cron window.
    """
    # IST-aware cutoff: a naive datetime.now() is only correct when the host
    # clock happens to be IST. datetime.now(tz=IST) is correct anywhere.
    if datetime.now(IST).hour >= SYNC_RETRY_UNTIL_HOUR:
        return False

    jq = context.job_queue
    # Drop any already-armed retry so attempts cannot compound.
    for job in jq.get_jobs_by_name(RETRY_JOB_NAME):
        job.schedule_removal()

    jq.run_once(
        _sync_retry_job,
        when=SYNC_RETRY_INTERVAL_MINUTES * 60,
        name=RETRY_JOB_NAME,
    )
    logger.info("Armed BhavCopy retry in %d min", SYNC_RETRY_INTERVAL_MINUTES)
    return True


async def _sync_retry_job(context):
    """
    Re-attempt a pending BhavCopy, re-arming itself until it lands or time runs
    out. Only the outcome is announced; a per-attempt message would mean ~16
    notifications across the evening.
    """
    app = context.application
    try:
        result = await _run_sync_cycle(app, is_retry=True)

        # Bug #3 fix: a positive total_records does NOT mean work is done. If NSE
        # successfully published one date but a *different* date is still
        # not_available, the retry loop must keep going until every pending date
        # lands or the cutoff hour passes. Only stop when nothing is left pending.
        if result.get('not_available'):
            logger.info("%d record(s) landed but %d date(s) still pending; keeping retry loop alive",
                        result.get('total_records', 0), len(result.get('not_available', [])))
            if not _schedule_sync_retry(context):
                pending = ', '.join(str(d) for d in result['not_available'])
                await send_to_owner(app, (
                    f"⚠️ **BhavCopy Still Unavailable**\n\n"
                    f"Gave up for today at {SYNC_RETRY_UNTIL_HOUR}:00 IST.\n"
                    f"📅 Pending: {pending}\n"
                    f"🔄 Next attempt at the {SYNC_TIME} sync."
                ), use_rich=True)
                logger.warning("Retry window closed with dates still pending")

    except Exception as e:
        logger.error("Sync retry job failed: %s", e, exc_info=True)
        # A transport blip should not kill the loop; keep trying if time remains.
        _schedule_sync_retry(context)


async def _daily_sync_job(context):
    """
    Daily sync job: downloads incremental BhavCopy data.
    Runs at SYNC_TIME (default 6:30 PM IST).
    """
    logger.info("=" * 60)
    logger.info("DAILY SYNC JOB STARTED at %s", datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'))
    logger.info("=" * 60)

    app = context.application

    try:
        result = await _run_sync_cycle(app)

        status_msg = generate_sync_status_message(result)
        await send_to_owner(app, status_msg, use_rich=True)

        if result.get('not_available'):
            armed = _schedule_sync_retry(context)
            pending = ', '.join(str(d) for d in result['not_available'])
            await send_to_owner(app, (
                f"⏳ **BhavCopy Not Available Yet**\n\n"
                f"NSE had not published at sync time.\n"
                f"📅 Pending dates: {pending}\n"
                + (f"🔄 Retrying every {SYNC_RETRY_INTERVAL_MINUTES} min "
                   f"until {SYNC_RETRY_UNTIL_HOUR}:00 IST."
                   if armed else
                   f"🔄 Will retry on the next {SYNC_TIME} sync.")
            ), use_rich=True)
            logger.info("Notified owner: %d dates pending NSE publish",
                        len(result['not_available']))

        logger.info("Daily sync job completed successfully")

    except Exception as e:
        logger.error("Daily sync job failed: %s", e, exc_info=True)
        alert = generate_sync_failure_alert(str(e))
        try:
            await send_to_owner(app, alert)
        except Exception:
            logger.error("Failed to send failure alert to owner")


async def _premarket_report_job(context):
    """
    Pre-market report at 09:00 IST (Mon–Fri).

    JobQueue ALWAYS invokes job callbacks as callback(context). daily_report and
    daily_sync follow this shape; the premarket job had been registering the raw
    send_premarket_report(app) coroutine and on 2026-07-31 never produced a
    'Running job premarket_report' or any exception after a restart close to the
    window — the run was lost silently. A dedicated (context)-shaped callback
    matches the other jobs, guarantees the Application resolves, and lets us
    notify the owner if the send itself fails.
    """
    logger.info("=" * 60)
    logger.info("PREMARKET REPORT JOB STARTED at %s",
                datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'))
    logger.info("=" * 60)
    try:
        result = await send_premarket_report(context.application)
        logger.info("Premarket report job completed: %s", result)
        # If nothing actually reached the owner, say so explicitly — silence here
        # is how the 09:00 run went missing unnoticed.
        if result.get('sent', 0) == 0:
            await send_to_owner(context.application, (
                "⚠️ **Pre-market report: nothing sent**\n"
                "The 09:00 job ran but delivered to 0 recipients. "
                "(Likely no live data / no analysis yet.)"
            ), use_rich=True)
    except Exception as e:
        logger.error("Premarket report job failed: %s", e, exc_info=True)
        try:
            await send_to_owner(context.application,
                f"❌ *Pre-market report failed:*\n```\n{str(e)[:400]}\n```")
        except Exception:
            logger.error("Failed to send premarket failure alert")


async def _open_crosscheck_job(context):
    """
    Market-open cross-check at 09:15 IST (Mon–Fri).

    Merges the EOD analysis (morning report data) with live 09:15 prices so the
    owner can validate the morning calls against the actual open.
    """
    logger.info("=" * 60)
    logger.info("MARKET-OPEN CROSS-CHECK JOB STARTED at %s",
                datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'))
    logger.info("=" * 60)
    try:
        result = await send_open_crosscheck_report(context.application)
        logger.info("Market-open cross-check job completed: %s", result)
        if result.get('sent', 0) == 0:
            await send_to_owner(context.application, (
                "⚠️ **Market-open cross-check: nothing sent**\n"
                "The 09:15 job ran but delivered to 0 recipients. "
                "(Likely no live data / no analysis yet.)"
            ), use_rich=True)
    except Exception as e:
        logger.error("Market-open cross-check job failed: %s", e, exc_info=True)
        try:
            await send_to_owner(context.application,
                f"❌ *Market-open cross-check failed:*\n```\n{str(e)[:400]}\n```")
        except Exception:
            logger.error("Failed to send cross-check failure alert")


async def _daily_report_job(context):
    """
    Daily report job: generates and broadcasts morning report.
    Runs at REPORT_TIME (default 8:00 AM IST).
    """
    logger.info("=" * 60)
    logger.info("DAILY REPORT JOB STARTED at %s", datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'))
    logger.info("=" * 60)

    try:
        result = await send_report_to_all(context.application)
        logger.info("Daily report job completed: %s", result)

    except Exception as e:
        logger.error("Daily report job failed: %s", e, exc_info=True)
        try:
            await send_to_owner(
                context.application,
                f"❌ *Morning report generation failed:*\n```\n{str(e)[:400]}\n```"
            )
        except Exception:
            logger.error("Failed to send report failure alert")


def setup_scheduled_jobs(app: Application):
    """
    Register all scheduled jobs with the bot's JobQueue.
    Jobs run in IST timezone.
    """
    job_queue = app.job_queue

    sync_time = _parse_time(SYNC_TIME)
    report_time = _parse_time(REPORT_TIME)
    premarket_time = _parse_time(PREMARKET_TIME)

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
        days=(0, 1, 2, 3, 4),  # Mon-Fri only
        name="premarket_report",
    )
    logger.info("Scheduled pre-market report at %s IST (Mon-Fri)", PREMARKET_TIME)

    # Market-open cross-check at 9:15 AM IST (Mon-Fri)
    open_check_time = _parse_time("09:15")
    job_queue.run_daily(
        _open_crosscheck_job,
        time=open_check_time,
        days=(0, 1, 2, 3, 4),  # Mon-Fri only
        name="open_crosscheck_report",
    )
    logger.info("Scheduled market-open cross-check at 09:15 IST (Mon-Fri)")

    logger.info("All scheduled jobs registered")
