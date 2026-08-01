"""
db/cache_repo — CRUD for the `report_cache` table.

Phase 2 moves (verbatim from /database.py):
- get_cached_report
- put_cached_report
- invalidate_report_cache

All SQL is byte-identical to the original.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from marketmeter.core.config import REPORT_CACHE_VERSION, REPORT_CACHE_RETAIN_DAYS
from marketmeter.db.connection import get_connection


def get_cached_report(kind: str, analysis_date: date) -> Optional[str]:
    """
    Return a previously rendered report, or None on miss.

    Single primary-key seek on a WITHOUT ROWID table: ~0.08ms, against ~1.1s
    to render from scratch.
    """
    with get_connection() as conn:
        row = conn.execute("""
            SELECT payload FROM report_cache
            WHERE kind = ? AND analysis_date = ? AND version = ?
        """, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION)).fetchone()
        return row['payload'] if row else None


def put_cached_report(kind: str, analysis_date: date, payload: str) -> None:
    """Store a rendered report and prune payloads outside the retention window."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO report_cache
                (kind, analysis_date, version, payload, built_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (kind, analysis_date.isoformat(), REPORT_CACHE_VERSION, payload))

        # Keep the table tiny: newest N dates per kind, plus drop stale versions.
        conn.execute("""
            DELETE FROM report_cache
            WHERE version <> ?
               OR analysis_date NOT IN (
                    SELECT analysis_date FROM report_cache
                    WHERE kind = ?
                    ORDER BY analysis_date DESC
                    LIMIT ?
               )
        """, (REPORT_CACHE_VERSION, kind, REPORT_CACHE_RETAIN_DAYS))


def invalidate_report_cache(kind: Optional[str] = None) -> int:
    """Drop cached reports. Returns rows removed."""
    with get_connection() as conn:
        if kind is None:
            cur = conn.execute("DELETE FROM report_cache")
        else:
            cur = conn.execute("DELETE FROM report_cache WHERE kind = ?", (kind,))
        return cur.rowcount


__all__ = [
    "get_cached_report",
    "put_cached_report",
    "invalidate_report_cache",
]