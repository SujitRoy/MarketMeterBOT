"""
db/subscriber_repo — CRUD for the `subscribers` table.

Phase 2 moves (verbatim from /database.py):
- add_subscriber
- remove_subscriber
- get_active_subscribers
- get_all_subscribers
- get_subscriber_count

All SQL is byte-identical to the original.
"""
from __future__ import annotations

from marketmeter.db.connection import get_connection


def add_subscriber(chat_id: int, username: str = None,
                   first_name: str = None, last_name: str = None) -> bool:
    """Add or re-activate a subscriber. Returns True if newly added."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT chat_id, active FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if existing:
            if not existing['active']:
                conn.execute("""
                    UPDATE subscribers SET active = 1, receive_reports = 1,
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name),
                        last_name = COALESCE(?, last_name)
                    WHERE chat_id = ?
                """, (username, first_name, last_name, chat_id))
                return True
            return False
        else:
            conn.execute("""
                INSERT INTO subscribers (chat_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (chat_id, username, first_name, last_name))
            return True


def remove_subscriber(chat_id: int) -> bool:
    """Soft-delete a subscriber. Returns True if they existed and were active."""
    with get_connection() as conn:
        cur = conn.execute("""
            UPDATE subscribers SET active = 0, receive_reports = 0
            WHERE chat_id = ? AND active = 1
        """, (chat_id,))
        return cur.rowcount > 0


def get_active_subscribers() -> list[dict]:
    """Get all active subscribers who want reports."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT chat_id, username, first_name, last_name
            FROM subscribers
            WHERE active = 1 AND receive_reports = 1
        """).fetchall()
        return [dict(r) for r in rows]


def get_all_subscribers() -> list[dict]:
    """Get all subscribers (including inactive)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT chat_id, username, first_name, last_name, active, receive_reports, subscribed_at
            FROM subscribers
            ORDER BY subscribed_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_subscriber_count() -> int:
    """Count of active subscribers."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM subscribers WHERE active = 1"
        ).fetchone()
        return row['cnt']


__all__ = [
    "add_subscriber",
    "remove_subscriber",
    "get_active_subscribers",
    "get_all_subscribers",
    "get_subscriber_count",
]