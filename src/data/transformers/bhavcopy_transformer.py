"""
BhavCopy Data Transformer
Transforms raw NSE CSV data into analysis-ready format.
"""
import logging
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def transform_bhavcopy(df: pd.DataFrame, trade_date: date) -> pd.DataFrame:
    """
    Map the NSE CSV columns onto our schema.
    
    Expects the stripped, EQ-filtered frame from NSEBhavCopyFetcher.
    avg_price comes straight from NSE's AVG_PRICE column, which is the
    exchange's own per-day average traded price.
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


def prepare_for_analysis(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert transformed DataFrame to list of dicts for DB insertion."""
    return df.to_dict(orient='records')


def filter_valid_rows(df: pd.DataFrame, min_price: float = 20.0, min_volume: int = 10_000) -> pd.DataFrame:
    """Filter rows for analysis based on minimum criteria."""
    return df[
        (df['close'] >= min_price) &
        (df['volume'] >= min_volume)
    ].copy()


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns like change percentage."""
    df = df.copy()
    df['change'] = ((df['close'] - df['prevclose']) / df['prevclose'] * 100).round(2)
    df['change_abs'] = (df['close'] - df['prevclose']).round(2)
    return df
