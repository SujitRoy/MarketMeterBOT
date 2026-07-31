"""
Backfill Engine
Handles full historical backfill from NSE archives.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.core.config import HISTORICAL_START_DATE
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
class BackfillResult:
    """Result of a backfill operation."""
    status: str  # completed, partial, failed
    dates_processed: int = 0
    success: int = 0
    failed: int = 0
    holidays: int = 0
    total_records: int = 0
    details: list = field(default_factory=list)
    message: str = ""


class BackfillEngine:
    """Handles full historical backfill from NSE BhavCopy archives."""

    def __init__(self):
        self.fetcher = NSEBhavCopyFetcher()
        self.bhavcopy_repo = BhavCopyRepository()
        self.sync_repo = SyncRepository()
        self.stats_repo = StatsRepository()

    def run_backfill(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        batch_size: int = 100
    ) -> BackfillResult:
        """
        Run full historical backfill.
        
        Args:
            start_date: Start date (default: HISTORICAL_START_DATE)
            end_date: End date (default: today)
            batch_size: Commit batch size for progress logging
        """
        if start_date is None:
            start_date = date.fromisoformat(HISTORICAL_START_DATE)
        if end_date is None:
            end_date = date.today()

        trading_days = get_trading_days(start_date, end_date)
        logger.info("Backfilling %d trading days from %s to %s",
                    len(trading_days), start_date, end_date)

        result = BackfillResult()

        try:
            for i, trade_date in enumerate(trading_days, 1):
                if i % batch_size == 0:
                    logger.info("Backfill progress: %d/%d days, %d records so far",
                                i, len(trading_days), result.total_records)

                date_result = self._backfill_single_date(trade_date)
                result.details.append(date_result)

                result.dates_processed += 1
                if date_result['status'] == 'success':
                    result.success += 1
                    result.total_records += date_result['records']
                elif date_result['status'] == 'holiday':
                    result.holidays += 1
                else:
                    result.failed += 1

                # Rate limiting
                if i < len(trading_days):
                    time.sleep(self.fetcher.delay)

            result.message = (
                f"Backfill complete: {result.success} success, "
                f"{result.failed} failed, {result.holidays} holidays, "
                f"{result.total_records} total records"
            )
            result.status = 'completed' if result.failed == 0 else 'partial'
            logger.info(result.message)

            return result

        finally:
            self.fetcher.close()

    def _backfill_single_date(self, trade_date: date) -> dict[str, Any]:
        """Backfill a single date."""
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

        logger.info("Backfilled %s: %d records", trade_date, inserted)

        return {
            'date': trade_date,
            'status': 'success',
            'records': inserted,
            'message': f"Downloaded {len(fetch_result.data)} records",
        }

    def run_resume_backfill(self, start_date: date | None = None) -> BackfillResult:
        """
        Resume backfill from last successful date in database.
        """
        latest_in_db = self.bhavcopy_repo.get_latest_trade_date()

        if latest_in_db is None:
            return self.run_backfill(start_date=start_date)

        # Resume from day after latest
        resume_start = date.fromisoformat(latest_in_db) + datetime.timedelta(days=1)
        logger.info("Resuming backfill from %s", resume_start)

        return self.run_backfill(start_date=resume_start)


import datetime  # For timedelta in run_resume_backfill
