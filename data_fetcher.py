"""
NSE BhavCopy data fetcher.
Handles historical backfill and incremental daily sync.

Fetches the official NSE archive CSV directly rather than through nsefin.
nsefin 0.1.5's get_equity_bhav_copy is a thin wrapper over the same public URL
(https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_<DDMMYYYY>.csv)
but it drops the AVG_PRICE column and swallows every error into an empty
DataFrame, which makes "NSE has not published yet" indistinguishable from a
real network failure. Reading the CSV ourselves keeps AVG_PRICE (NSE's own
per-day average traded price) and lets us classify 404 vs error correctly.
"""
import datetime as dt
import logging
import time
from datetime import date, datetime
from io import StringIO
from typing import Optional

import pandas as pd
import requests

from config import (
    HISTORICAL_START_DATE, REQUEST_DELAY,
    MAX_RETRIES, RETRY_BACKOFF, MAX_RETRY_DATES,
    NSE_BHAVCOPY_URL, NSE_REQUEST_HEADERS, NSE_HTTP_TIMEOUT,
    MARKET_CLOSE_HOUR, SYNC_RETRY_INTERVAL_MINUTES, SYNC_RETRY_UNTIL_HOUR,
)
from database import (
    insert_bhavcopy_batch, log_sync, get_last_synced_date,
    get_latest_trade_date, get_failed_syncs,
)

logger = logging.getLogger(__name__)


# BhavcopyNotPublished stays defined here for Phase 1. Phase 3 of the modular
# refactor will move it to marketmeter.core.errors and replace this definition
# with a back-compat alias. New code should prefer the marketmeter.core.errors
# version (same class, same exception identity once Phase 3 lands).
class BhavcopyNotPublished(Exception):
    """NSE returned 404: the file does not exist yet (or the date is a holiday)."""


# ── Trading Calendar ────────────────────────────────────────────────

# NSE trading holidays (CM segment), kept as iso-strings so the "does NSE
# publish today?" decision is data-driven and never reaches the network on a
# known closed day. Without this, a closed Monday/Friday was downloaded,
# 404'd, then misclassified 'not_available' and retried forever.
# Populate one rolling year ahead; covers 2024-2026 sync window.
NSE_HOLIDAYS = {
    # 2024
    "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29", "2024-04-11",
    "2024-04-17", "2024-04-21", "2024-05-23", "2024-06-17", "2024-07-17",
    "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15", "2024-12-25",
    # 2025
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-18", "2025-05-01", "2025-08-15", "2025-10-01", "2025-10-02",
    "2025-10-21", "2025-10-22", "2025-11-05", "2025-12-25",
    # 2026 (extend each year; a date not listed falls back to the 404 path)
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


def is_weekend_or_holiday(d: date) -> bool:
    """True for weekends and NSE holidays (both closed)."""
    return is_nse_holiday(d)


def get_trading_days(start_date: date, end_date: date) -> list[date]:
    """Get list of all weekdays between start and end (inclusive)."""
    current = start_date
    trading_days = []
    while current <= end_date:
        if is_trading_day(current):
            trading_days.append(current)
        current += dt.timedelta(days=1)
    return trading_days


def classify_sync_status(trade_date: date, message: str) -> str:
    """
    Classify sync result based on date and error message.
    - 'holiday' only for weekends/known holidays
    - 'not_available' for weekdays where NSE hasn't published yet (retryable)
    - 'failed' for actual errors
    """
    msg_lower = message.lower()

    # If it's a weekend, it's definitely a holiday
    if is_weekend_or_holiday(trade_date):
        return 'holiday'

    # For weekdays, distinguish between "NSE not ready yet" vs "real error".
    # 'has not published' / '404' cover BhavcopyNotPublished; the rest are the
    # older wordings, kept so historical sync_log rows stay classifiable.
    retryable = ('has not published', '404', 'no data', 'not available',
                 'holiday', 'no eq rows')
    if any(t in msg_lower for t in retryable):
        return 'not_available'  # NSE hasn't published yet — will retry

    return 'failed'


# ── BhavCopy Download ──────────────────────────────────────────────

def fetch_bhavcopy_csv(trade_date: date, session: Optional[requests.Session] = None) -> pd.DataFrame:
    """
    Download and parse the NSE full BhavCopy CSV for one date.

    Raises BhavcopyNotPublished on 404 so the caller can distinguish "not yet
    published" from a genuine transport error. Every other failure propagates.
    """
    url = NSE_BHAVCOPY_URL.format(date_str=trade_date.strftime("%d%m%Y"))
    getter = session.get if session is not None else requests.get
    resp = getter(url, headers=NSE_REQUEST_HEADERS, timeout=NSE_HTTP_TIMEOUT)

    if resp.status_code == 404:
        raise BhavcopyNotPublished(
            f"NSE has not published {trade_date} yet (HTTP 404 at {url})"
        )
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))
    # NSE ships leading spaces in every header and in SERIES values.
    df.columns = [c.strip() for c in df.columns]
    if 'SERIES' not in df.columns:
        raise ValueError(
            f"Unexpected BhavCopy layout for {trade_date}: columns={list(df.columns)[:8]}. "
            "NSE may have changed the archive format; check the CSV manually."
        )
    df['SERIES'] = df['SERIES'].astype(str).str.strip()
    return df[df['SERIES'] == 'EQ'].copy()


