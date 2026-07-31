"""
Backtest Package
Backtesting engine, metrics, and fastbt adapter.
"""
from src.analysis.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    default_strategy,
    run_default_backtest,
)
from src.analysis.backtest.fastbt_adapter import FastBTAdapter
from src.analysis.backtest.metrics import PortfolioMetrics, calculate_metrics, print_metrics

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "default_strategy",
    "run_default_backtest",
    "calculate_metrics",
    "PortfolioMetrics",
    "print_metrics",
    "FastBTAdapter",
]
