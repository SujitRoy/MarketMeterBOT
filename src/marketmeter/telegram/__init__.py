"""
MarketMeter — Telegram transport layer.

Phase 5 split: the original /bot.py (498 LoC) and /search_handler.py (724 LoC)
became focused modules under src/marketmeter/telegram/:

    telegram/
    ├── app.py              # create_application (handler registration)
    ├── menu.py             # menu button setup
    ├── delivery.py         # send_to_owner, broadcast_to_subscribers, send_report_to_all
    ├── rich/
    │   ├── detect.py       # _needs_rich
    │   ├── split.py        # _split_rich_markdown
    │   └── send.py         # _send_rich_message, _send_rich_chunks, _send_report_in_chunks, _reply
    ├── search/
    │   ├── keyboards.py    # build_search_keyboard, _build_candidate_keyboard, _chart_keyboard
    └── handlers/
        ├── core.py         # /start /help /status /indicators /subscribe /unsubscribe
        ├── report.py       # /report
        └── search.py       # /search + on_search_select (inlined tv_symbol_lookup, detail functions)

The /bot.py and /search_handler.py shims at the project root re-export the
full public surface so existing call sites keep working through Phase 6.
"""
from __future__ import annotations

from .app import create_application
from .menu import _setup_menu_button, _setup_menu_button_post_start
from .delivery import send_to_owner, broadcast_to_subscribers, send_report_to_all

# Re-export rich message utilities
from .rich.detect import _needs_rich
from .rich.split import _split_rich_markdown
from .rich.send import (
    _send_rich_message, _send_rich_chunks, _send_report_in_chunks, _reply,
)

# Re-export search utilities (keyboards only; lookup/detail inlined in handlers/search)
from .search.keyboards import (
    build_search_keyboard, _build_candidate_keyboard, _chart_keyboard,
)

# Re-export handlers (for registration in app.py and test patching)
from .handlers.core import core_handlers
from .handlers.report import report_handlers
from .handlers.search import search_handlers

__all__ = [
    # app
    "create_application",
    # menu
    "_setup_menu_button", "_setup_menu_button_post_start",
    # delivery
    "send_to_owner", "broadcast_to_subscribers", "send_report_to_all",
    # rich
    "_needs_rich", "_split_rich_markdown",
    "_send_rich_message", "_send_rich_chunks", "_send_report_in_chunks", "_reply",
    # search
    "build_search_keyboard", "_build_candidate_keyboard", "_chart_keyboard",
    # handlers
    "core_handlers", "report_handlers", "search_handlers",
]