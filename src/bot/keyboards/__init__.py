"""
Keyboards Package
Inline keyboards for the bot.
"""
from src.bot.keyboards.menu import (
    build_confirmation_keyboard,
    build_menu_keyboard,
    build_pagination_keyboard,
    build_report_type_keyboard,
    build_settings_keyboard,
    build_symbol_keyboard,
)
from src.bot.keyboards.pagination import (
    PaginatedKeyboard,
    PaginationConfig,
    create_simple_pagination,
)

__all__ = [
    # Menu
    "build_menu_keyboard",
    "build_settings_keyboard",
    "build_confirmation_keyboard",
    "build_pagination_keyboard",
    "build_symbol_keyboard",
    "build_report_type_keyboard",

    # Pagination
    "PaginationConfig",
    "PaginatedKeyboard",
    "create_simple_pagination",
]
