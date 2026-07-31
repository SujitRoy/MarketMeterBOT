"""
Handlers Package
All command handlers for the bot.
"""
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.base import BaseHandler
from src.bot.handlers.indicators import IndicatorsHandler
from src.bot.handlers.report import ReportHandler
from src.bot.handlers.search import (
    cmd_search,
    fetch_live_for_symbol,
    format_live_detail,
    on_search_select,
    search_handlers,
    send_live_stock_detail,
)
from src.bot.handlers.start import HelpHandler, StartHandler
from src.bot.handlers.status import StatusHandler
from src.bot.handlers.subscribe import SubscribeHandler, UnsubscribeHandler

__all__ = [
    "BaseHandler",
    "StartHandler",
    "HelpHandler",
    "SubscribeHandler",
    "UnsubscribeHandler",
    "ReportHandler",
    "StatusHandler",
    "IndicatorsHandler",
    "cmd_search",
    "on_search_select",
    "fetch_live_for_symbol",
    "format_live_detail",
    "send_live_stock_detail",
    "search_handlers",
    "AdminHandler",
]


def register_handlers(app) -> None:
    """Register all command handlers with the application."""
    from src.bot.handlers.search import search_handlers

    handlers = [
        StartHandler(),
        HelpHandler(),
        SubscribeHandler(),
        UnsubscribeHandler(),
        ReportHandler(),
        StatusHandler(),
        IndicatorsHandler(),
        AdminHandler(),
    ]

    for handler in handlers:
        app.add_handler(handler.get_handler())

    # Add search handlers (CommandHandler + CallbackQueryHandler)
    for h in search_handlers:
        app.add_handler(h)

    logger.info("All handlers registered")
