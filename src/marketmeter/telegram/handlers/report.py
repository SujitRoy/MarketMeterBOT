"""
telegram/handlers/report — /report command handler.
"""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CommandHandler

from marketmeter.core.logging import get_logger
from marketmeter.reports import generate_morning_report
from marketmeter.telegram.rich.send import _send_report_in_chunks

logger = get_logger(__name__)


async def cmd_report(update: Update, context):
    """Handle /report command — send latest analysis on demand."""

    # Send temp message
    temp_msg = await update.message.reply_text("🔍 Generating report...")

    try:
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        # Always use latest available analysis date (no arg = auto-detect)
        report = await loop.run_in_executor(None, generate_morning_report)

        # Delete temp message
        try:
            await temp_msg.delete()
        except Exception:
            pass

        # Send in chunks using Rich Messages
        await _send_report_in_chunks(update.message, report)

    except Exception as e:
        logger.error("Failed to generate report: %s", e)
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            "❌ Failed to generate report. Please try again later.\n"
            "Use /status to check if data is available."
        )


# ─── Handler Export ─────────────────────────────────────────────────

report_handlers = [
    CommandHandler("report", cmd_report),
]