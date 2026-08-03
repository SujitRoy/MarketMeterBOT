"""
telegram/handlers — command handlers.
"""
from __future__ import annotations

from .core import core_handlers
from .report import report_handlers
from .search import search_handlers

__all__ = ["core_handlers", "report_handlers", "search_handlers"]