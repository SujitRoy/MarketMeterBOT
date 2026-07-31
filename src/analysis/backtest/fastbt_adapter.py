"""
FastBT Adapter
Integration with fastbt backtesting library (if available).
"""
import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# Try to import fastbt
try:
    import fastbt
    FASTBT_AVAILABLE = True
except ImportError:
    FASTBT_AVAILABLE = False
    logger.info("fastbt not available. Install with: pip install fastbt")


class FastBTAdapter:
    """Adapter for fastbt backtesting library."""

    def __init__(self):
        if not FASTBT_AVAILABLE:
            raise ImportError("fastbt not installed. Install with: pip install fastbt")

    def run_backtest(
        self,
        strategy_class,
        data: dict[str, Any],
        start_date: date,
        end_date: date,
        **kwargs
    ) -> dict[str, Any]:
        """
        Run a backtest using fastbt.
        
        Args:
            strategy_class: fastbt Strategy class
            data: Dictionary of symbol -> price DataFrame
            start_date: Backtest start date
            end_date: Backtest end date
        """
        # This would integrate with fastbt's API
        # Placeholder for future implementation
        raise NotImplementedError("FastBT integration pending")

    def convert_to_fastbt_format(self, df) -> Any:
        """Convert our DataFrame format to fastbt format."""
        # fastbt expects specific column names and index
        pass


def create_fastbt_strategy(strategy_name: str, **params):
    """Create a fastbt strategy class dynamically."""
    if not FASTBT_AVAILABLE:
        return None

    # This would create a fastbt strategy
    pass
