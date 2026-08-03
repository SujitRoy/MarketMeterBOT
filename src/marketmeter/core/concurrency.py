"""
core/concurrency — process-level single-instance lock and async helpers.

Phase 1 moves `_acquire_lock` from main.py here. The shim at main.py keeps
calling it via re-export until Phase 6 cleans the import surface.

Future phases (not in Phase 1):
- asyncio.Semaphore wrapper for rate-limiting NSE requests.
- A shared aiohttp.ClientSession for the bot's outbound HTTP calls.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)


def acquire_lock(lock_path: Path) -> Optional[int]:
    """Take an exclusive advisory lock so only one instance touches the DB.

    Returns the held fd (int), or None if another instance owns it. The fd
    must stay open for the lifetime of the process: closing it releases the
    lock.

    Moved verbatim from main.py on 2026-08-01 (Phase 1). The original
    `_acquire_lock` name is kept as a back-compat alias.
    """
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as e:
        logger.error(
            "Cannot open lock file %s: %s. Verify the data directory is writable "
            "(systemd ProtectHome/ProtectSystem can make it read-only).",
            lock_path, e,
        )
        return None

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None

    try:
        os.truncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        # PID content is advisory only; the flock is what matters.
        pass

    return fd


# Back-compat alias for the original private name in main.py.
_acquire_lock = acquire_lock


__all__ = ["acquire_lock", "_acquire_lock"]
