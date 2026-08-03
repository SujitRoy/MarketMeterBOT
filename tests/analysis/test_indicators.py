"""
tests/analysis/test_indicators.py — pure math tests for analysis/indicators.py.

These tests prove the indicator math is correct. They use pre-built
sample DataFrames instead of the live DB, so they run in microseconds
and are fully deterministic.

Phase 7 §3 mandate: "Indicator math tests (pure pandas, no DB)."
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from marketmeter.analysis.indicators import (
    calc_sma, calc_ema, calc_rsi, calc_macd, calc_atr, calc_adx,
    calc_bollinger_bands, calc_obv,
)


# ── A canonical synthetic OHLCV frame for tests ─────────────────────────────
def _ohlcv(prices):
    """Build a deterministic OHLCV frame from a list of close prices.

    Other columns are derived from closes for reproducibility:
      open = prev close
      high = close * 1.01
      low  = close * 0.99
      volume = 1_000_000
    """
    n = len(prices)
    closes = np.array(prices, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = closes * 1.01
    lows = closes * 0.99
    volumes = np.full(n, 1_000_000, dtype=int)
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


# ── Simple Moving Average ───────────────────────────────────────────────────

class TestCalcSma:
    def test_short_window_equals_manual(self):
        prices = list(range(1, 11))  # 1..10
        df = _ohlcv(prices)
        sma = calc_sma(df["close"], 3)
        # Expected: NaN NaN 2.0 3.0 4.0 5.0 6.0 7.0 8.0 9.0
        expected = [np.nan, np.nan, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
        for i, exp in enumerate(expected):
            if np.isnan(exp):
                assert np.isnan(sma.iloc[i])
            else:
                assert sma.iloc[i] == exp

    def test_window_larger_than_series(self):
        df = _ohlcv([10.0, 20.0])
        sma = calc_sma(df["close"], 5)
        # All NaN
        assert sma.isna().all()

    def test_window_equals_series_length(self):
        df = _ohlcv([10.0, 20.0, 30.0])
        sma = calc_sma(df["close"], 3)
        # Only last value is valid
        assert pd.isna(sma.iloc[0])
        assert pd.isna(sma.iloc[1])
        assert sma.iloc[2] == 20.0


# ── Exponential Moving Average ──────────────────────────────────────────────

class TestCalcEma:
    def test_first_value_equals_first_price(self):
        df = _ohlcv([10.0, 20.0, 30.0, 40.0, 50.0])
        ema = calc_ema(df["close"], 3)
        # Standard EMA: first value = first close (with adjust=False)
        assert ema.iloc[0] == 10.0

    def test_smoothes_upward_trend(self):
        # If prices are monotonically increasing, EMA should be increasing
        df = _ohlcv([float(i) for i in range(1, 21)])
        ema = calc_ema(df["close"], 5)
        for i in range(1, len(ema)):
            assert ema.iloc[i] > ema.iloc[i - 1]

    def test_window_larger_than_series(self):
        df = _ohlcv([10.0, 20.0])
        ema = calc_ema(df["close"], 5)
        # Should still work, just with fewer effective samples
        assert not ema.isna().all()


# ── Relative Strength Index ───────────────────────────────────────────────

class TestCalcRsi:
    def test_rsi_strong_uptrend_is_high(self):
        # A strong, consistent uptrend with small noise → RSI should be very high
        prices = [10.0, 10.5, 10.2, 10.8, 10.6, 11.0, 10.9, 11.2,
                  11.0, 11.5, 11.3, 11.8, 11.6, 12.0, 12.5]
        df = _ohlcv(prices)
        rsi = calc_rsi(df["close"], 14)
        # The last value should be high (strong uptrend)
        assert rsi.iloc[-1] > 70

    def test_rsi_strong_downtrend_is_low(self):
        prices = [12.0, 11.5, 11.8, 11.2, 11.4, 11.0, 11.1, 10.8,
                  11.0, 10.5, 10.7, 10.2, 10.4, 10.0, 9.5]
        df = _ohlcv(prices)
        rsi = calc_rsi(df["close"], 14)
        # The last value should be low (strong downtrend)
        assert rsi.iloc[-1] < 30

    def test_rsi_range_is_0_to_100(self):
        import random
        random.seed(42)
        prices = [100 + random.uniform(-5, 5) for _ in range(50)]
        df = _ohlcv(prices)
        rsi = calc_rsi(df["close"], 14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


# ── MACD ───────────────────────────────────────────────────────────────────

class TestCalcMacd:
    def test_returns_three_series(self):
        df = _ohlcv([float(i) for i in range(1, 51)])
        macd_line, signal_line, hist = calc_macd(df["close"])
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(hist, pd.Series)

    def test_histogram_is_macd_minus_signal(self):
        df = _ohlcv([float(i) for i in range(1, 51)])
        macd_line, signal_line, hist = calc_macd(df["close"])
        # On any non-NaN row, hist should equal macd - signal
        for i in range(len(hist)):
            if not (pd.isna(macd_line.iloc[i]) or pd.isna(signal_line.iloc[i])):
                assert hist.iloc[i] == pytest.approx(
                    macd_line.iloc[i] - signal_line.iloc[i], abs=1e-9
                )


# ── Average True Range ────────────────────────────────────────────────────

class TestCalcAtr:
    def test_atr_non_negative(self):
        # ATR is always non-negative
        prices = [10, 12, 11, 13, 12, 14, 13, 15, 14, 16]
        df = _ohlcv(prices)
        atr = calc_atr(df["high"], df["low"], df["close"], 14)
        valid = atr.dropna()
        assert (valid >= 0).all()

    def test_atr_window_larger_than_series(self):
        df = _ohlcv([10.0, 11.0, 12.0])
        atr = calc_atr(df["high"], df["low"], df["close"], 14)
        # All NaN because the window is larger than the series
        assert atr.isna().all()


# ── Average Directional Index ──────────────────────────────────────────────

class TestCalcAdx:
    def test_adx_window_larger_than_series(self):
        df = _ohlcv([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        adx = calc_adx(df["high"], df["low"], df["close"], 14)
        assert adx.isna().all()

    def test_adx_non_negative(self):
        prices = [10 + i * 0.1 for i in range(40)]
        df = _ohlcv(prices)
        adx = calc_adx(df["high"], df["low"], df["close"], 14)
        valid = adx.dropna()
        assert (valid >= 0).all()


# ── Bollinger Bands ────────────────────────────────────────────────────────

class TestCalcBollingerBands:
    def test_returns_upper_middle_lower(self):
        df = _ohlcv([float(i) for i in range(1, 31)])
        upper, middle, lower = calc_bollinger_bands(df["close"], 20, 2)
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)

    def test_middle_equals_sma(self):
        df = _ohlcv([float(i) for i in range(1, 31)])
        upper, middle, lower = calc_bollinger_bands(df["close"], 20, 2)
        expected_sma = calc_sma(df["close"], 20)
        # middle band should match the SMA
        for i in range(len(middle)):
            if not pd.isna(middle.iloc[i]):
                assert middle.iloc[i] == pytest.approx(expected_sma.iloc[i], abs=1e-9)

    def test_upper_above_lower(self):
        # By construction, upper > middle > lower
        prices = [100 + i for i in range(30)]
        df = _ohlcv(prices)
        upper, middle, lower = calc_bollinger_bands(df["close"], 20, 2)
        for i in range(20, 30):  # only valid window
            if not pd.isna(upper.iloc[i]):
                assert upper.iloc[i] >= middle.iloc[i]
                assert middle.iloc[i] >= lower.iloc[i]


# ── On-Balance Volume ──────────────────────────────────────────────────────

class TestCalcObv:
    def test_returns_series_of_same_length(self):
        df = _ohlcv([10.0, 11.0, 12.0, 11.0, 10.0])
        obv = calc_obv(df["close"], df["volume"])
        assert isinstance(obv, pd.Series)
        assert len(obv) == len(df)

    def test_increasing_prices_increases_obv(self):
        # Volume is constant, prices strictly increasing → OBV should
        # monotonically increase (each day adds the full volume).
        prices = [10.0, 11.0, 12.0, 13.0]
        df = _ohlcv(prices)
        obv = calc_obv(df["close"], df["volume"])
        for i in range(1, len(obv)):
            # OBV strictly increases
            assert obv.iloc[i] > obv.iloc[i - 1]
