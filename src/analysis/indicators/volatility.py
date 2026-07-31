"""
Volatility Indicators
ATR, Bollinger Bands, etc.
"""
import pandas as pd

from src.analysis.indicators.base import BaseIndicator


class ATRIndicator(BaseIndicator):
    """Average True Range."""

    def __init__(self, window: int = 14):
        super().__init__("ATR", window=window)
        self.window = window

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        high = data['high']
        low = data['low']
        close = data['close']

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(window=self.window).mean()


class BollingerBandsIndicator(BaseIndicator):
    """Bollinger Bands."""

    def __init__(self, window: int = 20, num_std: float = 2.0):
        super().__init__("BollingerBands", window=window, num_std=num_std)
        self.window = window
        self.num_std = num_std

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data['close']
        sma = close.rolling(window=self.window).mean()
        std = close.rolling(window=self.window).std()

        upper = sma + (std * self.num_std)
        lower = sma - (std * self.num_std)

        return pd.DataFrame({
            'bb_upper': upper,
            'bb_middle': sma,
            'bb_lower': lower,
        }, index=data.index)

    def get_latest(self, data: pd.DataFrame) -> dict:
        """Get latest Bollinger Band values."""
        result = self.calculate(data)
        return {
            'upper': float(result['bb_upper'].iloc[-1]) if not pd.isna(result['bb_upper'].iloc[-1]) else None,
            'middle': float(result['bb_middle'].iloc[-1]) if not pd.isna(result['bb_middle'].iloc[-1]) else None,
            'lower': float(result['bb_lower'].iloc[-1]) if not pd.isna(result['bb_lower'].iloc[-1]) else None,
        }


class KeltnerChannelsIndicator(BaseIndicator):
    """Keltner Channels."""

    def __init__(self, window: int = 20, atr_window: int = 10, multiplier: float = 2.0):
        super().__init__("KeltnerChannels", window=window, atr_window=atr_window, multiplier=multiplier)
        self.window = window
        self.atr_window = atr_window
        self.multiplier = multiplier

    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data['close']
        high = data['high']
        low = data['low']

        ema = close.ewm(span=self.window, adjust=False).mean()

        # Calculate ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_window).mean()

        upper = ema + (atr * self.multiplier)
        lower = ema - (atr * self.multiplier)

        return pd.DataFrame({
            'kc_upper': upper,
            'kc_middle': ema,
            'kc_lower': lower,
        }, index=data.index)
