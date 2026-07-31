"""
Validators
Input validation utilities.
"""
import re
from datetime import date
from typing import Any

# NSE symbol pattern (uppercase alphanumeric, 1-10 chars)
SYMBOL_PATTERN = re.compile(r'^[A-Z0-9&]{1,10}$')

# Email pattern
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Chat ID pattern (Telegram chat IDs are integers, can be negative for groups)
CHAT_ID_PATTERN = re.compile(r'^-?\d+$')


def validate_symbol(symbol: str) -> bool:
    """Validate NSE symbol format."""
    if not symbol:
        return False
    symbol = symbol.upper().strip()
    return bool(SYMBOL_PATTERN.match(symbol))


def validate_date(date_str: str) -> date | None:
    """Validate and parse date string (YYYY-MM-DD)."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def validate_chat_id(chat_id: Any) -> int | None:
    """Validate and convert chat ID."""
    try:
        return int(chat_id)
    except (ValueError, TypeError):
        return None


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False
    return bool(EMAIL_PATTERN.match(email))


def validate_time_str(time_str: str) -> bool:
    """Validate HH:MM time string."""
    try:
        hour, minute = map(int, time_str.split(':'))
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AttributeError):
        return False


def sanitize_symbol(symbol: str) -> str:
    """Sanitize symbol input."""
    if not symbol:
        return ""
    return symbol.upper().strip()


def sanitize_text(text: str, max_length: int = 4096) -> str:
    """Sanitize text for Telegram messages."""
    if not text:
        return ""
    # Remove control characters except newlines and tabs
    sanitized = ''.join(c for c in text if c == '\n' or c == '\t' or ord(c) >= 32)
    return sanitized[:max_length]


def validate_positive_number(value: Any, min_value: float = 0) -> float | None:
    """Validate positive number."""
    try:
        num = float(value)
        if num >= min_value:
            return num
    except (ValueError, TypeError):
        pass
    return None


def validate_integer(value: Any, min_value: int = None, max_value: int = None) -> int | None:
    """Validate integer within range."""
    try:
        num = int(value)
        if min_value is not None and num < min_value:
            return None
        if max_value is not None and num > max_value:
            return None
        return num
    except (ValueError, TypeError):
        return None


def validate_list_items(items: list[str], validator: callable) -> list[str]:
    """Validate all items in a list."""
    return [item for item in items if validator(item)]


class ValidationError(Exception):
    """Validation error with details."""

    def __init__(self, message: str, field: str = None, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value
