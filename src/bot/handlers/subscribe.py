"""
Subscribe/Unsubscribe Handlers
"""
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler


class SubscribeHandler(BaseHandler):
    """Handle /subscribe command."""

    @property
    def command(self) -> str:
        return "subscribe"

    @property
    def description(self) -> str:
        return "Subscribe to daily reports"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.require_private_chat(update, context):
            return

        newly_added = self.subscribe_user(update)

        if newly_added:
            msg = (
                "✅ **Subscribed!**\n\n"
                "You'll receive the daily morning report at 08:30 AM IST.\n"
                "Reports include:\n"
                "• Top 3 detailed picks with full indicator breakdown\n"
                "• Top 25 scan table with key metrics\n"
                "• Market outlook & category tally\n\n"
                "Use `/unsubscribe` to stop receiving reports."
            )
        else:
            msg = (
                "ℹ️ **Already subscribed**\n\n"
                "You're already receiving daily reports at 08:30 AM IST.\n"
                "Use `/unsubscribe` to stop."
            )

        await self.send_message(update, msg)


class UnsubscribeHandler(BaseHandler):
    """Handle /unsubscribe command."""

    @property
    def command(self) -> str:
        return "unsubscribe"

    @property
    def description(self) -> str:
        return "Unsubscribe from reports"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.require_private_chat(update, context):
            return

        removed = self.unsubscribe_user(update)

        if removed:
            msg = (
                "✅ **Unsubscribed**\n\n"
                "You'll no longer receive daily morning reports.\n"
                "Use `/subscribe` anytime to start receiving them again."
            )
        else:
            msg = (
                "ℹ️ **Not subscribed**\n\n"
                "You weren't receiving reports.\n"
                "Use `/subscribe` to start receiving daily reports."
            )

        await self.send_message(update, msg)
