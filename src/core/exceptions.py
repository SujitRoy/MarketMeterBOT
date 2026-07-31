"""
MarketMeter Custom Exceptions
Centralized exception hierarchy for better error handling.
"""


class MarketMeterError(Exception):
    """Base exception for all MarketMeter errors."""
    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.context = context or {}


class ConfigurationError(MarketMeterError):
    """Raised when configuration is invalid or missing."""
    pass


class DataFetchError(MarketMeterError):
    """Raised when data fetching fails."""
    def __init__(self, message: str, source: str = None, status_code: int = None, context: dict = None):
        super().__init__(message, context)
        self.source = source
        self.status_code = status_code


class DataParseError(MarketMeterError):
    """Raised when data parsing fails."""
    pass


class DatabaseError(MarketMeterError):
    """Raised when database operations fail."""
    pass


class AnalysisError(MarketMeterError):
    """Raised when technical analysis fails."""
    pass


class ReportGenerationError(MarketMeterError):
    """Raised when report generation fails."""
    pass


class ReportNotFoundError(ReportGenerationError):
    """Raised when a cached report is not found."""
    pass


class SyncError(MarketMeterError):
    """Raised when sync operations fail."""
    pass


class IntradayError(MarketMeterError):
    """Raised when intraday operations fail."""
    pass


class SchedulerError(MarketMeterError):
    """Raised when scheduler operations fail."""
    pass


class BotError(MarketMeterError):
    """Raised when bot operations fail."""
    pass


class ValidationError(MarketMeterError):
    """Raised when input validation fails."""
    pass


class CacheError(MarketMeterError):
    """Raised when cache operations fail."""
    pass


class NotTradingDayError(MarketMeterError):
    """Raised when attempting operations on non-trading days."""
    pass


class InsufficientDataError(AnalysisError):
    """Raised when there's insufficient data for analysis."""
    pass


class RateLimitError(BotError):
    """Raised when Telegram rate limits are hit."""
    pass


class SessionExpiredError(DataFetchError):
    """Raised when TradingView session expires."""
    pass


class MigrationError(DatabaseError):
    """Raised when database migration fails."""
    pass


class BacktestError(MarketMeterError):
    """Raised when backtesting fails."""
    pass
