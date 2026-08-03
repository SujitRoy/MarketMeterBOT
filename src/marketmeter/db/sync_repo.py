"""
db/sync_repo — CRUD for the `sync_log` table.

Phase 2 moves (verbatim from /database.py):
- log_sync
- get_last_synced_date
- get_sync_status
- get_failed_syncs
- get_holiday_dates

All SQL is byte-identical to the original.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from marketmeter.db.connection import get_connection


def log_sync(trade_date: date, status: str, records: int = 0, error: str = None):
    """Record a sync attempt."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO sync_log (trade_date, status, records_count, error_message, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (trade_date.isoformat(), status, records, error))


def get_last_synced_date() -> Optional[date]:
    """Get the last successfully synced trade date."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT trade_date FROM sync_log
            WHERE status = 'success'
            ORDER BY trade_date DESC
            LIMIT 1
        """).fetchone()
        if row:
            return date.fromisoformat(row['trade_date'])
        return None


def get_sync_status(days: int = 10) -> list[dict]:
    """Get recent sync log entries."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT trade_date, status, records_count, error_message, synced_at
            FROM sync_log
            ORDER BY trade_date DESC
            LIMIT ?
        """, (days,)).fetchall()
        return [dict(r) for r in rows]


def get_failed_syncs() -> list[dict]:
    """Get all failed/not_available syncs that need retry."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT trade_date, error_message
            FROM sync_log
            WHERE status IN ('failed', 'not_available')
            ORDER BY trade_date
        """).fetchall()
        return [dict(r) for r in rows]


def get_holiday_dates() -> list[dict]:
    """Get dates marked as confirmed holidays (weekends + known NSE holidays)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT trade_date
            FROM sync_log
            WHERE status = 'holiday'
            ORDER BY trade_date
        """).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "log_sync",
    "get_last_synced_date",
    "get_sync_status",
    "get_failed_syncs",
    "get_holiday_dates",
]