"""
Start Command Handler
"""
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler


class StartHandler(BaseHandler):
    """Handle /start command."""

    @property
    def command(self) -> str:
        return "start"

    @property
    def description(self) -> str:
        return "Welcome message"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from src.reports import generate_welcome_message

        first_name = update.effective_user.first_name or "there"
        welcome_msg = generate_welcome_message(first_name)

        await self.send_message(update, welcome_msg)


class HelpHandler(BaseHandler):
    """Handle /help command."""

    @property
    def command(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Show all commands"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from src.reports import generate_help_message

        help_msg = generate_help_message()
        await self.send_message(update, help_msg)
