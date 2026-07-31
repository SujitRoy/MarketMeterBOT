"""
TradingView Scanner Fetcher
Fetches live intraday data from TradingView Scanner API.
"""
import logging
from datetime import datetime, time
from typing import Any

import requests

from src.core.config import (
    DEFAULT_INTRADAY_SYMBOLS,
    MARKET_CLOSE_TIME,
    MARKET_OPEN_TIME,
    TRADINGVIEW_SESSION_ID,
)
from src.data.fetchers.base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)

# TradingView Scanner endpoint
TV_SCAN_URL = "https://scanner.tradingview.com/india/scan"
TV_HEADERS = {
    "content-type": "application/json",
    "accept": "text/plain, */*; q=0.01",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin": "https://www.tradingview.com",
    "referer": "https://www.tradingview.com/",
}


def build_query(symbols: list[str]) -> dict[str, Any]:
    """Build TradingView scanner query for given symbols using tickers."""
    tickers = [f"NSE:{s}" for s in symbols]
    return {
        "markets": ["india"],
        "symbols": {"tickers": tickers},
        "options": {"lang": "en"},
        "columns": [
            "name",
            "close", "open", "high", "low", "volume",
            "change", "change_abs", "change_from_open", "change_from_open_abs",
            "gap", "gap_percent", "VWAP",
            "RSI", "MACD.macd", "MACD.signal",
            "EMA9", "EMA21", "EMA50", "EMA200",
            "SMA20", "SMA50", "SMA200",
            "relative_volume_10d_calc",
            "market_cap_basic", "price_earnings_ttm",
            "earnings_per_share_diluted_ttm", "dividends_yield_current",
            "Recommend.All", "Recommend.MA", "Recommend.Other",
            "sector", "industry",
            "Stoch.K", "Stoch.D", "ADX", "ADX+DI", "ADX-DI", "ATR",
            "BB.upper", "BB.lower", "BB.basis",
            "high_52w", "low_52w",
            "all_time_high", "all_time_low",
            "gross_margin_ttm", "net_margin_ttm",
        ],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, len(symbols)],
        "ignore_unknown_fields": True,
    }


class TradingViewScannerFetcher(BaseFetcher):
    """Fetches live intraday data from TradingView Scanner."""

    def __init__(self, session_id: str | None = None):
        super().__init__("TradingView Scanner")
        self.session_id = session_id or TRADINGVIEW_SESSION_ID
        self.session = requests.Session()
        if self.session_id:
            self.session.cookies.set("sessionid", self.session_id)

    def fetch(self, symbols: list[str] | None = None) -> FetchResult:
        """Fetch live snapshot for given symbols."""
        if symbols is None:
            symbols = DEFAULT_INTRADAY_SYMBOLS.copy()

        return self._retry(self._fetch_snapshot, symbols)

    def _fetch_snapshot(self, symbols: list[str]) -> FetchResult:
        """Internal fetch implementation."""
        query = build_query(symbols)

        try:
            resp = self.session.post(
                TV_SCAN_URL,
                json=query,
                headers=TV_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for row in data.get("data", []):
                cols = query["columns"]
                d = dict(zip(cols, row["d"]))
                d["symbol"] = d.pop("name")
                d["timestamp"] = datetime.now().isoformat()
                d["exchange"] = row["s"].split(":")[0]
                results.append(d)

            # Deduplicate: prefer NSE over BSE
            seen = {}
            for r in results:
                sym = r["symbol"]
                if sym not in seen or r["exchange"] == "NSE":
                    seen[sym] = r
            results = list(seen.values())

            self.log_fetch(len(results))
            return FetchResult(success=True, data=results)

        except requests.RequestException as e:
            # Check for session expiry
            if resp.status_code == 401 or "session" in str(e).lower():
                from src.core.exceptions import SessionExpiredError
                raise SessionExpiredError("TradingView session expired", source="tradingview")
            return self.handle_error(e, f"for {len(symbols)} symbols")

    def aggregate_to_5min_candles(self, live_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert live snapshots to 5-minute candles."""
        now = datetime.now()
        bucket_minute = (now.minute // 5) * 5
        bucket_ts = now.replace(minute=bucket_minute, second=0, microsecond=0)

        candles = []
        for d in live_data:
            candle = {
                "symbol": d["symbol"],
                "candle_ts": bucket_ts.isoformat(),
                "open": d.get("open"),
                "high": d.get("high"),
                "low": d.get("low"),
                "close": d.get("close"),
                "volume": d.get("volume"),
                "vwap": d.get("VWAP"),
            }
            candles.append(candle)

        return candles

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        now = datetime.now()
        current_time = now.time()
        open_time = time.fromisoformat(MARKET_OPEN_TIME)
        close_time = time.fromisoformat(MARKET_CLOSE_TIME)
        return open_time <= current_time <= close_time

    def close(self):
        """Close HTTP session."""
        try:
            self.session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Convenience function for backward compatibility
def fetch_live_snapshot(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    """Fetch live intraday data for symbols from TradingView."""
    with TradingViewScannerFetcher() as fetcher:
        result = fetcher.fetch(symbols)
        if result.success:
            return result.data or []
        return []
