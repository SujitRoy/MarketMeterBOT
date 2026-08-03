"""
telegram/search/keyboards — inline keyboard builders for search results.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_search_keyboard(
    matches: list[tuple[str, int]], query: str
) -> InlineKeyboardMarkup:
    """Build inline keyboard with search results."""
    buttons = []
    for symbol, score in matches:
        label = f"{symbol} ({int(round(score))}%)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"search_select|{symbol}")])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="search_cancel")])
    return InlineKeyboardMarkup(buttons)


def _build_candidate_keyboard(
    candidates: list[str], names: dict[str, str]
) -> InlineKeyboardMarkup:
    """Inline keyboard: symbol + company description if available."""
    buttons = []
    for sym in candidates:
        label = f"{sym}"
        if names.get(sym):
            label += f" · {names[sym]}"
        buttons.append([InlineKeyboardButton(label[:64], callback_data=f"search_select|{sym}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="search_cancel")])
    return InlineKeyboardMarkup(buttons)


def _chart_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """
    Public TradingView symbol page. This URL works without our sessionid
    cookie (the personal /chart/<id>/?symbol=... URL does NOT — see audit).
    """
    url = f"https://in.tradingview.com/symbols/NSE-{symbol}/"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Open Chart", url=url)],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"search_select|{symbol}")],
    ])


__all__ = [
    "build_search_keyboard",
    "_build_candidate_keyboard",
    "_chart_keyboard",
]