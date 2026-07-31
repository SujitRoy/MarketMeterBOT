"""
Sync Engine
Orchestrates incremental daily sync with retry logic.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.core.config import (
    HISTORICAL_START_DATE,
    MARKET_CLOSE_HOUR,
    MAX_RETRY_DATES,
    SYNC_RETRY_UNTIL_HOUR,
)
from src.data.fetchers.nse_bhavcopy import (
    NSEBhavCopyFetcher,
    classify_sync_status,
    get_trading_days,
)
from src.database.repositories import (
    BhavCopyRepository,
    StatsRepository,
    SyncRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    status: str  # completed, up_to_date, partial
    dates_processed: int = 0
    success: int = 0
    failed: int = 0
    holidays: int = 0
    not_available: list[str] = field(default_factory=list)
    synced_dates: list[str] = field(default_factory=list)
    per_date_records: dict[str, int] = field(default_factory=dict)
    total_records: int = 0
    message: str = ""


class SyncEngine:
    """Orchestrates incremental daily sync from NSE BhavCopy."""

    def __init__(self):
        self.fetcher = NSEBhavCopyFetcher()
        self.bhavcopy_repo = BhavCopyRepository()
        self.sync_repo = SyncRepository()
        self.stats_repo = StatsRepository()

    def run_incremental_sync(self) -> SyncResult:
        """
        Sync missing trading days from last synced date to today.
        Also retries previously failed dates.
        """
        today = date.today()
        last_synced = self.sync_repo.get_last_synced_date()

        # Determine start date for sync
        if last_synced is None:
            latest_in_db = self.bhavcopy_repo.get_latest_trade_date()
            if latest_in_db is None:
                start = date.fromisoformat(HISTORICAL_START_DATE)
                logger.info("No data found. Starting backfill from %s", start)
            else:
                start = latest_in_db + dt.timedelta(days=1)
                logger.info("Resuming from last DB date: %s", start)
        else:
            start = last_synced + dt.timedelta(days=1)
            logger.info("Last synced: %s. Starting from: %s", last_synced, start)

        # Get failed dates to retry (only last N)
        failed_syncs = self.sync_repo.get_failed_syncs()
        retry_dates = [
            date.fromisoformat(f['trade_date'])
            for f in failed_syncs[-MAX_RETRY_DATES:]
        ]

        # Get trading days to sync
        if start <= today:
            new_dates = get_trading_days(start, today)
        else:
            new_dates = []

        # Skip today if before market close
        if new_dates and new_dates[-1] == today and datetime.now().hour < MARKET_CLOSE_HOUR:
            new_dates = new_dates[:-1]
            logger.info(
                "Skipping %s: before %02d:00 IST, NSE has not published yet",
                today, MARKET_CLOSE_HOUR,
            )

        # Combine: retry failed first, then new dates
        all_dates = sorted(set(retry_dates + new_dates))

        if not all_dates:
            logger.info("No new dates to sync. Everything up to date.")
            return SyncResult(
                status='up_to_date',
                message='Already up to date',
            )

        logger.info("Syncing %d dates (%d retries, %d new)",
                    len(all_dates), len(retry_dates), len(new_dates))

        result = SyncResult()

        try:
            for i, trade_date in enumerate(all_dates, 1):
                logger.info("[%d/%d] Processing %s...", i, len(all_dates), trade_date)
                date_result = self._sync_single_date(trade_date)

                result.dates_processed += 1

                if date_result['status'] == 'success':
                    result.success += 1
                    result.total_records += date_result['records']
                    if date_result['records'] > 0:
                        result.synced_dates.append(trade_date.isoformat())
                        result.per_date_records[trade_date.isoformat()] = date_result['records']
                elif date_result['status'] == 'holiday':
                    result.holidays += 1
                elif date_result['status'] == 'not_available':
                    result.not_available.append(trade_date.isoformat())
                else:
                    result.failed += 1

                # Rate limiting
                if i < len(all_dates):
                    time.sleep(self.fetcher.delay)

            # Build summary
            parts = [f"Sync complete: {result.success} success"]
            if result.failed:
                parts.append(f"{result.failed} failed")
            if result.holidays:
                parts.append(f"{result.holidays} holidays")
            if result.not_available:
                parts.append(f"{len(result.not_available)} pending (NSE not ready)")
            parts.append(f"{result.total_records} records inserted")

            result.message = ", ".join(parts)
            result.status = 'completed' if result.success > 0 else 'partial'
            logger.info(result.message)

            return result

        finally:
            self.fetcher.close()

    def _sync_single_date(self, trade_date: date) -> dict[str, Any]:
        """Sync a single date."""
        fetch_result = self.fetcher.fetch(trade_date)

        if not fetch_result.success:
            status = classify_sync_status(trade_date, fetch_result.error or "Unknown error")
            self.sync_repo.log_sync(trade_date, status, 0, fetch_result.error)
            return {
                'date': trade_date,
                'status': status,
                'records': 0,
                'message': fetch_result.error,
            }

        # Insert into database
        inserted = self.bhavcopy_repo.insert_batch([
            # Convert dict to BhavCopyRow
            type('BhavCopyRow', (), {'to_db_tuple': lambda self: (
                r['symbol'], r.get('series', 'EQ'), r.get('open'), r.get('high'),
                r.get('low'), r.get('close'), r.get('last'), r.get('prevclose'),
                r.get('volume'), r.get('value_lakh'), r.get('del_pct'),
                r['trade_date'], r.get('avg_price')
            )})()
            for r in fetch_result.data
        ])

        # Log success
        self.sync_repo.log_sync(trade_date, 'success', inserted)

        # Update stats cache
        if inserted > 0:
            self.stats_repo.update_total_records(inserted)
            self.stats_repo.update_date_range(
                trade_date.isoformat(), trade_date.isoformat()
            )
            self.stats_repo.mark_symbols_dirty()

        logger.info("Reconciled %s: %d net-new rows", trade_date, inserted)

        return {
            'date': trade_date,
            'status': 'success',
            'records': inserted,
            'net_new': inserted > 0,
            'message': f"Downloaded {len(fetch_result.data)} records",
        }

    def run_retry_sync(self) -> SyncResult:
        """Run retry sync for failed dates only."""
        failed_syncs = self.sync_repo.get_failed_syncs()
        retry_dates = [
            date.fromisoformat(f['trade_date'])
            for f in failed_syncs[-MAX_RETRY_DATES:]
        ]

        if not retry_dates:
            return SyncResult(
                status='up_to_date',
                message='No failed dates to retry',
            )

        logger.info("Retrying %d failed dates", len(retry_dates))

        result = SyncResult()

        try:
            for i, trade_date in enumerate(retry_dates, 1):
                logger.info("[%d/%d] Retrying %s...", i, len(retry_dates), trade_date)
                date_result = self._sync_single_date(trade_date)

                result.dates_processed += 1

                if date_result['status'] == 'success':
                    result.success += 1
                    result.total_records += date_result['records']
                    if date_result['records'] > 0:
                        result.synced_dates.append(trade_date.isoformat())
                        result.per_date_records[trade_date.isoformat()] = date_result['records']
                elif date_result['status'] == 'holiday':
                    result.holidays += 1
                elif date_result['status'] == 'not_available':
                    result.not_available.append(trade_date.isoformat())
                else:
                    result.failed += 1

                if i < len(retry_dates):
                    time.sleep(self.fetcher.delay)

            # Build summary
            parts = [f"Retry sync: {result.success} success"]
            if result.failed:
                parts.append(f"{result.failed} failed")
            if result.holidays:
                parts.append(f"{result.holidays} holidays")
            if result.not_available:
                parts.append(f"{len(result.not_available)} still pending")
            parts.append(f"{result.total_records} records inserted")

            result.message = ", ".join(parts)
            result.status = 'completed' if result.success > 0 else 'partial'
            logger.info(result.message)

            return result

        finally:
            self.fetcher.close()


def should_retry_now() -> bool:
    """Check if we should run retry sync based on current time."""
    now = datetime.now()
    return now.hour < SYNC_RETRY_UNTIL_HOUR
