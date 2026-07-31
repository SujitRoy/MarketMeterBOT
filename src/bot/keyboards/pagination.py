"""
Pagination Keyboard
Advanced pagination for large datasets.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass
class PaginationConfig:
    """Configuration for pagination."""
    items_per_page: int = 10
    max_visible_pages: int = 5
    show_first_last: bool = True
    show_page_numbers: bool = True


class PaginatedKeyboard:
    """Generates pagination keyboards for any list of items."""

    def __init__(
        self,
        items: list[Any],
        config: PaginationConfig = None,
        item_callback: Callable[[Any], str] = None,
        item_label: Callable[[Any], str] = None,
        page_callback_prefix: str = "page",
    ):
        self.items = items
        self.config = config or PaginationConfig()
        self.item_callback = item_callback or (lambda x: str(x))
        self.item_label = item_label or (lambda x: str(x))
        self.page_callback_prefix = page_callback_prefix
        self.current_page = 1
        self.total_pages = max(1, (len(items) + self.config.items_per_page - 1) // self.config.items_per_page)

    def get_page_items(self, page: int = None) -> list[Any]:
        """Get items for a specific page."""
        page = page or self.current_page
        start = (page - 1) * self.config.items_per_page
        end = start + self.config.items_per_page
        return self.items[start:end]

    def get_keyboard(self, plugin_page: int = None) -> InlineKeyboardMarkup:
        """Get keyboard for a specific page."""
        page = plugin_page or self.current_page
        page = max(1, min(page, self.total_pages))

        buttons = []
        page_items = self.get_page_items(page)

        # Item buttons
        for item in page_items:
            buttons.append([
                InlineKeyboardButton(
                    self.item_label(item),
                    callback_data=f"{self.page_callback_prefix}_{self.item_callback(item)}"
                )
            ])

        # Pagination controls
        if self.total_pages > 1:
            nav_buttons = []

            if self.config.show_first_last and page > 1:
                nav_buttons.append(InlineKeyboardButton("⏮️ First", callback_data=f"{self.page_callback_prefix}_page_1"))

            if page > 1:
                nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{self.page_callback_prefix}_page_{page - 1}"))

            if self.config.show_page_numbers:
                # Calculate visible page range
                half = self.config.max_visible_pages // 2
                start = max(1, page - half)
                end = min(self.total_pages, start + self.config.max_visible_pages - 1)
                start = max(1, end - self.config.max_visible_pages + 1)

                for p in range(start, end + 1):
                    if p == page:
                        nav_buttons.append(InlineKeyboardButton(f"[{p}]", callback_data="noop"))
                    else:
                        nav_buttons.append(InlineKeyboardButton(str(p), callback_data=f"{self.page_callback_prefix}_page_{p}"))

            if page < self.total_pages:
                nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"{self.page_callback_prefix}_page_{page + 1}"))

            if self.config.show_first_last and page < self.total_pages:
                nav_buttons.append(InlineKeyboardButton("Last ⏭️", callback_data=f"{self.page_callback_prefix}_page_{self.total_pages}"))

            if nav_buttons:
                buttons.append(nav_buttons)

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_main")])
        return InlineKeyboardMarkup(buttons)

    def set_page(self, page: int):
        """Set current page."""
        self.current_page = max(1, min(page, self.total_pages))


def create_simple_pagination(
    items: list[str],
    page: int = 1,
    per_page: int = 10,
    callback_prefix: str = "item",
) -> InlineKeyboardMarkup:
    """Simple pagination for string lists."""
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    buttons = []
    for item in page_items:
        buttons.append([InlineKeyboardButton(item, callback_data=f"{callback_prefix}_{item}")])

    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"{callback_prefix}_page_{page - 1}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"{callback_prefix}_page_{page + 1}"))
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)
