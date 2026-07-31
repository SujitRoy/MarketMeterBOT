"""
Trend Indicators
SMA, EMA, ADX, etc.
"""
import numpy as np
import pandas as pd

from src.analysis.indicators.base import BaseIndicator


class SMAIndicator(BaseIndicator):
    """Simple Moving Average."""

    def __init__(self, window: int):
        super().__init__(f"SMA{window}", window=window)
        self.window = window

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return data['close'].rolling(window=self.window).mean()


class EMAIndicator(BaseIndicator):
    """Exponential Moving Average."""

    def __init__(self, window: int):
        super().__init__(f"EMA{window}", window=window)
        self.window = window

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return data['close'].ewm(span=self.window, adjust=False).mean()


class ADXIndicator(BaseIndicator):
    """Average Directional Index."""

    def __init__(self, window: int = 14):
        super().__init__("ADX", window=window)
        self.window = window

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        high = data['high']
        low = data['low']
        close = data['close']

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.window).mean()

        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        plus_dm_s = pd.Series(plus_dm, index=high.index).rolling(window=self.window).mean()
        minus_dm_s = pd.Series(minus_dm, index=high.index).rolling(window=self.window).mean()

        plus_di = 100 * (plus_dm_s / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm_s / atr.replace(0, np.nan))

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(window=self.window).mean()

        return pd.DataFrame({
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di,
        }, index=data.index)


class ParabolicSARIndicator(BaseIndicator):
    """Parabolic SAR."""

    def __init__(self, step: float = 0.02, max_step: float = 0.2):
        super().__init__("ParabolicSAR", step=step, max_step=max_step)
        self.step = step
        self.max_step = max_step

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        high = data['high']
        low = data['low']

        sar = pd.Series(index=data.index, dtype=float)
        ep = pd.Series(index=data.index, dtype=float)
        af = pd.Series(index=data.index, dtype=float)
        trend = pd.Series(index=data.index, dtype=int)  # 1 = up, -1 = down

        # Initialize
        sar.iloc[0] = low.iloc[0]
        ep.iloc[0] = high.iloc[0]
        af.iloc[0] = self.step
        trend.iloc[0] = 1

        for i in range(1, len(data)):
            # Calculate SAR
            sar.iloc[i] = sar.iloc[i-1] + af.iloc[i-1] * (ep.iloc[i-1] - sar.iloc[i-1])

            # Check trend reversal
            if trend.iloc[i-1] == 1:  # Uptrend
                if low.iloc[i] < sar.iloc[i]:
                    # Reversal to downtrend
                    trend.iloc[i] = -1
                    sar.iloc[i] = ep.iloc[i-1]
                    ep.iloc[i] = low.iloc[i]
                    af.iloc[i] = self.step
                else:
                    trend.iloc[i] = 1
                    if high.iloc[i] > ep.iloc[i-1]:
                        ep.iloc[i] = high.iloc[i]
                        af.iloc[i] = min(af.iloc[i-1] + self.step, self.max_step)
                    else:
                        ep.iloc[i] = ep.iloc[i-1]
                        af.iloc[i] = af.iloc[i-1]
            else:  # Downtrend
                if high.iloc[i] > sar.iloc[i]:
                    # Reversal to uptrend
                    trend.iloc[i] = 1
                    sar.iloc[i] = ep.iloc[i-1]
                    ep.iloc[i] = high.iloc[i]
                    af.iloc[i] = self.step
                else:
                    trend.iloc[i] = -1
                    if low.iloc[i] < ep.iloc[i-1]:
                        ep.iloc[i] = low.iloc[i]
                        af.iloc[i] = min(af.iloc[i-1] + self.step, self.max_step)
                    else:
                        ep.iloc[i] = ep.iloc[i-1]
                        af.iloc[i] = af.iloc[i-1]

        return sar
