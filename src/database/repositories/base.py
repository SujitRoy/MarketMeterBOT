"""
Base Repository Class
Common database operations for all repositories.
"""
import logging
from contextlib import contextmanager
from typing import Any, TypeVar

from src.database.connection import get_connection, get_readonly_connection
from src.database.queries import *

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository:
    """Base class for all repositories providing common operations."""

    def __init__(self, readonly: bool = False):
        self.readonly = readonly

    @contextmanager
    def _connection(self):
        """Get appropriate connection based on readonly flag."""
        if self.readonly:
            with get_readonly_connection() as conn:
                yield conn
        else:
            with get_connection() as conn:
                yield conn

    def execute(self, query: str, params: tuple = ()) -> int:
        """Execute a write query and return rowcount."""
        with self._connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount

    def execute_many(self, query: str, params_list: list[tuple]) -> int:
        """Execute a query with multiple parameter sets."""
        with self._connection() as conn:
            before = conn.total_changes
            conn.executemany(query, params_list)
            return conn.total_changes - before

    def fetch_one(self, query: str, params: tuple = ()) -> dict[str, Any] | None:
        """Fetch a single row as dict."""
        with self._connection() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Fetch all rows as list of dicts."""
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def fetch_scalar(self, query: str, params: tuple = ()) -> Any:
        """Fetch a single scalar value."""
        with self._connection() as conn:
            row = conn.execute(query, params).fetchone()
            return row[0] if row else None


class ReadOnlyRepository(BaseRepository):
    """Repository for read-only operations."""

    def __init__(self):
        super().__init__(readonly=True)
