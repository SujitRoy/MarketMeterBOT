"""
core/retry — generic async retry with exponential backoff.

Phase 1 introduces the decorator only. Existing callers (data_fetcher,
intraday_fetcher) keep their hand-rolled retry loops until Phase 3 retires
them in favour of this primitive.

Why a decorator and not a hand-rolled while-loop:
- Backoff math is in exactly one place.
- Caller code reads as the success path.
- Test surface is one function, not N call sites.
"""
from __future__ import annotations

import asyncio
import functools
import random
from typing import Awaitable, Callable, Iterable, Optional, Type, TypeVar

from .logging import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


def async_retry(
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 30.0,
    jitter: float = 0.1,
    retry_on: Iterable[Type[BaseException]] = (Exception,),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator: retry an async callable on failure with exponential backoff.

    Args:
        max_attempts: total attempts (including the first). Must be >= 1.
        base_delay: initial wait after the first failure, in seconds.
        backoff: multiplier applied to the delay after each failure.
        max_delay: hard cap on the per-attempt wait.
        jitter: fraction of the delay added as +/- random jitter (0.1 = ±10%).
        retry_on: tuple of exception types that should trigger a retry.
        on_retry: optional callback(attempt_number, exception, next_delay) for
            custom logging/side-effects.

    The wrapped function is called up to max_attempts times. The last failure
    is re-raised; not swallowed.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    retry_types = tuple(retry_on)

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except retry_types as e:
                    last_exc = e
                    if attempt >= max_attempts:
                        logger.error(
                            "retry exhausted: %s failed after %d attempts: %s",
                            getattr(fn, "__qualname__", fn), attempt, e,
                        )
                        raise
                    # Add jitter ± fraction of delay.
                    actual_delay = delay * (1.0 + random.uniform(-jitter, jitter))
                    actual_delay = min(actual_delay, max_delay)
                    if on_retry is not None:
                        try:
                            on_retry(attempt, e, actual_delay)
                        except Exception:  # pragma: no cover
                            logger.exception("on_retry callback raised")
                    else:
                        logger.warning(
                            "retry %d/%d for %s: %s — sleeping %.2fs",
                            attempt, max_attempts,
                            getattr(fn, "__qualname__", fn), e, actual_delay,
                        )
                    await asyncio.sleep(actual_delay)
                    delay = min(delay * backoff, max_delay)
            # Unreachable: the loop either returns or raises. Defensive only.
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


__all__ = ["async_retry"]
