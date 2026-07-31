"""
Base Handler Class
Common functionality for all command handlers.
"""
import logging
from abc import ABC, abstractmethod

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.core.exceptions import BotError
from src.database.repositories import SubscriberRepository


class BaseHandler(ABC):
    """Abstract base class for command handlers."""

    def __init__(self):
        self.logger = logging.getLogger(f"handler.{self.__class__.__name__}")
        self.subscriber_repo = SubscriberRepository()

    @property
    @abstractmethod
    def command(self) -> str:
        """Command name (without /)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Command description for help."""
        pass

    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the command. Must be implemented by subclasses."""
        pass

    def get_handler(self) -> CommandHandler:
        """Get the CommandHandler for this command."""
        return CommandHandler(self.command, self.handle)

    async def send_message(
        self,
        update: Update,
        text: str,
        parse_mode: str = "Markdown",
        **kwargs
    ) -> None:
        """Send a message with error handling."""
        try:
            await update.message.reply_text(text, parse_mode=parse_mode, **kwargs)
        except Exception as e:
            self.logger.error("Failed to send message: %s", e)
            raise BotError(f"Failed to send message: {e}") from e

    def is_owner(self, update: Update) -> bool:
        """Check if user is the bot owner."""
        from src.core.config import OWNER_CHAT_ID
        return update.effective_chat.id == OWNER_CHAT_ID

    def is_private_chat(self, update: Update) -> bool:
        """Check if message is in private chat."""
        return update.effective_chat.type == "private"

    async def require_private_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Require private chat, send error if not."""
        if not self.is_private_chat(update):
            await self.send_message(update, "❌ This command only works in private chat.")
            return False
        return True

    async def require_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Require owner access, send error if not."""
        if not self.is_owner(update):
            await self.send_message(update, "❌ Owner only command.")
            return False
        return True

    def subscribe_user(self, update: Update) -> bool:
        """Subscribe the user. Returns True if newly subscribed."""
        chat = update.effective_chat
        return self.subscriber_repo.add_subscriber(
            chat_id=chat.id,
            username=chat.username,
            first_name=chat.first_name,
            last_name=chat.last_name,
        )

    def unsubscribe_user(self, update: Update) -> bool:
        """Unsubscribe the user. Returns True if was subscribed."""
        chat = update.effective_chat
        return self.subscriber_repo.remove_subscriber(chat.id)
