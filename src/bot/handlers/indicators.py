"""
Indicators Handler
Handles /indicators command for technical indicator explanations.
"""
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler


class IndicatorsHandler(BaseHandler):
    """Handle /indicators command."""

    @property
    def command(self) -> str:
        return "indicators"

    @property
    def description(self) -> str:
        return "Technical indicators explained"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from src.reports import generate_indicators_message

        indicators_msg = generate_indicators_message()
        await self.send_message(update, indicators_msg)
