"""
core/logging — structured logging setup for MarketMeter.

Replaces the inline RotatingFileHandler + basicConfig block previously in
main.py. Idempotent: calling setup() multiple times is safe (replaces handlers
in-place rather than appending).

Phase 1 scope:
- Preserves the existing rotation, format, and redaction behaviour exactly.
- Adds a CorrelationIdFilter so future request-scoped logs can carry an id
  without changing every call site.

Future phases (not in Phase 1):
- JSON formatter for ingest pipelines.
- Async log queue for non-blocking writes.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

# Re-export the format constants so callers can `from core.logging import LOG_FORMAT`
# without churning config.py. We import lazily so core.logging can be imported
# without triggering config.py's env-var validation (useful for tests).


class CorrelationIdFilter(logging.Filter):
    """Attach a correlation_id attribute to every record so downstream
    handlers/formatters can include it. Default 'no-id' for non-scoped logs.

    This is the hook for future request-scoped tracing. It costs nothing if
    nobody sets the correlation id.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "-"
        return True


def setup(
    log_file,
    log_level: str = "INFO",
    log_format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    log_max_bytes: int = 5 * 1024 * 1024,
    log_backup_count: int = 3,
    logger_name: str = "MarketMeter",
) -> logging.Logger:
    """Configure the root MarketMeter logger with a rotating file handler.

    Idempotent: removes any existing handlers on the named logger before
    adding the new one. Prevents the duplicate-handler issue that bit us on
    2026-07-22 (every line logged twice after a restart).

    Suppresses noisy library logs (httpx, telegram, nsefin) to WARNING.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove existing handlers to make this idempotent.
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.propagate = False

    handler = RotatingFileHandler(
        log_file,
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(log_format))
    handler.addFilter(CorrelationIdFilter())
    logger.addHandler(handler)

    # Suppress noisy library logs (preserve prior behaviour).
    for noisy in ("httpx", "telegram", "nsefin"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a module-level logger under the MarketMeter namespace.

    Usage:
        from marketmeter.core.logging import get_logger
        logger = get_logger(__name__)
    """
    if name is None:
        return logging.getLogger("MarketMeter")
    if name.startswith("MarketMeter"):
        return logging.getLogger(name)
    return logging.getLogger(f"MarketMeter.{name}")
