"""
Backtest Engine
Runs historical backtests of strategies.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.analyzer import AnalysisEngine
from src.core.config import MIN_DATA_POINTS
from src.database.repositories import BhavCopyReadRepository

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    strategy_name: str
    start_date: date
    end_date: date
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)


class BacktestEngine:
    """Runs backtests on historical data."""

    def __init__(self):
        self.analyzer = AnalysisEngine()
        self.bhavcopy_repo = BhavCopyReadRepository()

    def run_strategy_backtest(
        self,
        strategy_func: Callable[[pd.DataFrame], dict[str, Any]],
        symbols: list[str],
        start_date: date,
        end_date: date,
        initial_capital: float = 1_000_000,
    ) -> BacktestResult:
        """
        Run a backtest for a given strategy.
        
        Args:
            strategy_func: Function that takes price DataFrame and returns signal dict
            symbols: List of symbols to test
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital
        """
        logger.info("Running backtest for %d symbols from %s to %s",
                    len(symbols), start_date, end_date)

        all_trades = []
        equity = initial_capital
        equity_curve = [equity]
        peak_equity = equity

        for symbol in symbols:
            history = self.bhavcopy_repo.get_history(
                symbol,
                min_days=MIN_DATA_POINTS,
                window=None  # Full history
            )
            if not history:
                continue

            df = pd.DataFrame(history)
            df = df[(df['trade_date'] >= start_date.isoformat()) &
                    (df['trade_date'] <= end_date.isoformat())]

            if len(df) < 50:
                continue

            trades = self._simulate_trades(df, strategy_func, symbol)
            all_trades.extend(trades)

        # Calculate metrics
        if all_trades:
            returns = [t['return_pct'] for t in all_trades]
            winning = [r for r in returns if r > 0]
            losing = [r for r in returns if r <= 0]

            win_rate = len(winning) / len(returns) * 100 if returns else 0
            avg_return = np.mean(returns) if returns else 0
            total_return = np.prod([1 + r/100 for r in returns]) * 100 - 100 if returns else 0

            # Calculate drawdown
            equity_curve = [initial_capital]
            for r in returns:
                equity_curve.append(equity_curve[-1] * (1 + r/100))

            peak = initial_capital
            max_dd = 0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak * 100
                max_dd = max(max_dd, dd)

            # Sharpe ratio (simplified)
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            win_rate = avg_return = total_return = max_dd = sharpe = 0

        result = BacktestResult(
            strategy_name=strategy_func.__name__,
            start_date=start_date,
            end_date=end_date,
            total_trades=len(all_trades),
            winning_trades=len([t for t in all_trades if t['return_pct'] > 0]),
            losing_trades=len([t for t in all_trades if t['return_pct'] <= 0]),
            win_rate=round(win_rate, 2),
            avg_return=round(avg_return, 2),
            total_return=round(total_return, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            trades=all_trades,
            equity_curve=equity_curve,
        )

        logger.info("Backtest complete: %d trades, %.2f%% win rate, %.2f%% total return",
                    result.total_trades, result.win_rate, result.total_return)

        return result

    def _simulate_trades(
        self,
        df: pd.DataFrame,
        strategy_func: Callable,
        symbol: str
    ) -> list[dict[str, Any]]:
        """Simulate trades for a single symbol."""
        trades = []
        position = None

        for i in range(50, len(df)):  # Need 50 bars for indicators
            window = df.iloc[:i+1]
            signal = strategy_func(window)

            current_price = window['close'].iloc[-1]
            current_date = window['trade_date'].iloc[-1]

            # Check exit conditions
            if position:
                should_exit = signal.get('action') == 'sell' or \
                             signal.get('stop_loss') and current_price <= position['stop_loss'] or \
                             signal.get('take_profit') and current_price >= position['take_profit']

                if should_exit:
                    return_pct = (current_price - position['entry_price']) / position['entry_price'] * 100
                    trades.append({
                        'symbol': symbol,
                        'entry_date': position['entry_date'],
                        'exit_date': current_date,
                        'entry_price': position['entry_price'],
                        'exit_price': current_price,
                        'return_pct': round(return_pct, 2),
                        'days_held': i - position['entry_idx'],
                    })
                    position = None

            # Check entry conditions
            if not position and signal.get('action') == 'buy':
                position = {
                    'entry_price': current_price,
                    'entry_date': current_date,
                    'entry_idx': i,
                    'stop_loss': signal.get('stop_loss'),
                    'take_profit': signal.get('take_profit'),
                }

        return trades


def default_strategy(df: pd.DataFrame) -> dict[str, Any]:
    """Default strategy: buy when RSI < 30 and price > SMA200."""
    # This would use the CompositeScorer in real implementation
    from src.analysis.scorer import score_stock
    result = score_stock(df)

    signals = result.get('signals', {})
    indicators = result.get('indicators', {})

    if signals.get('rsi_bullish') and signals.get('above_sma200'):
        return {
            'action': 'buy',
            'stop_loss': indicators.get('close', 0) * 0.95,
            'take_profit': indicators.get('close', 0) * 1.15,
        }

    return {'action': 'hold'}


def run_default_backtest(
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> BacktestResult:
    """Run backtest with default strategy."""
    engine = BacktestEngine()
    return engine.run_strategy_backtest(default_strategy, symbols, start_date, end_date)
