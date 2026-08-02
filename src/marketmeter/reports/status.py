"""
reports/status — sync status, sync failure alert, /status command response.

Phase 4 split: generate_sync_status_message, generate_sync_failure_alert, and
generate_status_message moved here from /report_generator.py. They share the
owner-DM and /status-command responsibilities and stay together.
"""
from __future__ import annotations

from datetime import datetime

from marketmeter.core.config import (
    BOT_DISPLAY_NAME, SYNC_TIME, REPORT_TIME, SYNC_RETRY_INTERVAL_MINUTES,
)
from marketmeter.db import get_db_stats, get_sync_status


def generate_sync_status_message(sync_result: dict) -> str:
    """Generate a sync completion/failure notification for the owner."""
    status = sync_result.get('status', 'unknown')
    now = datetime.now().strftime('%d %b %Y, %I:%M %p IST')

    if status == 'up_to_date':
        return f"""✅ *{BOT_DISPLAY_NAME} Sync Status*

📅 {now}
📊 Status: Already up to date
💾 No new data to sync.

_Everything is current._"""

    if status == 'completed':
        success = sync_result.get('success', 0)
        failed = sync_result.get('failed', 0)
        holidays = sync_result.get('holidays', 0)
        not_available = sync_result.get('not_available', [])
        records = sync_result.get('total_records', 0)
        processed = sync_result.get('dates_processed', 0)

        emoji = "✅" if failed == 0 and not not_available else "⚠️"

        lines = [
            f"{emoji} *{BOT_DISPLAY_NAME} Sync Completed*",
            "",
            f"📅 {now}",
            f"📊 Dates processed: {processed}",
            f"✅ Success: {success} | ❌ Failed: {failed} | 🏖️ Holidays: {holidays} | ⏳ Pending: {len(not_available)}",
            f"📥 Records inserted: {records:,}",
        ]

        if records > 0:
            lines.append("")
            lines.append(f"✅ *BhavCopy data inserted: {records:,} records*")

        if not_available:
            lines.append("")
            lines.append(f"⏳ *Pending dates (NSE not ready):* {', '.join(not_available)}")
            lines.append("_Will retry on next sync._")

        if failed > 0:
            lines.append("")
            lines.append("⚠️ *Failed dates will be retried on next sync.*")

        return "\n".join(lines)

    return f"""❌ *{BOT_DISPLAY_NAME} Sync Failed*

📅 {now}
❌ Status: {status}
📝 {sync_result.get('message', 'Unknown error')}

_Sync will be retried on next schedule._"""


def generate_sync_failure_alert(error_message: str) -> str:
    """Generate an alert when sync completely fails."""
    now = datetime.now().strftime('%d %b %Y, %I:%M %p IST')
    return f"""🚨 *{BOT_DISPLAY_NAME} Sync Alert*

📅 {now}
❌ Sync encountered an error:

```
{error_message[:500]}
```

_The scheduler will retry on the next cycle._
_Check logs for details: `tail -50 logs/bot.log`_"""


def generate_status_message() -> str:
    """Generate a detailed status message for the /status command."""
    db_stats = get_db_stats()
    sync_logs = get_sync_status(days=5)

    lines = [
        "📊 **MarketMeter Status**",
        "",
        "**Database**",
        f"• Records: {db_stats['total_records']:,}",
        f"• Symbols: {db_stats['unique_symbols']:,}",
        f"• Range: {db_stats['date_from']} → {db_stats['date_to']}",
        f"• Subscribers: {db_stats['active_subscribers']}",
        "",
        "**Recent Syncs**",
        "",  # blank line required: the local Bot API server only parses a
             # pipe-table as a native RichBlockTable when it starts a fresh
             # paragraph. Adjacent to '**Recent Syncs**' it flattened to a
             # paragraph and /status rendered as raw pipe text.
    ]

    if sync_logs:
        lines.append("| Date | Status | Records |")
        lines.append("|:-----|:-------|--------:|")
        for log in sync_logs[:5]:
            status_emoji = {
                'success': '✅', 'failed': '❌',
                'holiday': '🏖️', 'skipped': '⏭️',
                'not_available': '⏳',
            }.get(log['status'], '❓')
            lines.append(
                f"| {log['trade_date']} | {status_emoji} {log['status']} | "
                f"{log['records_count']:,} |"
            )
    else:
        lines.append("• No sync history yet")

    lines.append("")
    lines.append("⏰ **Schedule**")
    lines.append(f"• Sync: {SYNC_TIME} IST daily (retries every "
                 f"{SYNC_RETRY_INTERVAL_MINUTES} min until published)")
    lines.append(f"• Report: {REPORT_TIME} IST daily")

    return "\n".join(lines)


__all__ = [
    "generate_sync_status_message",
    "generate_sync_failure_alert",
    "generate_status_message",
]