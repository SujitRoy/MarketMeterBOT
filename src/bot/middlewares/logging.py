"""
Logging Middleware
Logs all updates and errors for debugging and monitoring.
"""
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from telegram import Update
from telegram.ext import Application, ContextTypes


class LoggingMiddleware:
    """Middleware for logging updates and responses."""

    def __init__(self):
        self.logger = logging.getLogger("middleware.logging")

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        next_handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
    ) -> Any:
        """Called for each update."""
        # Store start time
        context.bot_data['_update_start_time'] = time.time()

        # Log update
        user = update.effective_user
        chat = update.effective_chat

        if update.message:
            self.logger.info(
                "Update: user=%s(%s) chat=%s(%s) text=%s",
                user.id if user else None,
                user.username if user else None,
                chat.id if chat else None,
                chat.type if chat else None,
                update.message.text[:100] if update.message.text else None,
            )
        elif update.callback_query:
            self.logger.info(
                "Callback: user=%s(%s) chat=%s data=%s",
                user.id if user else None,
                user.username if user else None,
                chat.id if chat else None,
                update.callback_query.data[:100] if update.callback_query.data else None,
            )

        try:
            result = await next_handler(update, context)

            # Log elapsed time
            start_time = context.bot_data.pop('_update_start_time', None)
            if start_time:
                elapsed = (time.time() - start_time) * 1000
                self.logger.debug("Update processed in %.2f ms", elapsed)

            return result
        except Exception as e:
            self.logger.error(
                "Error processing update: user=%s chat=%s error=%s",
                user.id if user else None,
                chat.id if chat else None,
                e,
                exc_info=e,
            )
            raise


def setup_middlewares(app: Application) -> None:
    """Setup all middlewares."""
    app.add_handler(logging_middleware, group=-1)


# Global middleware instance
logging_middleware = LoggingMiddleware()
