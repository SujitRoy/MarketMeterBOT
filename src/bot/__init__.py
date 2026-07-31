"""
Bot Package
Telegram bot components: application, handlers, keyboards, middlewares, filters.
"""
from src.bot.application import create_application, setup_bot, shutdown_bot
from src.bot.filters import (
    channel_chat,
    group_chat,
    non_private_chat,
    private_chat,
)
from src.bot.handlers import register_handlers
from src.bot.keyboards import (
    PaginatedKeyboard,
    PaginationConfig,
    build_confirmation_keyboard,
    build_menu_keyboard,
    build_pagination_keyboard,
    build_report_type_keyboard,
    build_settings_keyboard,
    build_symbol_keyboard,
    create_simple_pagination,
)
from src.bot.middlewares import (
    LoggingMiddleware,
    RateLimitMiddleware,
    logging_middleware,
    rate_limit_middleware,
    setup_middlewares,
)

__all__ = [
    # Application
    "create_application",
    "setup_bot",
    "shutdown_bot",

    # Handlers
    "register_handlers",

    # Keyboards
    "build_menu_keyboard",
    "build_settings_keyboard",
    "build_confirmation_keyboard",
    "build_pagination_keyboard",
    "build_symbol_keyboard",
    "build_report_type_keyboard",
    "PaginationConfig",
    "PaginatedKeyboard",
    "create_simple_pagination",

    # Middlewares
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "logging_middleware",
    "rate_limit_middleware",
    "setup_middlewares",

    # Filters
    "private_chat",
    "group_chat",
    "channel_chat",
    "non_private_chat",
]