def transform_bhavcopy(df: pd.DataFrame, trade_date: date) -> pd.DataFrame:
    """
    Map the NSE CSV columns onto our schema.

    Expects the stripped, EQ-filtered frame from fetch_bhavcopy_csv. avg_price
    comes straight from NSE's AVG_PRICE column, which is the exchange's own
    per-day average traded price -- more authoritative than deriving
    turnover/volume ourselves.
    """
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

    # A row with no close price is unusable downstream; drop rather than store NaN.
    return result.dropna(subset=['close'])


def download_bhavcopy_for_date(trade_date: date,
                               session: Optional[requests.Session] = None,
                               nse_client=None) -> tuple[bool, Optional[pd.DataFrame], str]:
    """
    Download bhavcopy for a single date.

    nse_client is accepted and ignored for backward compatibility with callers
    that still pass a reusable client.
    Returns: (success, DataFrame or None, message)
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = fetch_bhavcopy_csv(trade_date, session=session)

            if raw.empty:
                return (False, None,
                        "No EQ rows in NSE file (not yet published or genuine holiday)")

            df = transform_bhavcopy(raw, trade_date)
            if df.empty:
                return (False, None, "All rows dropped: no usable close prices")
            return (True, df, f"Downloaded {len(df)} records")

        except BhavcopyNotPublished as e:
            # Deterministic: retrying inside this call cannot help. Report it so
            # classify_sync_status marks the date retryable at a later time.
            return (False, None, str(e))

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.warning("Attempt %d/%d for %s failed: %s",
                           attempt, MAX_RETRIES, trade_date, error_msg)

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF ** attempt)  # OK: runs in executor thread
            else:
                return (False, None, error_msg)

    return (False, None, "Unknown error")


def download_and_store_date(trade_date: date,
                            session: Optional[requests.Session] = None,
                            nse_client=None) -> dict:
    """
    Download bhavcopy for a date and store in DB.

    nse_client is accepted and ignored for backward compatibility.
    Returns status dict for logging.
    """
    success, df, message = download_bhavcopy_for_date(trade_date, session=session)

    if not success:
        # 🔧 FIX: Use proper classification based on date + message
        status = classify_sync_status(trade_date, message)
        log_sync(trade_date, status, 0, message)
        return {
            'date': trade_date,
            'status': status,
            'records': 0,
            'message': message,
        }

    # Convert to list of dicts for DB insert
    rows = df.to_dict(orient='records')
    inserted = insert_bhavcopy_batch(rows)

    # Status stays 'success' (sync_log CHECK constraint admits only a fixed set),
    # which is accurate: the date downloaded and reconciled. The honest signal
    # lives in records_count + net_new, so a duplicate/partial re-run is never
    # mistaken for a fresh batch of rows.
    log_sync(trade_date, 'success', inserted)
    logger.info("Reconciled %s: %d net-new rows", trade_date, inserted)

    return {
        'date': trade_date,
        'status': 'success',
        'records': inserted,
        'net_new': inserted > 0,
        'message': message,
    }


# ── Incremental Sync ────────────────────────────────────────────────

def sync_incremental_data() -> dict:
    """
    Sync missing trading days from last synced date to today.
    Also retries previously failed dates.
    Returns summary dict.
    """
    today = date.today()
    last_synced = get_last_synced_date()

    # Determine start date for sync
    if last_synced is None:
        latest_in_db = get_latest_trade_date()
        if latest_in_db is None:
            start = date.fromisoformat(HISTORICAL_START_DATE)
            logger.info("No data found. Starting backfill from %s", start)
        else:
            start = latest_in_db + dt.timedelta(days=1)
            logger.info("Resuming from last DB date: %s", start)
    else:
        start = last_synced + dt.timedelta(days=1)
        logger.info("Last synced: %s. Starting from: %s", last_synced, start)

    # 🔧 FIX: Only retry last N failed dates (avoid processing 200+ stale failures)
    failed_dates = get_failed_syncs()
    retry_dates = [date.fromisoformat(f['trade_date']) for f in failed_dates[-MAX_RETRY_DATES:]]  # Only last N

    # Get trading days to sync
    if start <= today:
        new_dates = get_trading_days(start, today)
    else:
        new_dates = []

    # Today's file does not exist until after the 15:30 close. Requesting it
    # earlier guarantees a 404 that gets logged as not_available, which is
    # exactly how 2026-07-29 was lost: synced at 09:21, never retried.
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
        return {
            'status': 'up_to_date',
            'dates_processed': 0,
            'success': 0,
            'failed': 0,
            'holidays': 0,
            'total_records': 0,
            'message': 'Already up to date',
        }

    logger.info("Syncing %d dates (%d retries, %d new)",
                len(all_dates), len(retry_dates), len(new_dates))

    # Reuse one HTTP session across all dates so TCP connections are pooled
    # rather than reopened per request.
    session = requests.Session()
    try:
        results = {
            'status': 'completed',
            'dates_processed': 0,
            'success': 0,
            'failed': 0,
            'holidays': 0,
            'not_available': [],
            'synced_dates': [],
            'per_date_records': {},
            'total_records': 0,
        }

        for i, trade_date in enumerate(all_dates, 1):
            logger.info("[%d/%d] Processing %s...", i, len(all_dates), trade_date)
            result = download_and_store_date(trade_date, session=session)

            results['dates_processed'] += 1
            if result['status'] == 'success':
                results['success'] += 1
                results['total_records'] += result['records']
                # Only dates that actually added rows belong in the receipt and
                # banner -- a 0-net-new re-run must not be announced as inserted.
                if result['records'] > 0:
                    results['synced_dates'].append(trade_date.isoformat())
                    results['per_date_records'][trade_date.isoformat()] = result['records']
            elif result['status'] == 'holiday':
                results['holidays'] += 1
            elif result['status'] == 'not_available':
                results['not_available'].append(trade_date.isoformat())
            else:
                results['failed'] += 1

            # Rate limiting
            if i < len(all_dates):
                time.sleep(REQUEST_DELAY)

        # Build summary message
        parts = [f"Sync complete: {results['success']} success"]
        if results['failed']:
            parts.append(f"{results['failed']} failed")
        if results['holidays']:
            parts.append(f"{results['holidays']} holidays")
        if results['not_available']:
            parts.append(f"{len(results['not_available'])} pending (NSE not ready)")
        parts.append(f"{results['total_records']} records inserted")

        results['message'] = ", ".join(parts)
        logger.info(results['message'])

        return results
    finally:
        # Close session to free TCP connections
        try:
            session.close()
        except Exception:
            pass


def backfill_historical_data(start_date: Optional[date] = None,
                              end_date: Optional[date] = None) -> dict:
    """
    Full historical backfill from start_date to end_date.
    This is the initial data load function.
    """
    if start_date is None:
        start_date = date.fromisoformat(HISTORICAL_START_DATE)
    if end_date is None:
        end_date = date.today()

    trading_days = get_trading_days(start_date, end_date)
    logger.info("Backfilling %d trading days from %s to %s",
                len(trading_days), start_date, end_date)

    results = {
        'status': 'completed',
        'dates_processed': 0,
        'success': 0,
        'failed': 0,
        'holidays': 0,
        'total_records': 0,
        'details': [],
    }

    for i, trade_date in enumerate(trading_days, 1):
        if i % 50 == 0:
            logger.info("Backfill progress: %d/%d days, %d records so far",
                        i, len(trading_days), results['total_records'])

        result = download_and_store_date(trade_date)

        results['dates_processed'] += 1
        if result['status'] == 'success':
            results['success'] += 1
            results['total_records'] += result['records']
        elif result['status'] == 'holiday':
            results['holidays'] += 1
        else:
            results['failed'] += 1

        results['details'].append(result)
        time.sleep(REQUEST_DELAY)

    results['message'] = (
        f"Backfill complete: {results['success']} success, "
        f"{results['failed']} failed, {results['holidays']} holidays, "
        f"{results['total_records']} total records"
    )
    logger.info(results['message'])
    return results
