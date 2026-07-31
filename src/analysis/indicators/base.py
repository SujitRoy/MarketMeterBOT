"""
Base Indicator Class
Abstract base for all technical indicators.
"""
from abc import ABC, abstractmethod

import pandas as pd


class BaseIndicator(ABC):
    """Abstract base class for technical indicators."""

    def __init__(self, name: str, **params):
        self.name = name
        self.params = params

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """Calculate indicator values from price data."""
        pass

    def get_latest(self, data: pd.DataFrame) -> float | None:
        """Get the latest indicator value."""
        series = self.calculate(data)
        if series.empty or pd.isna(series.iloc[-1]):
            return None
        return float(series.iloc[-1])

    def __repr__(self) -> str:
        params_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({params_str})"
