"""
Volume Indicators
OBV, Relative Volume, Volume Profile, etc.
"""
import numpy as np
import pandas as pd

from src.analysis.indicators.base import BaseIndicator


class OBVIndicator(BaseIndicator):
    """On-Balance Volume."""

    def __init__(self, lookback: int = 20):
        super().__init__("OBV", lookback=lookback)
        self.lookback = lookback

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data['close']
        volume = data['volume']

        direction = np.sign(close.diff()).fillna(0)
        obv = (direction * volume).cumsum()

        return obv

    def get_trend(self, data: pd.DataFrame) -> float:
        """Get OBV trend over lookback period."""
        obv = self.calculate(data)
        if len(obv) >= self.lookback:
            return float(obv.iloc[-1] - obv.iloc[-self.lookback])
        return 0.0


class RelativeVolumeIndicator(BaseIndicator):
    """Relative Volume vs rolling average."""

    def __init__(self, window: int = 20):
        super().__init__("RelativeVolume", window=window)
        self.window = window

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        volume = data['volume']
        avg_volume = volume.rolling(window=self.window).mean()
        return volume / avg_volume.replace(0, np.nan)


class VWAPIndicator(BaseIndicator):
    """Volume Weighted Average Price (session VWAP)."""

    def __init__(self):
        super().__init__("VWAP")
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate session VWAP from OHLCV data."""
        high = data['high']
        low = data['low']
        close = data['close']
        volume = data['volume']

        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum().replace(0, np.nan)

        return vwap


class VolumeProfileIndicator(BaseIndicator):
    """Volume Profile - volume at each price level."""

    def __init__(self, bins: int = 50):
        super().__init__("VolumeProfile", bins=bins)
        self.bins = bins

    def calculate(self, data: pd.DataFrame) -> dict:
        """Calculate volume profile as price -> volume mapping."""
        high = data['high'].max()
        low = data['low'].min()

        if pd.isna(high) or pd.isna(low) or high == low:
            return {}

        price_bins = np.linspace(low, high, self.bins + 1)
        volumes = np.zeros(self.bins)

        for _, row in data.iterrows():
            if pd.isna(row['close']) or pd.isna(row['volume']):
                continue
            # Distribute volume across the day's range
            price_range = row['high'] - row['low']
            if price_range > 0:
                weight = row['volume'] / self.bins
                for i in range(self.bins):
                    bin_mid = (price_bins[i] + price_bins[i+1]) / 2
                    if row['low'] <= bin_mid <= row['high']:
                        volumes[i] += weight

        return dict(zip([(price_bins[i] + price_bins[i+1])/2 for i in range(self.bins)], volumes))
