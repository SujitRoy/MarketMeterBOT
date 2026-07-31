"""
Indicators Package
All technical indicators organized by category.
"""
from src.analysis.indicators.base import BaseIndicator
from src.analysis.indicators.momentum import MACDIndicator, RSIIndicator, StochasticIndicator
from src.analysis.indicators.trend import (
    ADXIndicator,
    EMAIndicator,
    ParabolicSARIndicator,
    SMAIndicator,
)
from src.analysis.indicators.volatility import (
    ATRIndicator,
    BollingerBandsIndicator,
    KeltnerChannelsIndicator,
)
from src.analysis.indicators.volume import (
    OBVIndicator,
    RelativeVolumeIndicator,
    VolumeProfileIndicator,
    VWAPIndicator,
)


# Convenience function to create all standard indicators
def create_standard_indicators():
    """Create a standard set of indicators for analysis."""
    return {
        # Momentum
        'rsi': RSIIndicator(14),
        'macd': MACDIndicator(12, 26, 9),
        'stochastic': StochasticIndicator(14, 3),

        # Trend
        'sma_20': SMAIndicator(20),
        'sma_50': SMAIndicator(50),
        'sma_100': SMAIndicator(100),
        'sma_200': SMAIndicator(200),
        'ema_20': EMAIndicator(20),
        'ema_50': EMAIndicator(50),
        'ema_100': EMAIndicator(100),
        'ema_200': EMAIndicator(200),
        'adx': ADXIndicator(14),

        # Volatility
        'atr': ATRIndicator(14),
        'bollinger': BollingerBandsIndicator(20, 2),

        # Volume
        'obv': OBVIndicator(20),
        'rel_volume': RelativeVolumeIndicator(20),
        'vwap': VWAPIndicator(),
    }

__all__ = [
    "BaseIndicator",
    "RSIIndicator",
    "MACDIndicator",
    "StochasticIndicator",
    "SMAIndicator",
    "EMAIndicator",
    "ADXIndicator",
    "ParabolicSARIndicator",
    "ATRIndicator",
    "BollingerBandsIndicator",
    "KeltnerChannelsIndicator",
    "OBVIndicator",
    "RelativeVolumeIndicator",
    "VWAPIndicator",
    "VolumeProfileIndicator",
    "create_standard_indicators",
]
