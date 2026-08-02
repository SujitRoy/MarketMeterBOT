"""
telegram/rich — Rich Message primitives.
"""
from __future__ import annotations

from .detect import _needs_rich
from .split import _split_rich_markdown
from .send import (
    _send_rich_message, _send_rich_chunks, _send_report_in_chunks, _reply,
)

__all__ = [
    "_needs_rich",
    "_split_rich_markdown",
    "_send_rich_message", "_send_rich_chunks", "_send_report_in_chunks", "_reply",
]