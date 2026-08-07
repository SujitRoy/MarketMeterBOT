"""
scheduler/sync_cycle — sync cycle execution and retry logic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from marketmeter.core.config import (
    SYNC_RETRY_INTERVAL_MINUTES, SYNC_RETRY_UNTIL_HOUR,
)
from marketmeter.core.logging import get_logger
from marketmeter.core.time import IST

logger = get_logger(__name__)

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
    from marketmeter.telegram import send_to_owner

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


async def _run_sync_cycle(app, *, is_retry: bool = False) -> dict:
    """
    Run one sync pass, notify the owner, and analyse anything new.

    Shared by the 18:30 job and the 15-minute retry job so both paths behave
    identically. Returns the sync result dict.
    """
    # Import at call time so test patches on the marketmeter source modules
    # take effect (the legacy `scheduler` shim was removed in Phase 6 — importing
    # it raised ModuleNotFoundError and silently disabled the 18:30 sync).
    from marketmeter.sources.nse import sync_incremental_data
    from marketmeter.telegram import send_to_owner
    from marketmeter.analysis import run_batch_analysis
    from marketmeter.reports import warm_report_cache

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
    for job in jq.get_jobs_by_name("sync_retry"):
        job.schedule_removal()

    jq.run_once(
        _sync_retry_job,
        when=SYNC_RETRY_INTERVAL_MINUTES * 60,
        name="sync_retry",
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
        # Direct module refs (not the deleted shim) so test patches on
        # _run_sync_cycle / _schedule_sync_retry work cleanly.
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
                from marketmeter.telegram import send_to_owner
                from marketmeter.core.config import SYNC_RETRY_UNTIL_HOUR, SYNC_TIME
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


__all__ = [
    "confirm_bhavcopy_insertion",
    "_run_sync_cycle",
    "_schedule_sync_retry",
    "_sync_retry_job",
]