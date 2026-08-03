"""
db/connection — single SQLite connection factory for MarketMeter.

All repos under db/ obtain connections exclusively through get_connection().
This is the only file that knows the pragma values, the WAL mode, and the
path. If a future migration needs to swap SQLite for Postgres, this is the
single point of change.

Phase 2 moves the original get_connection() from /database.py here verbatim.
Existing callers (and the /database.py shim) keep working because
db/__init__.py re-exports get_connection().
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from marketmeter.core.config import DB_PATH
from marketmeter.core.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a sqlite3 connection optimized for 1GB RAM server."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Memory-optimized settings for 1GB RAM
    conn.execute("PRAGMA journal_mode = WAL")          # Faster, less memory
    conn.execute("PRAGMA synchronous = NORMAL")       # Balance speed/safety
    conn.execute("PRAGMA cache_size = -32768")        # 32MB cache (not 64MB)
    conn.execute("PRAGMA temp_store = MEMORY")        # Temp tables in RAM
    conn.execute("PRAGMA mmap_size = 134217728")      # 128MB mmap (not 256MB)
    conn.execute("PRAGMA page_size = 4096")           # Optimal page size
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # Prevent bloat
    conn.execute("PRAGMA secure_delete = OFF")        # Faster deletes
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


__all__ = ["get_connection"]