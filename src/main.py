#!/usr/bin/env python3
"""
MarketMeter — Main Entry Point
────────────────────────────────
Starts the Telegram bot, registers scheduled jobs, and runs the event loop.

Usage:
    python -m src.main                  # Normal start (bot + scheduler)
    python -m src.main --sync           # Run sync once and exit
    python -m src.main --backfill       # Run full historical backfill
    python -m src.main --report         # Generate and broadcast report once
    python -m src.main --analyze        # Run analysis only
    python -m src.main --status         # Show database status
"""
import argparse
import asyncio
import fcntl
import logging
import os
import signal
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bot.application import create_application, setup_bot
from src.core.config import (
    DATA_DIR,
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_FORMAT,
    LOG_LEVEL,
    LOG_MAX_BYTES,
)
from src.database.connection import init_database
from database import get_db_stats
from src.scheduler import setup_scheduled_jobs

# ── Single-instance Lock ────────────────────────────────────────────
LOCK_FILE = DATA_DIR / "marketmeter.lock"


def _acquire_lock():
    """
    Take an exclusive advisory lock so only one instance touches the DB.
    """
    try:
        fd = os.open(str(LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as e:
        logger.error(
            "Cannot open lock file %s: %s. Verify the data directory is writable.",
            LOCK_FILE, e,
        )
        return None

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None

    try:
        os.truncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        pass

    return fd


# ── Logging Setup ───────────────────────────────────────────────────

from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[file_handler],
)
logger = logging.getLogger("MarketMeter")

# Suppress noisy library logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


# ── CLI Commands ────────────────────────────────────────────────────

async def cmd_sync():
    """Run incremental sync once."""
    from src.analysis import run_batch_analysis
    from src.data.sync import SyncEngine
    from src.reports import generate_sync_status_message

    logger.info("Running one-time sync...")
    engine = SyncEngine()
    result = engine.run_incremental_sync()
    msg = generate_sync_status_message({
        'status': result.status,
        'success': result.success,
        'failed': result.failed,
        'holidays': result.holidays,
        'not_available': result.not_available,
        'total_records': result.total_records,
        'dates_processed': result.dates_processed,
    })
    print(msg)

    # If new data, run analysis
    if result.status == 'completed' and result.total_records > 0:
        logger.info("Running analysis on new data...")
        analysis_result = run_batch_analysis()
        print(f"Analysis: {analysis_result['message']}")


async def cmd_backfill():
    """Run full historical backfill."""
    from src.data.sync import BackfillEngine

    logger.info("Starting full historical backfill...")
    print("This will download data from 2022-01-01 to today.")
    print("Estimated time: 20-30 minutes for ~1100 trading days.")
    response = input("Continue? (y/n): ").strip().lower()

    if response != 'y':
        print("Aborted.")
        return

    engine = BackfillEngine()
    result = engine.run_backfill()
    print(f"\nBackfill complete: {result.message}")

    # Run analysis after backfill
    logger.info("Running initial analysis...")
    from src.analysis import run_batch_analysis
    analysis_result = run_batch_analysis()
    print(f"Analysis: {analysis_result['message']}")


async def cmd_report():
    """Generate and print report once."""
    from src.reports import generate_morning_report
    report = generate_morning_report()
    print(report)


async def cmd_analyze():
    """Run analysis only."""
    from src.analysis import run_batch_analysis
    result = run_batch_analysis()
    print(result['message'])


async def cmd_status():
    """Print database status."""
    stats = get_db_stats()
    print("=" * 50)
    print("MarketMeter Database Status")
    print("=" * 50)
    for key, value in stats.items():
        print(f"  {key}: {value}")


# ── Main Bot Runner ─────────────────────────────────────────────────

async def run_bot():
    """Start the bot with scheduled jobs."""
    # Initialize database
    init_database()
    logger.info("Database initialized")

    # Create bot application
    app = create_application()

    # Register scheduled jobs
    setup_scheduled_jobs(app)

    # Initialize bot first
    await setup_bot(app)

    await app.start()

    # Show startup stats
    stats = get_db_stats()
    logger.info("DB Stats: %d records, %d symbols, %d subscribers",
                stats['total_records'], stats['unique_symbols'], stats['active_subscribers'])

    # Send startup notification to owner
    from src.bot import send_to_owner
    await send_to_owner(app, (
        f"🟢 *MarketMeter Started*\n"
        f"• Records: {stats['total_records']:,}\n"
        f"• Symbols: {stats['unique_symbols']:,}\n"
        f"• Subscribers: {stats['active_subscribers']:,}\n"
        f"• Sync: 6:30 PM IST | Report: 8:00 AM IST"
    ))

    logger.info("Bot is running. Press Ctrl+C to stop.")

    # Start polling in the background
    polling_task = asyncio.create_task(
        app.updater.start_polling(drop_pending_updates=True)
    )

    # Wait for shutdown signal
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await stop_event.wait()

    # Graceful shutdown
    logger.info("Shutting down...")
    await send_to_owner(app, "🔴 *MarketMeter Stopped*")

    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    await app.updater.stop()
    await app.stop()
    await app.shutdown()

    logger.info("Bot stopped. Goodbye!")


# ── Entry Point ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MarketMeter — NSE Stock Analysis & Telegram Bot"
    )
    parser.add_argument(
        "--sync", action="store_true",
        help="Run incremental sync once and exit"
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Run full historical backfill (2022-01-01 to today)"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Generate and print morning report"
    )
    parser.add_argument(
        "--analyze", action="store_true",
        help="Run technical analysis only"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show database status"
    )

    args = parser.parse_args()

    # ALL modes need the lock to prevent concurrent DB access/corruption
    lock_fd = _acquire_lock()
    if lock_fd is None:
        logger.error("Another instance of MarketMeterBOT is already running. Exiting.")
        sys.exit(1)

    try:
        if args.sync:
            asyncio.run(cmd_sync())
        elif args.backfill:
            asyncio.run(cmd_backfill())
        elif args.report:
            asyncio.run(cmd_report())
        elif args.analyze:
            asyncio.run(cmd_analyze())
        elif args.status:
            asyncio.run(cmd_status())
        else:
            # Normal mode: run the bot
            asyncio.run(run_bot())

    finally:
        # Release lock
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
