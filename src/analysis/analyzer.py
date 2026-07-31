"""
Main Analysis Engine
Orchestrates batch analysis of all stocks.
"""
import logging
from datetime import date
from typing import Any

import pandas as pd

from src.analysis.scorer import CompositeScorer, score_stock
from src.core.config import (
    ANALYSIS_BATCH_SIZE,
    MIN_DATA_POINTS,
)
from src.database.repositories import (
    AnalysisRepository,
    BhavCopyReadRepository,
    SyncReadRepository,
)

logger = logging.getLogger(__name__)


class AnalysisEngine:
    """Main analysis engine for batch processing."""

    def __init__(self):
        self.scorer = CompositeScorer()
        self.bhavcopy_repo = BhavCopyReadRepository()
        self.analysis_repo = AnalysisRepository()
        self.sync_repo = SyncReadRepository()

    def run_batch_analysis(self, analysis_date: date | None = None) -> dict[str, Any]:
        """
        Run technical analysis on all stocks with sufficient history.
        Caches results in daily_analysis table.
        
        Returns summary dict.
        """
        if analysis_date is None:
            analysis_date = self.sync_repo.get_last_synced_date() or date.today()

        symbols = self.bhavcopy_repo.get_all_symbols(min_records=MIN_DATA_POINTS)
        total = len(symbols)
        logger.info("Starting batch analysis for %d symbols on %s...", total, analysis_date)

        all_results = []
        analyzed = 0
        skipped = 0
        saved = 0

        for i, symbol in enumerate(symbols, 1):
            if i % ANALYSIS_BATCH_SIZE == 0:
                logger.info("Analysis progress: %d/%d symbols (%d analyzed, %d skipped)",
                            i, total, analyzed, skipped)

            history = self.bhavcopy_repo.get_history(symbol, min_days=MIN_DATA_POINTS)
            if not history:
                skipped += 1
                continue

            df = pd.DataFrame(history)
            result = score_stock(df)

            if result.get('skip_reason'):
                skipped += 1
                continue

            # Add symbol and date to result
            result['symbol'] = symbol
            result['analysis_date'] = analysis_date.isoformat()

            all_results.append(result)
            analyzed += 1

            # Save in batches to limit memory
            if len(all_results) >= ANALYSIS_BATCH_SIZE:
                saved += self._save_batch(all_results)
                logger.info("Saved batch to DB (%d rows written so far)", saved)
                all_results.clear()

        # Save remaining
        if all_results:
            saved += self._save_batch(all_results)
            logger.info("Saved final batch of analysis results to DB")

        # Get recommendation counts from DB
        grouped = self.analysis_repo.get_analysis_by_recommendation(analysis_date)
        rec_counts = {k: len(v) for k, v in grouped.items()}

        summary = {
            'status': 'completed',
            'analysis_date': analysis_date.isoformat(),
            'total_symbols': total,
            'analyzed': analyzed,
            'skipped': skipped,
            'saved': saved,
            'recommendation_counts': rec_counts,
            'message': (
                f"Analysis complete: {analyzed} stocks analyzed, {skipped} skipped. "
                f"BUY: {rec_counts.get('STRONG_BUY', 0) + rec_counts.get('BUY', 0)}, "
                f"ACCUMULATE: {rec_counts.get('ACCUMULATE', 0)}, "
                f"WATCH: {rec_counts.get('WATCH', 0)}, "
                f"CAUTION/AVOID: {rec_counts.get('CAUTION', 0) + rec_counts.get('AVOID', 0)}"
            ),
        }

        logger.info(summary['message'])
        return summary

    def _save_batch(self, results: list[dict[str, Any]]) -> int:
        """Save a batch of analysis results."""
        from src.database.models import DailyAnalysis

        analysis_rows = []
        for r in results:
            # Convert to DailyAnalysis
            analysis = DailyAnalysis(
                symbol=r['symbol'],
                analysis_date=date.fromisoformat(r['analysis_date']),
                close=r.get('indicators', {}).get('close'),
                volume=r.get('indicators', {}).get('volume'),
                rsi_14=r.get('indicators', {}).get('rsi'),
                adx_14=r.get('indicators', {}).get('adx'),
                macd_line=r.get('indicators', {}).get('macd', {}).get('macd') if isinstance(r.get('indicators', {}).get('macd'), dict) else None,
                signal_line=r.get('indicators', {}).get('macd', {}).get('signal') if isinstance(r.get('indicators', {}).get('macd'), dict) else None,
                macd_hist=r.get('indicators', {}).get('macd', {}).get('histogram') if isinstance(r.get('indicators', {}).get('macd'), dict) else None,
                sma_20=r.get('indicators', {}).get('sma_20'),
                sma_50=r.get('indicators', {}).get('sma_50'),
                sma_100=r.get('indicators', {}).get('sma_100'),
                sma_200=r.get('indicators', {}).get('sma_200'),
                ema_20=r.get('indicators', {}).get('ema_20'),
                ema_50=r.get('indicators', {}).get('ema_50'),
                ema_100=r.get('indicators', {}).get('ema_100'),
                ema_200=r.get('indicators', {}).get('ema_200'),
                atr_14=r.get('indicators', {}).get('atr'),
                bb_upper=r.get('indicators', {}).get('bollinger', {}).get('upper') if isinstance(r.get('indicators', {}).get('bollinger'), dict) else None,
                bb_lower=r.get('indicators', {}).get('bollinger', {}).get('lower') if isinstance(r.get('indicators', {}).get('bollinger'), dict) else None,
                rel_volume=r.get('indicators', {}).get('rel_volume'),
                obv_trend=r.get('indicators', {}).get('obv'),
                avg_price=r.get('indicators', {}).get('avg_price'),
                composite_score=r.get('composite_score'),
                recommendation=r.get('recommendation'),
            )
            analysis_rows.append(analysis)

        return self.analysis_repo.save_batch(analysis_rows)

    def get_market_outlook(self, analysis_date: date | None = None) -> dict[str, Any]:
        """Generate market-level outlook from analysis cache."""
        if analysis_date is None:
            analysis_date = self.sync_repo.get_last_synced_date() or date.today()

        results = self.analysis_repo.get_latest_analysis(analysis_date)
        if not results:
            return {
                'outlook': 'N/A',
                'bullish_pct': 0,
                'bearish_pct': 0,
                'avg_rsi': None,
                'avg_adx': None,
                'total_stocks': 0,
            }

        df = pd.DataFrame(results)
        total = len(df)

        bullish = len(df[df['recommendation'].isin(['STRONG_BUY', 'BUY', 'ACCUMULATE'])])
        bearish = len(df[df['recommendation'].isin(['CAUTION', 'AVOID'])])

        bullish_pct = round(bullish / total * 100, 1) if total > 0 else 0
        bearish_pct = round(bearish / total * 100, 1) if total > 0 else 0

        avg_rsi = round(df['rsi_14'].mean(), 1) if 'rsi_14' in df.columns and df['rsi_14'].notna().any() else None
        avg_adx = round(df['adx_14'].mean(), 1) if 'adx_14' in df.columns and df['adx_14'].notna().any() else None

        if bullish_pct > 60:
            outlook = 'Bullish 📈'
        elif bullish_pct > 40:
            outlook = 'Neutral ↔️'
        elif bearish_pct > 50:
            outlook = 'Bearish 📉'
        else:
            outlook = 'Mixed 🔀'

        return {
            'outlook': outlook,
            'bullish_pct': bullish_pct,
            'bearish_pct': bearish_pct,
            'neutral_pct': round(100 - bullish_pct - bearish_pct, 1),
            'avg_rsi': avg_rsi,
            'avg_adx': avg_adx,
            'total_stocks': total,
        }

    def get_analysis_aggregate(self, analysis_date: date | None = None) -> tuple[dict[str, list[dict]], dict[str, Any]]:
        """
        Single-pass: read the analysis rows ONCE and return (grouped, outlook).
        """
        if analysis_date is None:
            analysis_date = self.sync_repo.get_last_synced_date() or date.today()

        results = self.analysis_repo.get_latest_analysis(analysis_date)

        grouped = {
            "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
            "WATCH": [], "CAUTION": [], "AVOID": []
        }
        for r in results:
            rec = r.get('recommendation', 'AVOID')
            if rec in grouped:
                grouped[rec].append(r)

        if not results:
            outlook = {
                'outlook': 'N/A', 'bullish_pct': 0, 'bearish_pct': 0,
                'avg_rsi': None, 'avg_adx': None, 'total_stocks': 0,
            }
            return grouped, outlook

        total = len(results)
        bullish = sum(len(grouped[k]) for k in ('STRONG_BUY', 'BUY', 'ACCUMULATE'))
        bearish = sum(len(grouped[k]) for k in ('CAUTION', 'AVOID'))
        bullish_pct = round(bullish / total * 100, 1) if total > 0 else 0
        bearish_pct = round(bearish / total * 100, 1) if total > 0 else 0

        rsi_vals = [r['rsi_14'] for r in results if r.get('rsi_14') is not None]
        adx_vals = [r['adx_14'] for r in results if r.get('adx_14') is not None]
        avg_rsi = round(sum(rsi_vals) / len(rsi_vals), 1) if rsi_vals else None
        avg_adx = round(sum(adx_vals) / len(adx_vals), 1) if adx_vals else None

        if bullish_pct > 60:
            outlook_lbl = 'Bullish 📈'
        elif bullish_pct > 40:
            outlook_lbl = 'Neutral ↔️'
        elif bearish_pct > 50:
            outlook_lbl = 'Bearish 📉'
        else:
            outlook_lbl = 'Mixed 🔀'

        outlook = {
            'outlook': outlook_lbl,
            'bullish_pct': bullish_pct,
            'bearish_pct': bearish_pct,
            'neutral_pct': round(100 - bullish_pct - bearish_pct, 1),
            'avg_rsi': avg_rsi,
            'avg_adx': avg_adx,
            'total_stocks': total,
        }
        return grouped, outlook


def run_batch_analysis(analysis_date: date | None = None) -> dict[str, Any]:
    """Convenience function for backward compatibility."""
    engine = AnalysisEngine()
    return engine.run_batch_analysis(analysis_date)


def get_market_outlook(analysis_date: date | None = None) -> dict[str, Any]:
    """Convenience function for backward compatibility."""
    engine = AnalysisEngine()
    return engine.get_market_outlook(analysis_date)


def get_analysis_aggregate(analysis_date: date | None = None) -> tuple[dict[str, list[dict]], dict[str, Any]]:
    """Convenience function for backward compatibility."""
    engine = AnalysisEngine()
    return engine.get_analysis_aggregate(analysis_date)
