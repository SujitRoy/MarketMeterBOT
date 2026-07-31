"""
NSE BhavCopy Fetcher
Fetches EOD data directly from NSE archives.
"""
import datetime as dt
import logging
import time
from datetime import date
from io import StringIO

import pandas as pd
import requests

from src.core.config import (
    MAX_RETRIES,
    NSE_BHAVCOPY_URL,
    NSE_HTTP_TIMEOUT,
    NSE_REQUEST_HEADERS,
    REQUEST_DELAY,
)
from src.core.exceptions import DataParseError
from src.data.fetchers.base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


# ── NSE Trading Holidays ───────────────────────────────────────────

# NSE trading holidays (CM segment) - kept as iso-strings
NSE_HOLIDAYS = {
    # 2024
    "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29", "2024-04-11",
    "2024-04-17", "2024-04-21", "2024-05-23", "2024-06-17", "2024-07-17",
    "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15", "2024-12-25",
    # 2025
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-18", "2025-05-01", "2025-08-15", "2025-10-01", "2025-10-02",
    "2025-10-21", "2025-10-22", "2025-11-05", "2025-12-25",
    # 2026
    "2026-01-26", "2026-02-17", "2026-03-10", "2026-03-20", "2026-03-31",
    "2026-04-02", "2026-04-13", "2026-05-01", "2026-06-26", "2026-08-15",
    "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-09", "2026-12-25",
}


def is_nse_holiday(d: date) -> bool:
    """True when NSE is closed and publishes no BhavCopy that day."""
    return d.weekday() >= 5 or d.isoformat() in NSE_HOLIDAYS


def is_trading_day(d: date) -> bool:
    """Check if a date is an NSE trading day (weekday and not a holiday)."""
    return not is_nse_holiday(d)


def get_trading_days(start_date: date, end_date: date) -> list[date]:
    """Get list of all weekdays between start and end (inclusive)."""
    current = start_date
    trading_days = []
    while current <= end_date:
        if is_trading_day(current):
            trading_days.append(current)
        current += dt.timedelta(days=1)
    return trading_days


class BhavcopyNotPublished(Exception):
    """NSE returned 404: the file does not exist yet (or the date is a holiday)."""
    pass


class NSEBhavCopyFetcher(BaseFetcher):
    """Fetches NSE BhavCopy EOD data directly from archives."""

    def __init__(self):
        super().__init__("NSE BhavCopy", delay=REQUEST_DELAY, max_retries=MAX_RETRIES)
        self.session = requests.Session()

    def fetch(self, trade_date: date) -> FetchResult:
        """Fetch BhavCopy for a single date."""
        return self._retry(self._fetch_single, trade_date)

    def _fetch_single(self, trade_date: date) -> FetchResult:
        """Internal single fetch with error handling."""
        try:
            df = self._download_csv(trade_date)
            if df.empty:
                return FetchResult(success=False, error="No EQ rows in NSE file")

            transformed = self._transform(df, trade_date)
            if transformed.empty:
                return FetchResult(success=False, error="All rows dropped: no usable close prices")

            data = transformed.to_dict(orient='records')
            self.log_fetch(len(data), f"for {trade_date}")
            return FetchResult(success=True, data=data)

        except BhavcopyNotPublished as e:
            return FetchResult(success=False, error=str(e), metadata={"retryable": True})
        except Exception as e:
            return self.handle_error(e, f"for {trade_date}")

    def _download_csv(self, trade_date: date) -> pd.DataFrame:
        """Download and parse the NSE full BhavCopy CSV for one date."""
        url = NSE_BHAVCOPY_URL.format(date_str=trade_date.strftime("%d%m%Y"))
        resp = self.session.get(url, headers=NSE_REQUEST_HEADERS, timeout=NSE_HTTP_TIMEOUT)

        if resp.status_code == 404:
            raise BhavcopyNotPublished(
                f"NSE has not published {trade_date} yet (HTTP 404)"
            )
        resp.raise_for_status()

        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]

        if 'SERIES' not in df.columns:
            raise DataParseError(f"Unexpected BhavCopy layout for {trade_date}: columns={list(df.columns)[:8]}")

        df['SERIES'] = df['SERIES'].astype(str).str.strip()
        return df[df['SERIES'] == 'EQ'].copy()

    def _transform(self, df: pd.DataFrame, trade_date: date) -> pd.DataFrame:
        """Map NSE CSV columns onto our schema."""
        df = df.copy()
        num = lambda col: pd.to_numeric(df[col], errors='coerce')

        result = pd.DataFrame()
        result['symbol'] = df['SYMBOL'].astype(str).str.strip()
        result['series'] = 'EQ'
        result['open'] = num('OPEN_PRICE')
        result['high'] = num('HIGH_PRICE')
        result['low'] = num('LOW_PRICE')
        result['close'] = num('CLOSE_PRICE')
        result['last'] = num('LAST_PRICE')
        result['prevclose'] = num('PREV_CLOSE')
        result['volume'] = num('TTL_TRD_QNTY')
        result['value_lakh'] = num('TURNOVER_LACS')
        result['del_pct'] = num('DELIV_PER')
        result['avg_price'] = num('AVG_PRICE')
        result['trade_date'] = trade_date.isoformat()

        return result.dropna(subset=['close'])

    def fetch_range(self, start_date: date, end_date: date) -> FetchResult:
        """Fetch multiple trading days in range."""
        trading_days = get_trading_days(start_date, end_date)
        logger.info("Fetching %d trading days from %s to %s", len(trading_days), start_date, end_date)

        all_data = []
        errors = []

        for i, trade_date in enumerate(trading_days, 1):
            result = self.fetch(trade_date)
            if result.success and result.data:
                all_data.extend(result.data)
            else:
                errors.append({"date": trade_date.isoformat(), "error": result.error})

            if i < len(trading_days):
                time.sleep(self.delay)

        return FetchResult(
            success=len(all_data) > 0,
            data=all_data,
            metadata={"errors": errors, "dates_requested": len(trading_days)}
        )

    def close(self):
        """Close HTTP session."""
        try:
            self.session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def classify_sync_status(trade_date: date, message: str) -> str:
    """
    Classify sync result based on date and error message.
    """
    msg_lower = message.lower()

    if is_nse_holiday(trade_date):
        return 'holiday'

    retryable = ('has not published', '404', 'no data', 'not available',
                 'holiday', 'no eq rows')
    if any(t in msg_lower for t in retryable):
        return 'not_available'

    return 'failed'
