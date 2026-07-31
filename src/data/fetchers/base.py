"""
Base Fetcher Abstract Class
Common interface for all data fetchers.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a fetch operation."""
    success: bool
    data: list[dict[str, Any]] | None = None
    error: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseFetcher(ABC):
    """Abstract base class for all data fetchers."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"fetcher.{name}")

    @abstractmethod
    def fetch(self, *args, **kwargs) -> FetchResult:
        """Fetch data. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def validate_response(self, response: Any) -> bool:
        """Validate that response contains expected data."""
        pass

    def handle_error(self, error: Exception, context: str = "") -> FetchResult:
        """Standard error handling."""
        msg = f"{self.name} fetch failed{f' ({context})' if context else ''}: {error}"
        self.logger.error(msg, exc_info=True)
        return FetchResult(success=False, error=msg)

    def log_fetch(self, count: int, context: str = "") -> None:
        """Log successful fetch."""
        self.logger.info("%s fetched %d records %s", self.name, count, context)


class RateLimitedFetcher(BaseFetcher):
    """Base fetcher with built-in rate limiting."""

    def __init__(self, name: str, delay: float = 0.15, max_retries: int = 3):
        super().__init__(name)
        self.delay = delay
        self.max_retries = max_retries

    def _sleep(self) -> None:
        """Sleep for rate limiting."""
        import time
        time.sleep(self.delay)

    def _retry(self, func, *args, **kwargs) -> FetchResult:
        """Execute with retry logic."""
        import time
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    backoff = 2 ** attempt
                    self.logger.warning(
                        "%s attempt %d/%d failed: %s. Retrying in %ds",
                        self.name, attempt + 1, self.max_retries, e, backoff
                    )
                    time.sleep(backoff)
                else:
                    self.logger.error(
                        "%s all %d attempts failed: %s",
                        self.name, self.max_retries, e
                    )

        return self.handle_error(last_error, f"after {self.max_retries} retries")
