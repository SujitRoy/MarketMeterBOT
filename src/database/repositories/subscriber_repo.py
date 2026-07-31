"""
Subscriber Repository
Data access for Telegram subscriber management.
"""
import logging
from typing import Any

from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository

logger = logging.getLogger(__name__)


class SubscriberRepository(BaseRepository):
    """Repository for subscriber operations."""

    def add_subscriber(
        self,
        chat_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None
    ) -> bool:
        """Add or re-activate a subscriber. Returns True if newly added."""
        with get_connection() as conn:
            existing = conn.execute(
                "SELECT chat_id, active FROM subscribers WHERE chat_id = ?", (chat_id,)
            ).fetchone()

            if existing:
                if not existing['active']:
                    conn.execute(UPDATE_SUBSCRIBER, (username, first_name, last_name, chat_id))
                    return True
                return False
            else:
                conn.execute(INSERT_SUBSCRIBER, (chat_id, username, first_name, last_name))
                return True

    def remove_subscriber(self, chat_id: int) -> bool:
        """Soft-delete a subscriber. Returns True if they existed and were active."""
        cur = self.execute(SOFT_DELETE_SUBSCRIBER, (chat_id,))
        return cur > 0

    def get_active_subscribers(self) -> list[dict[str, Any]]:
        """Get all active subscribers who want reports."""
        return self.fetch_all(GET_ACTIVE_SUBSCRIBERS)

    def get_all_subscribers(self) -> list[dict[str, Any]]:
        """Get all subscribers (including inactive)."""
        return self.fetch_all(GET_ALL_SUBSCRIBERS)

    def get_subscriber_count(self) -> int:
        """Count of active subscribers."""
        return self.fetch_scalar(GET_SUBSCRIBER_COUNT) or 0


class SubscriberReadRepository(ReadOnlyRepository):
    """Read-only repository for subscriber queries."""

    def get_active_subscribers(self) -> list[dict[str, Any]]:
        """Get all active subscribers who want reports."""
        return self.fetch_all(GET_ACTIVE_SUBSCRIBERS)

    def get_all_subscribers(self) -> list[dict[str, Any]]:
        """Get all subscribers (including inactive)."""
        return self.fetch_all(GET_ALL_SUBSCRIBERS)

    def get_subscriber_count(self) -> int:
        """Count of active subscribers."""
        return self.fetch_scalar(GET_SUBSCRIBER_COUNT) or 0
