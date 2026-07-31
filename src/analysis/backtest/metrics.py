"""
Backtest Metrics
Performance metrics calculation for backtests.
"""
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class TradeMetrics:
    """Metrics for a single trade."""
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    days_held: int
    is_win: bool


@dataclass
class PortfolioMetrics:
    """Aggregated portfolio metrics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    avg_days_held: float
    best_trade: float
    worst_trade: float


def calculate_metrics(trades: list[dict[str, Any]], initial_capital: float = 1_000_000) -> PortfolioMetrics:
    """Calculate comprehensive portfolio metrics from trades."""
    if not trades:
        return PortfolioMetrics(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=0, avg_win=0, avg_loss=0, profit_factor=0,
            total_return=0, annualized_return=0, max_drawdown=0,
            sharpe_ratio=0, sortino_ratio=0, calmar_ratio=0,
            avg_days_held=0, best_trade=0, worst_trade=0
        )

    returns = np.array([t['return_pct'] for t in trades])
    days_held = np.array([t['days_held'] for t in trades])

    winning = returns[returns > 0]
    losing = returns[returns <= 0]

    total_trades = len(trades)
    winning_trades = len(winning)
    losing_trades = len(losing)
    win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0

    avg_win = np.mean(winning) if len(winning) > 0 else 0
    avg_loss = np.mean(losing) if len(losing) > 0 else 0
    profit_factor = abs(np.sum(winning) / np.sum(losing)) if np.sum(losing) != 0 else float('inf')

    # Total return
    total_return = np.prod([1 + r/100 for r in returns]) * 100 - 100

    # Annualized return
    total_days = np.sum(days_held)
    years = total_days / 252 if total_days > 0 else 1
    annualized_return = (1 + total_return/100) ** (1/years) * 100 - 100 if years > 0 else 0

    # Equity curve for drawdown
    equity = initial_capital
    equity_curve = [equity]
    for r in returns:
        equity *= (1 + r/100)
        equity_curve.append(equity)

    peak = initial_capital
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        max_dd = max(max_dd, dd)

    # Sharpe ratio
    daily_returns = returns / np.sqrt(days_held)  # Approximate
    sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0

    # Sortino ratio (downside deviation)
    downside_returns = daily_returns[daily_returns < 0]
    sortino = np.mean(daily_returns) / np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 and np.std(downside_returns) > 0 else 0

    # Calmar ratio
    calmar = annualized_return / max_dd if max_dd > 0 else 0

    return PortfolioMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        profit_factor=round(profit_factor, 2),
        total_return=round(total_return, 2),
        annualized_return=round(annualized_return, 2),
        max_drawdown=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        calmar_ratio=round(calmar, 2),
        avg_days_held=round(np.mean(days_held), 1),
        best_trade=round(np.max(returns), 2) if len(returns) > 0 else 0,
        worst_trade=round(np.min(returns), 2) if len(returns) > 0 else 0,
    )


def print_metrics(metrics: PortfolioMetrics) -> str:
    """Format metrics for display."""
    lines = [
        "═══════════════════════════════════",
        "        BACKTEST METRICS           ",
        "═══════════════════════════════════",
        f"Total Trades:      {metrics.total_trades}",
        f"Winning Trades:    {metrics.winning_trades}",
        f"Losing Trades:     {metrics.losing_trades}",
        f"Win Rate:          {metrics.win_rate:.2f}%",
        f"Avg Win:           {metrics.avg_win:.2f}%",
        f"Avg Loss:          {metrics.avg_loss:.2f}%",
        f"Profit Factor:     {metrics.profit_factor:.2f}",
        "──────────────────────────────────",
        f"Total Return:      {metrics.total_return:.2f}%",
        f"Annualized Return: {metrics.annualized_return:.2f}%",
        f"Max Drawdown:      {metrics.max_drawdown:.2f}%",
        "──────────────────────────────────",
        f"Sharpe Ratio:      {metrics.sharpe_ratio:.2f}",
        f"Sortino Ratio:     {metrics.sortino_ratio:.2f}",
        f"Calmar Ratio:      {metrics.calmar_ratio:.2f}",
        "──────────────────────────────────",
        f"Avg Days Held:     {metrics.avg_days_held:.1f}",
        f"Best Trade:        {metrics.best_trade:.2f}%",
        f"Worst Trade:       {metrics.worst_trade:.2f}%",
        "═══════════════════════════════════",
    ]
    return "\n".join(lines)
