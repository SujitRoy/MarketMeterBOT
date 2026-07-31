"""
Database Connection Management
Optimized for low-memory server (954 MB RAM).
"""
import logging
import sqlite3
from contextlib import contextmanager
from typing import Any

from src.core.config import DB_PATH
from src.core.constants import DB_PRAGMAS
from src.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply optimized PRAGMA settings for memory-constrained server."""
    for pragma, value in DB_PRAGMAS.items():
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        elif isinstance(value, str) and value.lower() in ("on", "off"):
            value = value.upper()
        conn.execute(f"PRAGMA {pragma} = {value}")


@contextmanager
def get_connection() -> sqlite3.Connection:
    """
    Yield a sqlite3 connection optimized for 1GB RAM server.
    
    Uses context manager pattern to ensure proper cleanup.
    """
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        logger.error("Database error: %s", e)
        raise DatabaseError(f"Database operation failed: {e}") from e
    finally:
        if conn:
            conn.close()


@contextmanager
def get_readonly_connection() -> sqlite3.Connection:
    """
    Yield a read-only sqlite3 connection for queries that don't modify data.
    
    Uses a separate connection to avoid interfering with write transactions.
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30.0)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        yield conn
    except sqlite3.Error as e:
        logger.error("Read-only database error: %s", e)
        raise DatabaseError(f"Read-only database operation failed: {e}") from e
    finally:
        if conn:
            conn.close()


def init_database() -> None:
    """Initialize database schema and run migrations."""
    from src.database.migrations import run_migrations
    run_migrations()
    logger.info("Database initialized at %s", DB_PATH)


def vacuum_database() -> None:
    """Reclaim space and optimize database."""
    with get_connection() as conn:
        conn.execute("VACUUM")
    logger.info("Database vacuumed")


def check_database_health() -> dict[str, Any]:
    """
    Check database health and return diagnostic information.
    
    Returns:
        Dict with health metrics
    """
    with get_connection() as conn:
        # Check integrity
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        # Get page info
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        db_size_mb = (page_count * page_size) / (1024 * 1024)

        # Check WAL mode
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

        # Get table stats
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        table_stats = {}
        for table in tables:
            name = table[0]
            if name.startswith("sqlite_"):
                continue
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            table_stats[name] = count

        return {
            "integrity": integrity,
            "size_mb": round(db_size_mb, 2),
            "page_count": page_count,
            "page_size": page_size,
            "journal_mode": journal_mode,
            "tables": table_stats,
        }
