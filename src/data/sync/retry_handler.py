"""
Retry Handler
Manages retry logic for failed sync operations.
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from src.core.config import MAX_RETRY_DATES, SYNC_RETRY_INTERVAL_MINUTES, SYNC_RETRY_UNTIL_HOUR
from src.database.repositories import SyncRepository

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_dates: int = MAX_RETRY_DATES
    interval_minutes: int = SYNC_RETRY_INTERVAL_MINUTES
    until_hour: int = SYNC_RETRY_UNTIL_HOUR


class RetryHandler:
    """Handles retry logic for failed sync operations."""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self.sync_repo = SyncRepository()

    def get_retry_candidates(self) -> list[dict[str, Any]]:
        """Get dates that need retry (failed or not_available)."""
        failed = self.sync_repo.get_failed_syncs()
        return failed[-self.config.max_dates:]

    def should_retry_now(self) -> bool:
        """Check if current time is within retry window."""
        now = datetime.now()
        return now.hour < self.config.until_hour

    def get_next_retry_time(self) -> datetime:
        """Get the next scheduled retry time."""
        now = datetime.now()
        if now.minute < 30:
            next_retry = now.replace(minute=30, second=0, microsecond=0)
        else:
            next_retry = now.replace(hour=now.hour+1, minute=0, second=0, microsecond=0)

        # Don't schedule past until_hour
        if next_retry.hour >= self.config.until_hour:
            next_retry = next_retry.replace(hour=self.config.until_hour - 1, minute=0)

        return next_retry

    def run_retry_cycle(
        self,
        sync_func: Callable[[date], dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Run a single retry cycle.
        
        Args:
            sync_func: Function to call for each date. Should return dict with 'status' key.
            
        Returns:
            Summary of retry cycle
        """
        candidates = self.get_retry_candidates()

        if not candidates:
            return {
                'status': 'no_candidates',
                'message': 'No dates to retry',
                'retried': 0,
                'succeeded': 0,
                'still_pending': 0,
            }

        logger.info("Starting retry cycle for %d dates", len(candidates))

        retried = 0
        succeeded = 0
        still_pending = 0

        for candidate in candidates:
            trade_date = date.fromisoformat(candidate['trade_date'])

            # Check if we should still retry
            if not self.should_retry_now():
                logger.info("Retry window closed (past %d:00)", self.config.until_hour)
                break

            logger.info("Retrying %s...", trade_date)
            result = sync_func(trade_date)

            retried += 1

            if result.get('status') == 'success':
                succeeded += 1
                logger.info("Retry succeeded for %s: %d records", trade_date, result.get('records', 0))
            elif result.get('status') == 'not_available':
                still_pending += 1
                logger.info("Still not available: %s", trade_date)
            elif result.get('status') == 'holiday':
                logger.info("Marked as holiday: %s", trade_date)
            else:
                logger.warning("Retry failed for %s: %s", trade_date, result.get('message'))

            # Small delay between retries
            time.sleep(1)

        return {
            'status': 'completed',
            'retried': retried,
            'succeeded': succeeded,
            'still_pending': still_pending,
            'message': f"Retried {retried}, succeeded {succeeded}, pending {still_pending}",
        }

    def schedule_retry_jobs(self, job_queue) -> None:
        """
        Schedule periodic retry jobs using APScheduler.
        
        Args:
            job_queue: APScheduler job queue
        """
        from datetime import time

        # Run at :30 past each hour during retry window
        for hour in range(16, self.config.until_hour):
            job_queue.run_daily(
                self._retry_job_wrapper,
                time=time(hour, 30),
                days=(0, 1, 2, 3, 4),  # Mon-Fri
                name=f"sync_retry_{hour:02d}30",
            )

        logger.info("Scheduled retry jobs for %d:%02d to %d:%02d",
                    16, 30, self.config.until_hour - 1, 30)

    def _retry_job_wrapper(self, context) -> None:
        """Wrapper for APScheduler job."""
        # This would be called with the sync function bound
        # Implementation depends on how sync_engine is wired
        pass


def exponential_backoff(attempt: int, base: float = 2.0, max_delay: float = 300.0) -> float:
    """Calculate exponential backoff delay."""
    delay = base ** attempt
    return min(delay, max_delay)


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable."""
    retryable_types = (
        ConnectionError,
        TimeoutError,
        IOError,
    )
    return isinstance(error, retryable_types)
