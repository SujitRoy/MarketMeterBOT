"""
telegram/handlers/report — /report command handler.

Supports optional date argument:
    /report              → latest available analysis date
    /report 2026-07-15   → report for 15 Jul 2026 (YYYY-MM-DD)
    /report 15-07-2026   → also works (DD-MM-YYYY)
"""
from __future__ import annotations

import asyncio
import re
from datetime import date

from telegram import Update
from telegram.ext import CommandHandler

from marketmeter.core.logging import get_logger
from marketmeter.reports import generate_morning_report
from marketmeter.telegram.rich.send import _send_report_in_chunks
from marketmeter.db import analysis_date_exists, get_analysis_date_range

logger = get_logger(__name__)

# ── Date parsing ────────────────────────────────────────────────────

# Accept YYYY-MM-DD or DD-MM-YYYY (with dashes or forward slashes)
_DATE_PATTERN = re.compile(
    r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$"    # YYYY-MM-DD
    r"|^\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*$"    # DD-MM-YYYY
)


def _parse_report_date(raw: str) -> date | None:
    """Parse a date string from /report <date>. Returns None if invalid."""
    m = _DATE_PATTERN.match(raw)
    if not m:
        return None
    if m.group(1):  # YYYY-MM-DD
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:  # DD-MM-YYYY
        d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _format_date_error(raw: str) -> str:
    """Build an error message when the user passes an unparseable date."""
    from_date, to_date = get_analysis_date_range()
    range_hint = ""
    if from_date and to_date:
        range_hint = (
            f"\n📅 **Available date range:** `{from_date}` to `{to_date}`"
        )

    return (
        f"❌ Invalid date: `{raw}`\n\n"
        f"**Supported formats:**\n"
        f"• `YYYY-MM-DD` — e.g. `/report 2026-07-15`\n"
        f"• `DD-MM-YYYY` — e.g. `/report 15-07-2026`\n"
        f"{range_hint}\n\n"
        f"💡 Use `/report` (without a date) for the latest available report."
    )


def _format_no_data_date(target: date) -> str:
    """Build an error message when no analysis exists for the given date."""
    from_date, to_date = get_analysis_date_range()
    range_hint = ""
    if from_date and to_date:
        range_hint = f"\n📅 **Available range:** `{from_date}` to `{to_date}`"

    return (
        f"⚠️ No analysis data available for `{target.isoformat()}`."
        f"{range_hint}\n\n"
        f"💡 Use `/report` (without a date) for the latest available report."
    )


# ── Command handler ─────────────────────────────────────────────────

async def cmd_report(update: Update, context):
    """Handle /report command — send latest analysis or date-specific report."""

    # Parse optional date argument
    raw_date = " ".join(context.args) if context.args else ""
    target_date: date | None = None

    if raw_date:
        target_date = _parse_report_date(raw_date)
        if target_date is None:
            await update.message.reply_text(_format_date_error(raw_date))
            return

        # Reject future dates
        today = date.today()
        if target_date > today:
            await update.message.reply_text(
                f"❌ `{target_date.isoformat()}` is in the future. "
                "Analysis data is not yet available for this date.\n\n"
                f"💡 Use `/report` (without a date) for the latest available report."
            )
            return

        # Check data exists for this date
        if not analysis_date_exists(target_date):
            await update.message.reply_text(_format_no_data_date(target_date))
            return

    # Send temp message
    temp_msg = await update.message.reply_text("🔍 Generating report...")

    try:
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            generate_morning_report,
            target_date,  # None → auto-detect latest
        )

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