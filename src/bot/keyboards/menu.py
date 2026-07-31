"""
Inline Keyboards
Reusable keyboard components for the bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    buttons = [
        [InlineKeyboardButton("📊 Get Report", callback_data="menu_report")],
        [InlineKeyboardButton("📈 Search Stock", callback_data="menu_search")],
        [InlineKeyboardButton("📌 Status", callback_data="menu_status")],
        [InlineKeyboardButton("📚 Indicators", callback_data="menu_indicators")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_settings_keyboard(subscribed: bool = True) -> InlineKeyboardMarkup:
    """Settings keyboard."""
    sub_text = "🔔 Unsubscribe" if subscribed else "🔔 Subscribe"
    sub_data = "settings_unsubscribe" if subscribed else "settings_subscribe"

    buttons = [
        [InlineKeyboardButton(sub_text, callback_data=sub_data)],
        [InlineKeyboardButton("🕐 Timezone", callback_data="settings_timezone")],
        [InlineKeyboardButton("📱 Notifications", callback_data="settings_notifications")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_confirmation_keyboard(
    confirm_data: str,
    cancel_data: str = "menu_main",
    confirm_text: str = "✅ Confirm",
    cancel_text: str = "❌ Cancel"
) -> InlineKeyboardMarkup:
    """Confirmation dialog keyboard."""
    buttons = [
        [
            InlineKeyboardButton(confirm_text, callback_data=confirm_data),
            InlineKeyboardButton(cancel_text, callback_data=cancel_data),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def build_pagination_keyboard(
    current_page: int,
    total_pages: int,
    base_callback: str,
    extra_data: str = ""
) -> InlineKeyboardMarkup:
    """Pagination keyboard for lists."""
    buttons = []

    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{base_callback}_page_{current_page - 1}{extra_data}"))
    nav_row.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{base_callback}_page_{current_page + 1}{extra_data}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_main")])

    return InlineKeyboardMarkup(buttons)


def build_symbol_keyboard(symbols: list[str], callback_prefix: str = "symbol") -> InlineKeyboardMarkup:
    """Keyboard with symbol buttons (5 per row)."""
    buttons = []
    row = []

    for i, symbol in enumerate(symbols):
        row.append(InlineKeyboardButton(symbol, callback_data=f"{callback_prefix}_{symbol}"))
        if len(row) == 5 or i == len(symbols) - 1:
            buttons.append(row)
            row = []

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def build_report_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting report type."""
    buttons = [
        [InlineKeyboardButton("📊 Morning Report", callback_data="report_morning")],
        [InlineKeyboardButton("🌅 Pre-Market (09:00)", callback_data="report_premarket")],
        [InlineKeyboardButton("🧭 Open Cross-Check (09:15)", callback_data="report_crosscheck")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(buttons)
