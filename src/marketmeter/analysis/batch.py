"""
analysis/batch — memory-bounded batch analyzer + outlook aggregator.

Phase 4 split: run_batch_analysis + get_market_outlook + get_analysis_aggregate
from /analyzer.py. These are the "fan out across all symbols" entry points.

batch.py owns:
- run_batch_analysis: walk every tradable symbol, call analyze_stock on each,
  save the results to daily_analysis.
- get_market_outlook: roll up the latest daily_analysis into a market-wide
  summary (bullish / bearish / neutral %, avg RSI, avg ADX).
- get_analysis_aggregate: single-pass equivalent of the (grouped, outlook)
  pair that the morning report used to compute twice (this is the BUG-C fix).
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from marketmeter.core.config import (
    MIN_DATA_POINTS, ANALYSIS_BATCH_SIZE,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import (
    get_all_symbols, get_stock_history, save_daily_analysis,
    get_latest_trade_date, get_latest_analysis,
)
from marketmeter.analysis.analyzer import analyze_stock

logger = get_logger(__name__)


def run_batch_analysis(analysis_date: Optional[date] = None) -> dict:
    """
    Run analysis for all tradable symbols in memory-bounded batches.

    Returns a summary dict suitable for cron-job result reporting.
    """
    if analysis_date is None:
        analysis_date = get_latest_trade_date()
        if analysis_date is None:
            logger.warning("No trade date available; cannot run analysis")
            return {"status": "no_data", "message": "No trade data available", "analyzed": 0, "recommendations": {}}

    logger.info("Running batch analysis for %s", analysis_date)
    symbols = get_all_symbols(min_records=MIN_DATA_POINTS)
    logger.info("Found %d symbols to analyze", len(symbols))

    results = []
    for i, symbol in enumerate(symbols, 1):
        try:
            history = get_stock_history(symbol, min_days=MIN_DATA_POINTS)
            result = analyze_stock(history, symbol)
            if result is not None:
                result['analysis_date'] = analysis_date
                results.append(result)
        except Exception as e:
            logger.warning("Failed to analyze %s: %s", symbol, e)
            continue

        if i % ANALYSIS_BATCH_SIZE == 0:
            logger.info("Processed %d/%d symbols", i, len(symbols))

    # Save to DB
    saved = save_daily_analysis(results)
    logger.info("Saved %d analysis rows", saved)

    # Categorize
    recommendations = {}
    for r in results:
        rec = r.get('recommendation', 'AVOID')
        recommendations[rec] = recommendations.get(rec, 0) + 1

    return {
        "status": "completed",
        "message": f"Analyzed {len(results)} stocks, saved {saved}",
        "analyzed": len(results),
        "recommendations": recommendations,
    }


def get_market_outlook(analysis_date: Optional[date] = None) -> dict:
    """
    Aggregate the latest daily_analysis into a market-wide outlook.

    Returns:
        {outlook, bullish_pct, bearish_pct, neutral_pct,
         avg_rsi, avg_adx, total_stocks}

    The "outlook" string is BULLISH when bullish_pct > 60, BEARISH when
    bearish_pct >= 40, NEUTRAL otherwise.
    """
    rows = get_latest_analysis(analysis_date)
    if not rows:
        return {
            "outlook": "NO DATA",
            "bullish_pct": 0,
            "bearish_pct": 0,
            "neutral_pct": 0,
            "avg_rsi": None,
            "avg_adx": None,
            "total_stocks": 0,
        }

    total = len(rows)
    bullish = sum(1 for r in rows if r.get('recommendation', '') in ('STRONG_BUY', 'BUY', 'ACCUMULATE'))
    bearish = sum(1 for r in rows if r.get('recommendation', '') in ('AVOID', 'CAUTION'))
    neutral = total - bullish - bearish

    bullish_pct = round(bullish * 100 / total, 1)
    bearish_pct = round(bearish * 100 / total, 1)
    neutral_pct = round(neutral * 100 / total, 1)

    rsis = [r['rsi_14'] for r in rows if r.get('rsi_14') is not None]
    adxs = [r['adx_14'] for r in rows if r.get('adx_14') is not None]
    avg_rsi = round(sum(rsis) / len(rsis), 1) if rsis else None
    avg_adx = round(sum(adxs) / len(adxs), 1) if adxs else None

    if bullish_pct > 60:
        outlook = "🟢 BULLISH"
    elif bearish_pct >= 40:
        outlook = "🔴 BEARISH"
    else:
        outlook = "🟡 NEUTRAL"

    return {
        "outlook": outlook,
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "neutral_pct": neutral_pct,
        "avg_rsi": avg_rsi,
        "avg_adx": avg_adx,
        "total_stocks": total,
    }


def get_analysis_aggregate(analysis_date: Optional[date] = None) -> Tuple[dict, dict]:
    """
    Single DB read returns (grouped_by_recommendation, market_outlook).

    The morning report needs both. Previously it called get_latest_analysis
    twice (once via get_analysis_by_recommendation, once via get_market_outlook),
    each independently re-querying every row of daily_analysis. This wrapper
    reads the rows once and computes both in memory.
    """
    rows = get_latest_analysis(analysis_date)
    grouped = {
        "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
        "WATCH": [], "CAUTION": [], "AVOID": [],
    }
    for r in rows:
        rec = r.get('recommendation', 'AVOID')
        if rec in grouped:
            grouped[rec].append(r)

    if not rows:
        return grouped, {
            "outlook": "NO DATA",
            "bullish_pct": 0, "bearish_pct": 0, "neutral_pct": 0,
            "avg_rsi": None, "avg_adx": None, "total_stocks": 0,
        }

    total = len(rows)
    bullish = sum(1 for r in rows if r.get('recommendation', '') in ('STRONG_BUY', 'BUY', 'ACCUMULATE'))
    bearish = sum(1 for r in rows if r.get('recommendation', '') in ('AVOID', 'CAUTION'))
    neutral = total - bullish - bearish

    bullish_pct = round(bullish * 100 / total, 1)
    bearish_pct = round(bearish * 100 / total, 1)
    neutral_pct = round(neutral * 100 / total, 1)

    rsis = [r['rsi_14'] for r in rows if r.get('rsi_14') is not None]
    adxs = [r['adx_14'] for r in rows if r.get('adx_14') is not None]
    avg_rsi = round(sum(rsis) / len(rsis), 1) if rsis else None
    avg_adx = round(sum(adxs) / len(adxs), 1) if adxs else None

    if bullish_pct > 60:
        outlook_label = "🟢 BULLISH"
    elif bearish_pct >= 40:
        outlook_label = "🔴 BEARISH"
    else:
        outlook_label = "🟡 NEUTRAL"

    outlook = {
        "outlook": outlook_label,
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "neutral_pct": neutral_pct,
        "avg_rsi": avg_rsi,
        "avg_adx": avg_adx,
        "total_stocks": total,
    }
    return grouped, outlook


__all__ = ["run_batch_analysis", "get_market_outlook", "get_analysis_aggregate"]