"""
scheduler/jobs — scheduled job callbacks.
"""
from __future__ import annotations

from datetime import datetime

from marketmeter.core.logging import get_logger
from marketmeter.scheduler.timeparse import IST
from marketmeter.scheduler.sync_cycle import (
    _run_sync_cycle,
    _schedule_sync_retry,
)

logger = get_logger(__name__)


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
        from marketmeter.reports import generate_sync_status_message
        from marketmeter.telegram import send_to_owner

        result = await _run_sync_cycle(app)

        status_msg = generate_sync_status_message(result)
        await send_to_owner(app, status_msg, use_rich=True)

        if result.get('not_available'):
            armed = _schedule_sync_retry(context)
            pending = ', '.join(str(d) for d in result['not_available'])
            from marketmeter.core.config import SYNC_RETRY_INTERVAL_MINUTES, SYNC_RETRY_UNTIL_HOUR, SYNC_TIME
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
        from marketmeter.reports import generate_sync_failure_alert
        from marketmeter.telegram import send_to_owner
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
        from marketmeter.reports import send_premarket_report
        from marketmeter.telegram import send_to_owner
        result = await send_premarket_report(context.application)
        logger.info("Premarket report job completed: %s", result)
        # If nothing actually reached the owner, say so explicitly — silence here
        # is how the 09:00 run went missing unnoticed.
        if result.get('sent', 0) == 0:
            from marketmeter.telegram import send_to_owner
            await send_to_owner(context.application, (
                "⚠️ **Pre-market report: nothing sent**\n"
                "The 09:00 job ran but delivered to 0 recipients. "
                "(Likely no live data / no analysis yet.)"
            ), use_rich=True)
    except Exception as e:
        logger.error("Premarket report job failed: %s", e, exc_info=True)
        try:
            from marketmeter.telegram import send_to_owner
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
        from marketmeter.reports import send_open_crosscheck_report
        result = await send_open_crosscheck_report(context.application)
        logger.info("Market-open cross-check job completed: %s", result)
        if result.get('sent', 0) == 0:
            from marketmeter.telegram import send_to_owner
            await send_to_owner(context.application, (
                "⚠️ **Market-open cross-check: nothing sent**\n"
                "The 09:15 job ran but delivered to 0 recipients. "
                "(Likely no live data / no analysis yet.)"
            ), use_rich=True)
    except Exception as e:
        logger.error("Market-open cross-check job failed: %s", e, exc_info=True)
        try:
            from marketmeter.telegram import send_to_owner
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
        from marketmeter.telegram import send_report_to_all
        result = await send_report_to_all(context.application)
        logger.info("Daily report job completed: %s", result)

    except Exception as e:
        logger.error("Daily report job failed: %s", e, exc_info=True)
        try:
            from marketmeter.telegram import send_to_owner
            await send_to_owner(
                context.application,
                f"❌ *Morning report generation failed:*\n```\n{str(e)[:400]}\n```"
            )
        except Exception:
            logger.error("Failed to send report failure alert")


__all__ = [
    "_daily_sync_job",
    "_premarket_report_job",
    "_open_crosscheck_job",
    "_daily_report_job",
]