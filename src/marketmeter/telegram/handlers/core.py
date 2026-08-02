"""
telegram/handlers/core — core command handlers (/start, /help, /status, /indicators, /subscribe, /unsubscribe).
"""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CommandHandler

from marketmeter.core.logging import get_logger
from marketmeter.reports import (
    generate_welcome_message,
    generate_help_message,
    generate_indicators_message,
    generate_status_message,
)
from marketmeter.db import (
    add_subscriber, remove_subscriber,
)
from marketmeter.telegram.rich.send import _reply

logger = get_logger(__name__)


async def cmd_start(update: Update, context):
    """Handle /start command."""
    user = update.effective_user
    first_name = user.first_name or "there"
    await _reply(update, generate_welcome_message(first_name))


async def cmd_help(update: Update, context):
    """Handle /help command."""
    await _reply(update, generate_help_message())


async def cmd_indicators(update: Update, context):
    """Handle /indicators command - indicator glossary and scoring rules."""
    await _reply(update, generate_indicators_message())


async def cmd_subscribe(update: Update, context):
    """Handle /subscribe command."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    is_new = add_subscriber(
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if is_new:
        msg = (
            "✅ **Subscribed successfully!**\n\n"
            "You'll receive daily morning reports at 8:30 AM IST.\n"
            "Use /unsubscribe to stop receiving reports."
        )
    else:
        msg = "ℹ️ You're already subscribed! Use /unsubscribe to stop."

    await _reply(update, msg)
    logger.info("Subscriber %s (%d) %s",
                user.username or user.first_name, chat_id,
                "added" if is_new else "already active")


async def cmd_unsubscribe(update: Update, context):
    """Handle /unsubscribe command."""
    chat_id = update.effective_chat.id
    removed = remove_subscriber(chat_id)

    if removed:
        msg = (
            "👋 **Unsubscribed.**\n\n"
            "You'll no longer receive daily reports.\n"
            "Use /subscribe to re-subscribe anytime."
        )
    else:
        msg = "ℹ️ You weren't subscribed. Use /subscribe to start receiving reports."

    await _reply(update, msg)


async def cmd_status(update: Update, context):
    """Handle /status command — show DB and sync status."""
    loop = asyncio.get_event_loop()
    msg = await loop.run_in_executor(None, generate_status_message)
    # The status message contains a recent-syncs table, which Markdown V1
    # renders as raw pipes.
    await _reply(update, msg)


# ─── Handler Export ─────────────────────────────────────────────────

core_handlers = [
    CommandHandler("start", cmd_start),
    CommandHandler("help", cmd_help),
    CommandHandler("indicators", cmd_indicators),
    CommandHandler("subscribe", cmd_subscribe),
    CommandHandler("unsubscribe", cmd_unsubscribe),
    CommandHandler("status", cmd_status),
]