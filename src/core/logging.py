"""
MarketMeter Logging Configuration
Centralized logging setup with structured JSON support.
"""
import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

from src.core.config import LOG_BACKUP_COUNT, LOG_FILE, LOG_FORMAT, LOG_LEVEL, LOG_MAX_BYTES


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        if hasattr(record, "context"):
            log_obj["context"] = record.context
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


class ContextFilter(logging.Filter):
    """Add context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Add default context if not present
        if not hasattr(record, "context"):
            record.context = {}
        return True


def setup_logging(
    log_file: Path = LOG_FILE,
    log_level: str = LOG_LEVEL,
    json_format: bool = False,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    """
    Configure application logging.
    
    Args:
        log_file: Path to log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_format: Use JSON formatting (for log aggregation)
        max_bytes: Max size per log file
        backup_count: Number of backup files to keep
    """
    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Set level
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    # Choose formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(LOG_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # Add context filter
    context_filter = ContextFilter()
    root_logger.addFilter(context_filter)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logging.info("Logging initialized: level=%s, file=%s, json=%s", log_level, log_file, json_format)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding structured context to logs."""

    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.old_context = {}

    def __enter__(self):
        # Store existing context
        for handler in self.logger.handlers:
            for filter_ in handler.filters:
                if isinstance(filter_, ContextFilter):
                    # We can't easily access the filter's context, so we'll
                    # add context via the extra parameter instead
                    pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def log(self, level: int, message: str, **extra_context):
        """Log with combined context."""
        combined = {**self.context, **extra_context}
        self.logger.log(level, message, extra={"context": combined})


# Convenience function for structured logging
def log_with_context(logger: logging.Logger, level: int, message: str, **context):
    """Log a message with structured context."""
    logger.log(level, message, extra={"context": context})
