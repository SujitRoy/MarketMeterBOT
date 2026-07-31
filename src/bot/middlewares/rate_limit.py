"""
Rate Limit Middleware
Prevents abuse by limiting requests per user/chat.
"""
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from src.core.exceptions import RateLimitError


class RateLimitMiddleware:
    """Rate limiting middleware using sliding window."""

    def __init__(
        self,
        max_requests: int = 30,
        window_seconds: int = 60,
        burst_max: int = 5,
        burst_window: int = 10,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.burst_max = burst_max
        self.burst_window = burst_window

        # Storage: chat_id -> list of timestamps
        self._requests: defaultdict[int, list[float]] = defaultdict(list)
        self._burst_requests: defaultdict[int, list[float]] = defaultdict(list)

        self.logger = logging.getLogger("middleware.ratelimit")

    def _clean_old(self, requests: list[float], window: int) -> list[float]:
        """Remove timestamps older than window."""
        now = time.time()
        return [ts for ts in requests if now - ts < window]

    def _is_rate_limited(self, chat_id: int) -> tuple[bool, str]:
        """Check if chat is rate limited."""
        now = time.time()

        # Check burst limit
        burst = self._clean_old(self._burst_requests[chat_id], self.burst_window)
        if len(burst) >= self.burst_max:
            return True, f"Too many requests. Please wait {self.burst_window}s."

        # Check sustained limit
        sustained = self._clean_old(self._requests[chat_id], self.window_seconds)
        if len(sustained) >= self.max_requests:
            return True, f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s."

        # Record request
        self._burst_requests[chat_id] = burst + [now]
        self._requests[chat_id] = sustained + [now]

        return False, ""

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        next_handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
    ) -> Any:
        """Check rate limit before processing."""
        chat = update.effective_chat
        if not chat:
            return await next_handler(update, context)

        # Skip rate limiting for owner
        from src.core.config import OWNER_CHAT_ID
        if chat.id == OWNER_CHAT_ID:
            return await next_handler(update, context)

        limited, message = self._is_rate_limited(chat.id)
        if limited:
            self.logger.warning("Rate limited chat=%s", chat.id)
            raise RateLimitError(message)

        return await next_handler(update, context)


# Global middleware instance
rate_limit_middleware = RateLimitMiddleware()


def setup_middlewares(app) -> None:
    """Setup all middlewares."""
    from src.bot.middlewares.logging import logging_middleware

    # Add in order: rate limit first, then logging
    app.add_handler(rate_limit_middleware, group=-2)
    app.add_handler(logging_middleware, group=-1)
