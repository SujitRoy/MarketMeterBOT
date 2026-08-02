"""
telegram/handlers/search — /search command handler and callback query handler.
"""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from marketmeter.core.logging import get_logger
from marketmeter.telegram.rich.send import _reply
from marketmeter.telegram.search.lookup import tv_symbol_lookup
from marketmeter.telegram.search.keyboards import (
    _build_candidate_keyboard, _chart_keyboard,
)
from marketmeter.telegram.search.detail import (
    fetch_live_for_symbol, format_live_detail, send_live_stock_detail,
)

logger = get_logger(__name__)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /search <symbol|company>

    TradingView is the SOLE source of truth. We never fuzzy-search our local
    DB - TV has the full NSE universe with company descriptions and is fast
    enough (~300ms per call) to be the only path.

    Flow:
      1. Query TV symbol-search.
      2. If a result matches the query exactly → show live detail directly.
      3. Else show the TV candidates as a picker (with company descriptions).
      4. If TV returns nothing → tell the user we couldn't find a match.
    """
    if not context.args:
        await _reply(update, (
            "🔍 **Search Usage**\n\n"
            "`/search RELIANCE` — exact symbol\n"
            "`/search piramal` — by company name\n"
            "`/search adani` — group of symbols\n"
            "`/search TATAMTR` — fuzzy / typo-tolerant\n\n"
            "Exact symbol → live detail instantly. Otherwise tap a candidate."
        ))
        return

    query = " ".join(context.args).strip()
    q = query.upper()

    loop = asyncio.get_running_loop()
    tv_hits = await loop.run_in_executor(None, tv_symbol_lookup, query)

    # No TV hits → nothing matches
    if not tv_hits:
        await _reply(update, f"🔍 No match for **'{query}'**. Try a different symbol or company name.")
        return

    # Single confident TV hit → skip the picker, show live detail directly
    if len(tv_hits) == 1:
        await send_live_stock_detail(update, tv_hits[0]["symbol"])
        return

    # Exact symbol match among multiple TV hits → direct detail
    exact = [h for h in tv_hits if h["symbol"] == q]
    if exact:
        await send_live_stock_detail(update, exact[0]["symbol"])
        return

    # Picker: TV candidates with descriptions
    candidates = tv_hits[:10]
    names = {h["symbol"]: h["description"] for h in candidates if h.get("description")}
    syms = [h["symbol"] for h in candidates]
    keyboard = _build_candidate_keyboard(syms, names)
    await _reply(update, (
        f"🔍 **'{query}'** — {len(candidates)} match(es). Tap to view live detail:"
    ), reply_markup=keyboard)


async def on_search_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback from search result button."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "search_cancel":
        await query.edit_message_text("🔍 Search cancelled.")
        return

    try:
        _, symbol = data.split("|", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid selection.")
        return

    # Show loading
    await query.edit_message_text(f"📡 Fetching live data for **{symbol}**...")

    # Fetch live data
    live_data = await fetch_live_for_symbol(symbol)

    if not live_data:
        await query.edit_message_text(f"❌ No live data for **{symbol}**.")
        return

    # Format and send rich message
    message = format_live_detail(symbol, live_data)
    await _reply(update, message, reply_markup=_chart_keyboard(symbol))

    # Delete the loading message
    try:
        await query.delete_message()
    except Exception:
        pass


# ─── Handler Export ─────────────────────────────────────────────────

search_handlers = [
    CommandHandler("search", cmd_search),
    CallbackQueryHandler(on_search_select, pattern=r"^search_(select|cancel)"),
]