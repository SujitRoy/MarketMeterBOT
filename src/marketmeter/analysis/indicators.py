"""
analysis/indicators — pure technical indicator math.

Phase 4 split: these 7 functions were previously top-level in /analyzer.py.
Moving them to analysis/indicators.py makes the analysis package a leaf
that depends only on pandas/numpy and the core config. The downstream
analyzer.py / batch.py / outlook.py modules in this package import from here.

All functions are byte-identical to the originals. No behaviour change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calc_sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window).mean()


def calc_ema(series: pd.Series, window: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=window, adjust=False).mean()


def calc_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram."""
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()


def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=window).mean()

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm_s = pd.Series(plus_dm, index=high.index).rolling(window=window).mean()
    minus_dm_s = pd.Series(minus_dm, index=high.index).rolling(window=window).mean()

    plus_di = 100 * (plus_dm_s / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm_s / atr.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(window=window).mean()


def calc_bollinger_bands(series: pd.Series, window: int = 20, num_std: int = 2):
    """Bollinger Bands: upper, middle, lower."""
    sma = calc_sma(series, window)
    std = series.rolling(window=window).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, sma, lower


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume).cumsum()
    return obv


__all__ = [
    "calc_sma",
    "calc_ema",
    "calc_rsi",
    "calc_macd",
    "calc_atr",
    "calc_adx",
    "calc_bollinger_bands",
    "calc_obv",
]
