"""
Momentum Indicators
RSI, MACD, Stochastic, etc.
"""
import numpy as np
import pandas as pd

from src.analysis.indicators.base import BaseIndicator


class RSIIndicator(BaseIndicator):
    """Relative Strength Index."""

    def __init__(self, window: int = 14):
        super().__init__("RSI", window=window)
        self.window = window

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data['close']
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=self.window).mean()
        avg_loss = loss.rolling(window=self.window).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))


class MACDIndicator(BaseIndicator):
    """Moving Average Convergence Divergence."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__("MACD", fast=fast, slow=slow, signal=signal)
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Returns DataFrame with macd, signal, histogram columns."""
        close = data['close']
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return pd.DataFrame({
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram,
        }, index=data.index)

    def get_latest(self, data: pd.DataFrame) -> dict:
        """Get latest MACD values."""
        result = self.calculate(data)
        return {
            'macd': float(result['macd'].iloc[-1]) if not pd.isna(result['macd'].iloc[-1]) else None,
            'signal': float(result['signal'].iloc[-1]) if not pd.isna(result['signal'].iloc[-1]) else None,
            'histogram': float(result['histogram'].iloc[-1]) if not pd.isna(result['histogram'].iloc[-1]) else None,
        }


class StochasticIndicator(BaseIndicator):
    """Stochastic Oscillator."""

    def __init__(self, k_window: int = 14, d_window: int = 3):
        super().__init__("Stochastic", k_window=k_window, d_window=d_window)
        self.k_window = k_window
        self.d_window = d_window

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        high = data['high']
        low = data['low']
        close = data['close']

        lowest_low = low.rolling(window=self.k_window).min()
        highest_high = high.rolling(window=self.k_window).max()

        k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
        d_percent = k_percent.rolling(window=self.d_window).mean()

        return pd.DataFrame({
            'stoch_k': k_percent,
            'stoch_d': d_percent,
        }, index=data.index)
