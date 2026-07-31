"""
Analysis Package
Technical analysis engine, indicators, scorer, and backtesting.
"""
from src.analysis.analyzer import (
    AnalysisEngine,
    get_analysis_aggregate,
    get_market_outlook,
    run_batch_analysis,
)
from src.analysis.backtest import (
    BacktestEngine,
    BacktestResult,
    PortfolioMetrics,
    calculate_metrics,
    default_strategy,
    print_metrics,
    run_default_backtest,
)
from src.analysis.indicators import (
    ADXIndicator,
    ATRIndicator,
    BaseIndicator,
    BollingerBandsIndicator,
    EMAIndicator,
    KeltnerChannelsIndicator,
    MACDIndicator,
    OBVIndicator,
    ParabolicSARIndicator,
    RelativeVolumeIndicator,
    RSIIndicator,
    SMAIndicator,
    StochasticIndicator,
    VolumeProfileIndicator,
    VWAPIndicator,
    create_standard_indicators,
)
from src.analysis.scorer import CompositeScorer, score_stock

__all__ = [
    # Indicators
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

    # Scorer
    "CompositeScorer",
    "score_stock",

    # Analyzer
    "AnalysisEngine",
    "run_batch_analysis",
    "get_market_outlook",
    "get_analysis_aggregate",

    # Backtest
    "BacktestEngine",
    "BacktestResult",
    "default_strategy",
    "run_default_backtest",
    "calculate_metrics",
    "PortfolioMetrics",
    "print_metrics",
]
