"""
Status Handler
Handles /status command for bot and database status.
"""
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler


class StatusHandler(BaseHandler):
    """Handle /status command."""

    @property
    def command(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return "Check bot & database status"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from src.reports import generate_status_message

        status_msg = generate_status_message()
        await self.send_message(update, status_msg)
