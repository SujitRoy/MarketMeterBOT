"""
telegram/app — application factory (create_application).
"""
from __future__ import annotations

from telegram.ext import Application

from marketmeter.core.config import BOT_TOKEN, TELEGRAM_API_BASE_URL
from marketmeter.telegram.menu import _setup_menu_button, _setup_menu_button_post_start
from marketmeter.telegram.handlers.core import core_handlers
from marketmeter.telegram.handlers.report import report_handlers
from marketmeter.telegram.handlers.search import search_handlers

from marketmeter.core.logging import get_logger

logger = get_logger(__name__)


def create_application() -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(BOT_TOKEN).base_url(TELEGRAM_API_BASE_URL).build()

    # Register command handlers
    for h in core_handlers:
        app.add_handler(h)
    for h in report_handlers:
        app.add_handler(h)
    for h in search_handlers:
        app.add_handler(h)

    # Post-init & post-start: set menu button (≡) in chat typing area
    app.post_init = _setup_menu_button
    app.post_start = _setup_menu_button_post_start

    logger.info("Bot application created with %d handlers",
                len(core_handlers) + len(report_handlers) + len(search_handlers))
    return app


__all__ = ["create_application"]