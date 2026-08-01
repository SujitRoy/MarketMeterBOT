"""
sources/base — abstract Provider protocol for external market data sources.

Phase 3 introduces the Protocol that lets MarketMeter plug in multiple
data providers (NSE, TradingView, and future Zerodha/Upstox/Angel One)
without changing the call sites in analysis/ or reports/.

Why a Protocol and not an ABC:
- Structural typing: callers don't need to import or inherit from Provider
- No runtime registration overhead
- Test doubles (FakeProvider) work without subclassing
- Existing NSEProvider and TradingViewProvider satisfy the Protocol
  implicitly; their existing code didn't need a base class before, so we
  don't force one now.

The Protocol is intentionally minimal: just enough to plug into
the morning-report pipeline (EOD) and the search/intraday pipeline
(live snapshot). Provider-specific extras (TradingView's recommendation
rating, NSE's bhavcopy backfill) stay on the concrete subclasses.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class SymbolInfo:
    """Identity for a tradeable instrument on a specific exchange.

    `symbol` is the canonical ticker (e.g. "RELIANCE", "HDFCBANK").
    `exchange` is the venue code (e.g. "NSE", "BSE").
    `description` is the human-readable company name.
    """
    symbol: str
    exchange: str
    description: str = ""
    instrument_type: str = "stock"  # stock, etf, fund, ...


@dataclass(frozen=True)
class EodRow:
    """One day of end-of-day OHLCV + derived metrics for a single symbol.

    Mirrors the canonical bhavcopy schema. Providers map their native
    CSV/JSON onto this; consumers (analyzer, reports) read this only.
    """
    symbol: str
    trade_date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[int] = None
    turnover_lakh: Optional[float] = None
    delivery_pct: Optional[float] = None
    avg_price: Optional[float] = None


@dataclass(frozen=True)
class LiveSnapshot:
    """One snapshot of live/intraday data for a symbol.

    Providers can fill any subset; consumers must use `.get`/defaults.
    The base Protocol only requires `symbol` and a way to get the price.
    """
    symbol: str
    exchange: str
    timestamp: str           # ISO 8601
    price: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    change_pct: Optional[float] = None
    change_abs: Optional[float] = None
    vwap: Optional[float] = None
    extra: Optional[dict] = None  # provider-specific extras (RSI, MACD, ratings...)


@runtime_checkable
class Provider(Protocol):
    """The contract every market data provider must satisfy.

    Minimal so adding Zerodha/Upstox is a 30-minute job: implement these
    four methods, return the right dataclasses. Provider-specific extras
    (TradingView's full indicator set, NSE's bhavcopy archive) live on the
    concrete subclass and are reached through `isinstance` checks at the
    call site, not via the Protocol.

    The `name` property is used in logs and error messages so operator
    can tell which provider a request hit.
    """

    name: str

    def fetch_eod(self, trade_date: date) -> List[EodRow]:
        """End-of-day OHLCV for every tradable symbol on trade_date.

        Returns empty list on a closed/non-publish day. Raises on real
        transport failure.
        """
        ...

    def fetch_intraday(self, symbols: Optional[List[str]] = None) -> List[LiveSnapshot]:
        """Live/intraday snapshot for the given symbols (or all tracked
        symbols if None).

        Returns empty list on transport failure. Callers must treat empty
        as "no data right now", not as an error.
        """
        ...

    def lookup_symbol(self, text: str, limit: int = 8) -> List[SymbolInfo]:
        """Fuzzy/company-name resolution: 'reli' -> RELIANCE, etc.

        Empty list on transport failure or no match.
        """
        ...

    def health(self) -> bool:
        """Cheap liveness probe for `/status` and scheduler gates.

        Must NOT make a heavy authenticated request — keep it sub-100ms.
        """
        ...


__all__ = [
    "SymbolInfo",
    "EodRow",
    "LiveSnapshot",
    "Provider",
]