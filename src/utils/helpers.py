"""
Helper Utilities
General-purpose helper functions.
"""
import hashlib
import json
import logging
from datetime import date, datetime
from typing import Any


def generate_hash(data: str | dict | list, length: int = 16) -> str:
    """Generate short hash for data."""
    if isinstance(data, (dict, list)):
        data = json.dumps(data, sort_keys=True)
    return hashlib.md5(data.encode()).hexdigest()[:length]


def safe_get(data: dict, *keys, default: Any = None) -> Any:
    """Safely get nested dictionary value."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current


def chunk_list(lst: list[Any], size: int) -> list[list[Any]]:
    """Split list into chunks of given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def flatten_dict(d: dict, parent_key: str = '', sep: str = '.') -> dict:
    """Flatten nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def merge_dicts(*dicts: dict) -> dict:
    """Merge multiple dictionaries (later values override earlier)."""
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result


def filter_none_values(d: dict) -> dict:
    """Remove keys with None values from dictionary."""
    return {k: v for k, v in d.items() if v is not None}


def truncate_text(text: str, max_length: int = 4096, suffix: str = "...") -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def split_text(text: str, max_chunk: int = 3800) -> list[str]:
    """Split text into chunks under max_chunk size, preserving lines."""
    if len(text) <= max_chunk:
        return [text]

    chunks = []
    lines = text.split('\n')
    current = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chunk and current:
            chunks.append('\n'.join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append('\n'.join(current))

    return chunks


def format_datetime(dt: datetime, fmt: str = "%d %b %Y, %H:%M") -> str:
    """Format datetime for display."""
    if dt is None:
        return "—"
    return dt.strftime(fmt)


def format_date(d: date, fmt: str = "%d %b %Y") -> str:
    """Format date for display."""
    if d is None:
        return "—"
    return d.strftime(fmt)


def parse_bool(value: Any) -> bool:
    """Parse various boolean representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1', 'on', 'y', 't')
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def get_nested(data: dict, path: str, default: Any = None, sep: str = '.') -> Any:
    """Get nested value using dot notation path."""
    keys = path.split(sep)
    return safe_get(data, *keys, default=default)


def set_nested(data: dict, path: str, value: Any, sep: str = '.') -> None:
    """Set nested value using dot notation path."""
    keys = path.split(sep)
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def deep_update(source: dict, updates: dict) -> dict:
    """Deep update dictionary."""
    for key, value in updates.items():
        if isinstance(value, dict) and key in source and isinstance(source[key], dict):
            deep_update(source[key], value)
        else:
            source[key] = value
    return source


def json_dumps_safe(obj: Any, **kwargs) -> str:
    """JSON dumps with default handlers for common types."""
    def default_handler(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if hasattr(o, '__dict__'):
            return o.__dict__
        return str(o)

    return json.dumps(obj, default=default_handler, **kwargs)


def load_json_safe(filepath: str, default: Any = None) -> Any:
    """Load JSON file safely."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.getLogger(__name__).warning("Failed to load %s: %s", filepath, e)
        return default


def save_json_safe(filepath: str, data: Any, indent: int = 2) -> bool:
    """Save JSON file safely."""
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=indent, default=str)
        return True
    except Exception as e:
        logging.getLogger(__name__).error("Failed to save %s: %s", filepath, e)
        return False
