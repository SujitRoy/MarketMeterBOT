"""
Composite Scorer
Calculates composite scores and generates recommendations.
"""
import logging
from typing import Any

import pandas as pd

from src.analysis.indicators import create_standard_indicators
from src.core.config import (
    MIN_DATA_POINTS,
    MIN_PRICE,
    MIN_VOLUME,
    REC_THRESHOLDS,
    SCORE_WEIGHTS,
)
from src.core.constants import Recommendation

logger = logging.getLogger(__name__)


class CompositeScorer:
    """Calculates composite technical scores and recommendations."""

    def __init__(self):
        self.indicators = create_standard_indicators()

    def calculate_score(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate composite score for a stock.
        
        Returns dict with score, recommendation, and component breakdown.
        """
        if len(data) < MIN_DATA_POINTS:
            return self._empty_result("Insufficient data")

        # Get latest values
        close = data['close'].iloc[-1]
        volume = int(data['volume'].iloc[-1])

        if close < MIN_PRICE or volume < MIN_VOLUME:
            return self._empty_result("Price/volume filter")

        # Calculate all indicators
        ind_results = {}
        for name, indicator in self.indicators.items():
            try:
                if hasattr(indicator, 'get_latest'):
                    ind_results[name] = indicator.get_latest(data)
                else:
                    series = indicator.calculate(data)
                    ind_results[name] = float(series.iloc[-1]) if not pd.isna(series.iloc[-1]) else None
            except Exception as e:
                logger.warning("Indicator %s failed: %s", name, e)
                ind_results[name] = None

        # Calculate component scores
        components = self._calculate_components(ind_results)

        # Weighted composite score
        composite_score = sum(
            components[k] * SCORE_WEIGHTS.get(k, 0)
            for k in SCORE_WEIGHTS
        )
        composite_score = int(round(composite_score))

        # Determine recommendation
        recommendation = self._get_recommendation(composite_score, ind_results)

        # Add metadata
        rsi = ind_results.get('rsi')
        adx = ind_results.get('adx')

        return {
            'composite_score': composite_score,
            'recommendation': recommendation,
            'components': components,
            'indicators': ind_results,
            'trend_strength': self._get_trend_strength(adx),
            'momentum': self._get_momentum_label(rsi),
            'signals': self._get_signals(ind_results),
        }

    def _calculate_components(self, indicators: dict) -> dict[str, float]:
        """Calculate individual component scores (0-100 each)."""
        components = {}

        # Trend component (25% weight)
        trend_score = 0
        if indicators.get('adx'):
            adx = indicators['adx']
            if adx > 50: trend_score = 100
            elif adx > 30: trend_score = 75
            elif adx > 20: trend_score = 50
            elif adx > 10: trend_score = 25

        # Add SMA/EMA alignment
        above_sma20 = indicators.get('close', 0) > indicators.get('sma_20', float('inf'))
        above_sma50 = indicators.get('close', 0) > indicators.get('sma_50', float('inf'))
        above_sma200 = indicators.get('close', 0) > indicators.get('sma_200', float('inf'))

        if above_sma20: trend_score += 10
        if above_sma50: trend_score += 10
        if above_sma200: trend_score += 5

        components['trend'] = min(trend_score, 100)

        # Momentum component (25% weight)
        momentum_score = 0
        rsi = indicators.get('rsi')
        if rsi is not None:
            if 60 <= rsi <= 75: momentum_score = 100
            elif rsi > 75: momentum_score = 75
            elif rsi > 50: momentum_score = 50
            elif rsi > 40: momentum_score = 25

        # MACD
        macd = indicators.get('macd')
        if macd and isinstance(macd, dict):
            if macd.get('histogram', 0) > 0:
                momentum_score += 15
            if macd.get('macd', 0) > macd.get('signal', 0):
                momentum_score += 10

        components['momentum'] = min(momentum_score, 100)

        # Volatility component (15% weight)
        volatility_score = 50  # Neutral base
        atr = indicators.get('atr')
        bb = indicators.get('bollinger')

        if atr and indicators.get('close'):
            # Normalize ATR as % of price
            atr_pct = (atr / indicators['close']) * 100
            if 1 < atr_pct < 3:  # Healthy volatility
                volatility_score = 75
            elif atr_pct >= 3:  # High volatility
                volatility_score = 50
            else:  # Low volatility
                volatility_score = 60

        if bb and isinstance(bb, dict):
            close = indicators.get('close')
            if close and bb.get('upper') and bb.get('lower'):
                # Position within bands
                pos = (close - bb['lower']) / (bb['upper'] - bb['lower'])
                if 0.3 <= pos <= 0.7:  # Middle of bands
                    volatility_score = max(volatility_score, 70)

        components['volatility'] = min(volatility_score, 100)

        # Volume component (20% weight)
        volume_score = 0
        rel_vol = indicators.get('rel_volume')
        if rel_vol is not None:
            if rel_vol > 3: volume_score = 100
            elif rel_vol > 2: volume_score = 80
            elif rel_vol > 1.5: volume_score = 60
            elif rel_vol > 1: volume_score = 40
            else: volume_score = 20

        # OBV trend
        obv = indicators.get('obv')
        if obv and obv > 0:
            volume_score += 10

        components['volume'] = min(volume_score, 100)

        # Structure component (15% weight)
        structure_score = 50
        if above_sma20 and above_sma50 and above_sma200:
            structure_score = 100
        elif above_sma20 and above_sma50:
            structure_score = 80
        elif above_sma20:
            structure_score = 60

        # Price vs SMA20 momentum
        price_vs_sma20 = indicators.get('price_vs_sma20')
        if price_vs_sma20 is not None:
            if price_vs_sma20 > 5: structure_score += 10
            elif price_vs_sma20 > 0: structure_score += 5

        components['structure'] = min(structure_score, 100)

        return components

    def _get_recommendation(self, score: int, indicators: dict) -> str:
        """Determine recommendation from composite score."""
        rsi = indicators.get('rsi') or 50
        adx = indicators.get('adx') or 20

        # Override for overbought
        if rsi > 80 and score < 70:
            return Recommendation.CAUTION

        for rec in [Recommendation.STRONG_BUY, Recommendation.BUY,
                    Recommendation.ACCUMULATE, Recommendation.WATCH,
                    Recommendation.CAUTION, Recommendation.AVOID]:
            threshold = REC_THRESHOLDS.get(rec, 0)
            if score >= threshold:
                return rec

        return Recommendation.AVOID

    def _get_trend_strength(self, adx: float | None) -> str:
        """Get trend strength label from ADX."""
        if adx is None:
            return 'N/A'
        if adx > 50:
            return 'Very Strong'
        elif adx > 30:
            return 'Strong'
        elif adx > 20:
            return 'Moderate'
        return 'Weak'

    def _get_momentum_label(self, rsi: float | None) -> str:
        """Get momentum label from RSI."""
        if rsi is None:
            return 'N/A'
        if rsi > 70:
            return 'Overbought'
        elif rsi > 60:
            return 'Bullish'
        elif rsi > 40:
            return 'Neutral'
        elif rsi > 30:
            return 'Bearish'
        return 'Oversold'

    def _get_signals(self, indicators: dict) -> dict[str, bool]:
        """Get boolean trading signals."""
        return {
            'above_sma20': indicators.get('close', 0) > indicators.get('sma_20', float('inf')),
            'above_sma50': indicators.get('close', 0) > indicators.get('sma_50', float('inf')),
            'above_sma200': indicators.get('close', 0) > indicators.get('sma_200', float('inf')),
            'macd_bullish': (
                indicators.get('macd', {}).get('macd', 0) >
                indicators.get('macd', {}).get('signal', 0)
            ) if isinstance(indicators.get('macd'), dict) else False,
            'macd_hist_positive': (
                indicators.get('macd', {}).get('histogram', 0) > 0
            ) if isinstance(indicators.get('macd'), dict) else False,
            'obv_positive': indicators.get('obv', 0) > 0,
            'rsi_bullish': 50 < (indicators.get('rsi') or 0) < 75,
        }

    def _empty_result(self, reason: str) -> dict[str, Any]:
        return {
            'composite_score': 0,
            'recommendation': Recommendation.AVOID,
            'components': {},
            'indicators': {},
            'trend_strength': 'N/A',
            'momentum': 'N/A',
            'signals': {},
            'skip_reason': reason,
        }


def score_stock(data: pd.DataFrame) -> dict[str, Any]:
    """Convenience function to score a single stock."""
    scorer = CompositeScorer()
    return scorer.calculate_score(data)
