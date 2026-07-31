"""
Database Models (Dataclasses)
Type-safe representations of database records.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class BhavCopyRow:
    """Single row of NSE BhavCopy data."""
    symbol: str
    trade_date: date
    series: str = "EQ"
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    last: float | None = None
    prevclose: float | None = None
    volume: int | None = None
    value_lakh: float | None = None
    del_pct: float | None = None
    avg_price: float | None = None
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "BhavCopyRow":
        """Create from dictionary (e.g., CSV row)."""
        # Handle date parsing
        trade_date = data.get("trade_date") or data.get("DATE")
        if isinstance(trade_date, str):
            trade_date = date.fromisoformat(trade_date)

        return cls(
            symbol=data.get("SYMBOL") or data.get("symbol"),
            trade_date=trade_date,
            series=data.get("SERIES", "EQ"),
            open=_to_float(data.get("OPEN")),
            high=_to_float(data.get("HIGH")),
            low=_to_float(data.get("LOW")),
            close=_to_float(data.get("CLOSE")),
            last=_to_float(data.get("LAST")),
            prevclose=_to_float(data.get("PREVCLOSE")),
            volume=_to_int(data.get("VOLUME")),
            value_lakh=_to_float(data.get("VALUE_LAKH")),
            del_pct=_to_float(data.get("DEL_PCT")),
            avg_price=_to_float(data.get("AVG_PRICE")),
        )

    def to_db_tuple(self) -> tuple:
        """Convert to tuple for database insertion."""
        return (
            self.symbol, self.series, self.open, self.high, self.low,
            self.close, self.last, self.prevclose, self.volume,
            self.value_lakh, self.del_pct, self.trade_date.isoformat(),
            self.avg_price,
        )


@dataclass
class DailyAnalysis:
    """Pre-computed daily technical analysis for a symbol."""
    symbol: str
    analysis_date: date
    close: float | None = None
    volume: int | None = None
    rsi_14: float | None = None
    adx_14: float | None = None
    macd_line: float | None = None
    signal_line: float | None = None
    macd_hist: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_100: float | None = None
    sma_200: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    ema_100: float | None = None
    ema_200: float | None = None
    atr_14: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    rel_volume: float | None = None
    obv_trend: float | None = None
    avg_price: float | None = None
    composite_score: int | None = None
    recommendation: str | None = None
    created_at: datetime | None = None

    def to_db_tuple(self) -> tuple:
        """Convert to tuple for database insertion."""
        return (
            self.symbol, self.analysis_date.isoformat(), self.close, self.volume,
            self.rsi_14, self.adx_14, self.macd_line, self.signal_line, self.macd_hist,
            self.sma_20, self.sma_50, self.sma_100, self.sma_200,
            self.ema_20, self.ema_50, self.ema_100, self.ema_200,
            self.atr_14, self.bb_upper, self.bb_lower,
            self.rel_volume, self.obv_trend, self.avg_price,
            self.composite_score, self.recommendation,
        )

    @classmethod
    def from_row(cls, row: dict) -> "DailyAnalysis":
        """Create from database row."""
        return cls(
            symbol=row["symbol"],
            analysis_date=date.fromisoformat(row["analysis_date"]),
            close=row.get("close"),
            volume=row.get("volume"),
            rsi_14=row.get("rsi_14"),
            adx_14=row.get("adx_14"),
            macd_line=row.get("macd_line"),
            signal_line=row.get("signal_line"),
            macd_hist=row.get("macd_hist"),
            sma_20=row.get("sma_20"),
            sma_50=row.get("sma_50"),
            sma_100=row.get("sma_100"),
            sma_200=row.get("sma_200"),
            ema_20=row.get("ema_20"),
            ema_50=row.get("ema_50"),
            ema_100=row.get("ema_100"),
            ema_200=row.get("ema_200"),
            atr_14=row.get("atr_14"),
            bb_upper=row.get("bb_upper"),
            bb_lower=row.get("bb_lower"),
            rel_volume=row.get("rel_volume"),
            obv_trend=row.get("obv_trend"),
            avg_price=row.get("avg_price"),
            composite_score=row.get("composite_score"),
            recommendation=row.get("recommendation"),
        )


@dataclass
class SyncLogEntry:
    """Sync operation log entry."""
    trade_date: date
    status: str  # success, failed, holiday, skipped, not_available
    records_count: int = 0
    error_message: str | None = None
    synced_at: datetime | None = None
    id: int | None = None


@dataclass
class Subscriber:
    """Telegram subscriber."""
    chat_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    active: bool = True
    receive_reports: bool = True
    subscribed_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict) -> "Subscriber":
        return cls(
            chat_id=row["chat_id"],
            username=row.get("username"),
            first_name=row.get("first_name"),
            last_name=row.get("last_name"),
            active=bool(row.get("active", 1)),
            receive_reports=bool(row.get("receive_reports", 1)),
            subscribed_at=datetime.fromisoformat(row["subscribed_at"]) if row.get("subscribed_at") else None,
        )


@dataclass
class IntradayCandle:
    """5-minute intraday candle."""
    symbol: str
    candle_ts: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    vwap: float | None = None
    id: int | None = None
    created_at: datetime | None = None

    def to_db_tuple(self) -> tuple:
        return (
            self.symbol, self.candle_ts.isoformat(), self.open, self.high,
            self.low, self.close, self.volume, self.vwap,
        )


@dataclass
class IntradayAlert:
    """Intraday alert log."""
    symbol: str
    alert_type: str  # BREAKOUT, VOLUME_SPIKE, RSI_EXTREME, VWAP_RECLAIM
    candle_ts: datetime
    price: float
    details: dict = field(default_factory=dict)
    id: int | None = None
    created_at: datetime | None = None

    def to_db_tuple(self) -> tuple:
        return (
            self.symbol, self.alert_type, self.candle_ts.isoformat(),
            self.price, json.dumps(self.details),
        )


@dataclass
class TrackedSymbol:
    """Symbol tracked for intraday monitoring."""
    symbol: str
    added_by: str = "MANUAL"  # AUTO_REPORT, MANUAL
    active: bool = True
    added_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict) -> "TrackedSymbol":
        return cls(
            symbol=row["symbol"],
            added_by=row.get("added_by", "MANUAL"),
            active=bool(row.get("active", 1)),
            added_at=datetime.fromisoformat(row["added_at"]) if row.get("added_at") else None,
        )


@dataclass
class ReportCacheEntry:
    """Cached rendered report."""
    kind: str
    analysis_date: date
    version: int
    payload: str
    built_at: datetime | None = None


@dataclass
class DBStats:
    """Database statistics."""
    total_records: int
    unique_symbols: int
    date_from: str | None
    date_to: str | None
    active_subscribers: int


# Helper functions
def _to_float(value: Any) -> float | None:
    """Safely convert to float."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int | None:
    """Safely convert to int."""
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None
