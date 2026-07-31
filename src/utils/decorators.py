"""
Decorators
Utility decorators for the bot.
"""
import functools
import logging
import time
from collections.abc import Callable


def log_calls(logger: logging.Logger = None, level: int = logging.DEBUG):
    """Decorator to log function calls."""
    def decorator(func: Callable) -> Callable:
        _logger = logger or logging.getLogger(func.__module__)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _logger.log(level, "Calling %s with args=%s kwargs=%s",
                       func.__name__, args[:2], list(kwargs.keys())[:5])
            try:
                result = func(*args, **kwargs)
                _logger.log(level, "%s returned %s", func.__name__, type(result).__name__)
                return result
            except Exception as e:
                _logger.exception("%s raised %s: %s", func.__name__, type(e).__name__, e)
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            _logger.log(level, "Calling %s with args=%s kwargs=%s",
                       func.__name__, args[:2], list(kwargs.keys())[:5])
            try:
                result = await func(*args, **kwargs)
                _logger.log(level, "%s returned %s", func.__name__, type(result).__name__)
                return result
            except Exception as e:
                _logger.exception("%s raised %s: %s", func.__name__, type(e).__name__, e)
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def timing(logger: logging.Logger = None, threshold_ms: float = 100):
    """Decorator to log execution time."""
    def decorator(func: Callable) -> Callable:
        _logger = logger or logging.getLogger(func.__module__)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                if elapsed > threshold_ms:
                    _logger.warning("%s took %.2f ms", func.__name__, elapsed)
                else:
                    _logger.debug("%s took %.2f ms", func.__name__, elapsed)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                if elapsed > threshold_ms:
                    _logger.warning("%s took %.2f ms", func.__name__, elapsed)
                else:
                    _logger.debug("%s took %.2f ms", func.__name__, elapsed)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple = (Exception,), logger: logging.Logger = None):
    """Decorator to retry function on failure."""
    def decorator(func: Callable) -> Callable:
        _logger = logger or logging.getLogger(func.__module__)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        _logger.warning(
                            "%s attempt %d/%d failed: %s. Retrying in %.1fs",
                            func.__name__, attempt + 1, max_attempts, e, current_delay
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        _logger.error(
                            "%s all %d attempts failed: %s",
                            func.__name__, max_attempts, e
                        )

            raise last_exception

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        _logger.warning(
                            "%s attempt %d/%d failed: %s. Retrying in %.1fs",
                            func.__name__, attempt + 1, max_attempts, e, current_delay
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        _logger.error(
                            "%s all %d attempts failed: %s",
                            func.__name__, max_attempts, e
                        )

            raise last_exception

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def singleton(cls: type) -> type:
    """Decorator to make a class a singleton."""
    instances = {}

    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance


def cached(ttl: int = 300, key_func: Callable = None):
    """Simple caching decorator with TTL."""
    cache = {}
    timestamps = {}

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{args}:{frozenset(kwargs.items())}"

            now = time.time()

            # Check cache
            if key in cache and now - timestamps.get(key, 0) < ttl:
                return cache[key]

            # Execute and cache
            result = func(*args, **kwargs)
            cache[key] = result
            timestamps[key] = now
            return result

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{args}:{frozenset(kwargs.items())}"

            now = time.time()

            if key in cache and now - timestamps.get(key, 0) < ttl:
                return cache[key]

            result = await func(*args, **kwargs)
            cache[key] = result
            timestamps[key] = now
            return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def require_owner(func: Callable) -> Callable:
    """Decorator to require owner access for bot handlers."""
    @functools.wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        from src.core.config import OWNER_CHAT_ID

        if update.effective_chat.id != OWNER_CHAT_ID:
            await update.message.reply_text("❌ Owner only command.")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def require_private_chat(func: Callable) -> Callable:
    """Decorator to require private chat for bot handlers."""
    @functools.wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if update.effective_chat.type != "private":
            await update.message.reply_text("❌ This command only works in private chat.")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def rate_limit(max_calls: int = 30, window: int = 60):
    """Decorator for rate limiting function calls."""
    calls = {}

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Try to extract chat_id from args
            chat_id = None
            for arg in args:
                if hasattr(arg, 'effective_chat') and arg.effective_chat:
                    chat_id = arg.effective_chat.id
                    break

            if chat_id is None:
                return func(*args, **kwargs)

            now = time.time()

            # Clean old entries
            if chat_id in calls:
                calls[chat_id] = [t for t in calls[chat_id] if now - t < window]
            else:
                calls[chat_id] = []

            # Check limit
            if len(calls[chat_id]) >= max_calls:
                raise Exception(f"Rate limit exceeded: {max_calls} calls per {window}s")

            calls[chat_id].append(now)
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            chat_id = None
            for arg in args:
                if hasattr(arg, 'effective_chat') and arg.effective_chat:
                    chat_id = arg.effective_chat.id
                    break

            if chat_id is None:
                return await func(*args, **kwargs)

            now = time.time()

            if chat_id in calls:
                calls[chat_id] = [t for t in calls[chat_id] if now - t < window]
            else:
                calls[chat_id] = []

            if len(calls[chat_id]) >= max_calls:
                raise Exception(f"Rate limit exceeded: {max_calls} calls per {window}s")

            calls[chat_id].append(now)
            return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
