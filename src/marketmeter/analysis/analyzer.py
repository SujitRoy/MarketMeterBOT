# ruff: noqa: E701, E702
"""
analysis/analyzer — per-symbol analysis pipeline.

Phase 4 split: analyze_stock() from /analyzer.py. Takes a price-history
DataFrame and returns a dict with all indicator values + recommendation.

This is the single-symbol workhorse. It depends on:
- analysis/indicators.py for the math
- analysis/scoring.py for the score -> label mapping
- marketmeter.core.config for filters
- marketmeter.core.logging for the logger

The output shape is the contract: every key here is a column in the
daily_analysis table and a potential field in the morning report.
"""
from __future__ import annotations

from typing import Optional  # noqa: F401

import numpy as np
import pandas as pd

from marketmeter.core.config import MIN_PRICE, MIN_DATA_POINTS
from marketmeter.core.logging import get_logger
from marketmeter.analysis.indicators import (
    calc_sma, calc_ema, calc_rsi, calc_macd, calc_atr, calc_adx,
    calc_bollinger_bands, calc_obv,
)
from marketmeter.analysis.scoring import _get_recommendation

logger = get_logger(__name__)


def analyze_stock(df, symbol: str) -> Optional[dict]:
    """
    Full technical analysis for a single stock.
    Returns dict with all indicators and signals, or None if insufficient data.

    Accepts either a pd.DataFrame (legacy callers, tests) or a list[dict]
    (the new db.bhavcopy_repo contract — Phase 6 fix).
    """
    # Phase 6 refactor: db.bhavcopy_repo.get_stock_history returns a list of
    # dicts rather than a DataFrame. Normalise here so callers don't have to
    # know which module they're reading from.
    if isinstance(df, list):
        if not df:
            return None
        df = pd.DataFrame(df)

    if len(df) < MIN_DATA_POINTS:
        return None

    df = df.sort_values('trade_date').reset_index(drop=True)

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # ── Indicators ──
    sma_20 = calc_sma(close, 20).iloc[-1]
    sma_50 = calc_sma(close, 50).iloc[-1]
    sma_100 = calc_sma(close, 100).iloc[-1]
    sma_200 = calc_sma(close, 200).iloc[-1] if len(close) >= 200 else np.nan

    ema_20 = calc_ema(close, 20).iloc[-1]
    ema_50 = calc_ema(close, 50).iloc[-1]
    ema_100 = calc_ema(close, 100).iloc[-1] if len(close) >= 100 else np.nan
    ema_200 = calc_ema(close, 200).iloc[-1] if len(close) >= 200 else np.nan

    rsi_14 = calc_rsi(close, 14).iloc[-1]
    macd_line, signal_line, macd_hist = calc_macd(close)
    macd_line = macd_line.iloc[-1]
    signal_line = signal_line.iloc[-1]
    macd_hist = macd_hist.iloc[-1]

    atr_14 = calc_atr(high, low, close, 14).iloc[-1]
    adx_14 = calc_adx(high, low, close, 14).iloc[-1]

    bb_upper, bb_middle, bb_lower = calc_bollinger_bands(close)
    bb_upper = bb_upper.iloc[-1]
    bb_lower = bb_lower.iloc[-1]

    obv_series = calc_obv(close, volume)
    obv_trend = obv_series.iloc[-1] - obv_series.iloc[-20] if len(obv_series) >= 20 else 0

    avg_vol = volume.rolling(20).mean().iloc[-1]
    avg_price = df['avg_price'].iloc[-1] if 'avg_price' in df.columns else None

    # ── Relative Volume (today's vol / 20d avg) ──
    rel_volume = float(volume.iloc[-1] / avg_vol) if avg_vol and avg_vol > 0 else None

    # ── Composite Score ──
    score = 0
    if rsi_14 is not None and not np.isnan(rsi_14):
        if 60 <= rsi_14 <= 75:   score += 3  # noqa: E701
        elif rsi_14 > 75:        score += 2  # noqa: E701
        elif rsi_14 > 50:        score += 1  # noqa: E701
    if adx_14 is not None and not np.isnan(adx_14):
        if adx_14 > 50:   score += 3
        elif adx_14 > 30: score += 2
        elif adx_14 > 20: score += 1
    if rel_volume is not None:
        if rel_volume > 3:   score += 3
        elif rel_volume > 2: score += 2
        elif rel_volume > 1.5: score += 1
    if macd_line is not None and not np.isnan(macd_line) and signal_line is not None and not np.isnan(signal_line):
        if macd_line > signal_line: score += 2
    if sma_20 is not None and not np.isnan(sma_20) and close.iloc[-1] > sma_20: score += 2
    if sma_50 is not None and not np.isnan(sma_50) and close.iloc[-1] > sma_50: score += 2
    if sma_100 is not None and not np.isnan(sma_100) and close.iloc[-1] > sma_100: score += 1
    if sma_20 is not None and not np.isnan(sma_20) and close.iloc[-1] > sma_20 * 1.05: score += 1
    if obv_trend > 0: score += 1

    recommendation, _ = _get_recommendation(
        int(score),
        float(rsi_14) if rsi_14 is not None and not np.isnan(rsi_14) else None,
        float(adx_14) if adx_14 is not None and not np.isnan(adx_14) else None,
    )

    # ── Quality gate: must have price + volume ──
    if close.iloc[-1] < MIN_PRICE:
        return None
    if volume.iloc[-1] < 10000:
        return None

    return {
        'symbol': symbol,
        'close': float(close.iloc[-1]),
        'volume': int(volume.iloc[-1]),
        'rsi_14': None if rsi_14 is None or np.isnan(rsi_14) else float(rsi_14),
        'adx_14': None if adx_14 is None or np.isnan(adx_14) else float(adx_14),
        'macd_line': None if macd_line is None or np.isnan(macd_line) else float(macd_line),
        'signal_line': None if signal_line is None or np.isnan(signal_line) else float(signal_line),
        'macd_hist': None if macd_hist is None or np.isnan(macd_hist) else float(macd_hist),
        'sma_20': None if sma_20 is None or np.isnan(sma_20) else float(sma_20),
        'sma_50': None if sma_50 is None or np.isnan(sma_50) else float(sma_50),
        'sma_100': None if sma_100 is None or np.isnan(sma_100) else float(sma_100),
        'sma_200': None if sma_200 is None or np.isnan(sma_200) else float(sma_200),
        'ema_20': None if ema_20 is None or np.isnan(ema_20) else float(ema_20),
        'ema_50': None if ema_50 is None or np.isnan(ema_50) else float(ema_50),
        'ema_100': None if ema_100 is None or np.isnan(ema_100) else float(ema_100),
        'ema_200': None if ema_200 is None or np.isnan(ema_200) else float(ema_200),
        'atr_14': None if atr_14 is None or np.isnan(atr_14) else float(atr_14),
        'bb_upper': None if bb_upper is None or np.isnan(bb_upper) else float(bb_upper),
        'bb_lower': None if bb_lower is None or np.isnan(bb_lower) else float(bb_lower),
        'rel_volume': rel_volume,
        'obv_trend': float(obv_trend),
        'avg_price': None if avg_price is None or (isinstance(avg_price, float) and np.isnan(avg_price)) else float(avg_price),
        'composite_score': int(score),
        'recommendation': recommendation,
    }


__all__ = ["analyze_stock"]
