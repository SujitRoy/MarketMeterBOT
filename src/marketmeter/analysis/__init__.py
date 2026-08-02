"""
analysis — convenient re-exports for the analysis package.

Phase 4 promotes the /analyzer.py module into a 5-file package with this
flat surface. All callers can keep doing:

    from marketmeter.analysis import (
        analyze_stock, run_batch_analysis,
        get_market_outlook, get_analysis_aggregate,
    )

The /analyzer.py shim at the project root re-exports these so legacy
imports (`from analyzer import X`) continue to work through Phase 6.
"""
from __future__ import annotations

from .indicators import (
    calc_sma, calc_ema, calc_rsi, calc_macd,
    calc_atr, calc_adx, calc_bollinger_bands, calc_obv,
)
from .scoring import _get_recommendation
from .analyzer import analyze_stock
from .batch import run_batch_analysis, get_market_outlook, get_analysis_aggregate

__all__ = [
    # indicators
    "calc_sma", "calc_ema", "calc_rsi", "calc_macd",
    "calc_atr", "calc_adx", "calc_bollinger_bands", "calc_obv",
    # scoring
    "_get_recommendation",
    # per-symbol
    "analyze_stock",
    # batch + outlook
    "run_batch_analysis", "get_market_outlook", "get_analysis_aggregate",
]