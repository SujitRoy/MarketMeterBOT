"""
Intraday Fetcher — Live NSE Data via TradingView Scanner
"""
import logging
from datetime import datetime, time
from typing import Optional

import requests

from config import (
    TRADINGVIEW_SESSION_ID, MARKET_OPEN_TIME, MARKET_CLOSE_TIME,
    INTRADAY_SYMBOLS, TIMEZONE,
)
from database import (
    upsert_intraday_candles, get_tracked_symbols, add_tracked_symbol,
    get_intraday_candles, init_intraday_tables,
)

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


def build_query(symbols: list[str]) -> dict:
    """Build TradingView scanner query for given symbols."""
    return {
        "markets": ["india"],
        "symbols": {},
        "options": {"lang": "en"},
        "columns": [
            "name",
            "close",
            "volume",
            "change",
            "change_abs",
            "high",
            "low",
            "open",
            "VWAP",
            "RSI",
            "MACD.macd",
            "MACD.signal",
            "EMA9",
            "EMA21",
            "EMA50",
            "EMA200",
            "SMA20",
            "SMA50",
            "SMA200",
            "relative_volume_10d_calc",
            "market_cap_basic",
        ],
        "filter": [
            {"left": "name", "operation": "in_range", "right": symbols}
        ],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, len(symbols)],
        "ignore_unknown_fields": False,
    }


def fetch_live_snapshot(symbols: Optional[list[str]] = None) -> list[dict]:
    """
    Fetch live intraday data for symbols from TradingView.
    
    Args:
        symbols: List of symbol names (e.g., ['RELIANCE', 'HDFCBANK']). 
                 If None, uses INTRADAY_SYMBOLS from config + tracked symbols.
    
    Returns:
        List of dicts with live data for each symbol.
    """
    if symbols is None:
        symbols = list(INTRADAY_SYMBOLS)
        # Add tracked symbols from DB
        tracked = get_tracked_symbols()
        for t in tracked:
            if t['symbol'] not in symbols:
                symbols.append(t['symbol'])

    logger.info("Fetching live snapshot for %d symbols: %s", len(symbols), symbols)

    query = build_query(symbols)
    cookies = {"sessionid": TRADINGVIEW_SESSION_ID} if TRADINGVIEW_SESSION_ID else None

    try:
        resp = requests.post(
            TV_SCAN_URL,
            json=query,
            headers=TV_HEADERS,
            cookies=cookies,
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
            d["exchange"] = row["s"].split(":")[0]  # NSE or BSE
            results.append(d)

        # Deduplicate: prefer NSE over BSE
        seen = {}
        for r in results:
            sym = r["symbol"]
            if sym not in seen or r["exchange"] == "NSE":
                seen[sym] = r
        results = list(seen.values())

        logger.info("Fetched %d live records (deduped)", len(results))
        return results

    except requests.RequestException as e:
        logger.error("TradingView fetch failed: %s", e)
        return []


def aggregate_to_5min_candles(live_data: list[dict]) -> list[dict]:
    """
    Convert live snapshots to 5-minute candles.
    
    For true 5-min candles we'd need historical tick data; here we approximate
    by bucketing snapshots into 5-min windows. TradingView provides VWAP which
    is the session VWAP, so we use that directly.
    """
    now = datetime.now()
    # Round down to nearest 5-minute bucket
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


def store_intraday_candles(candles: list[dict]) -> int:
    """Store 5-minute candles in database."""
    if not candles:
        return 0

    rows = []
    for c in candles:
        rows.append({
            "symbol": c["symbol"],
            "candle_ts": c["candle_ts"],
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
            "vwap": c.get("vwap"),
        })

    return upsert_intraday_candles(rows)


def run_intraday_ingest() -> dict:
    """
    Main entry point: fetch live data, convert to candles, store.
    Called every 5 minutes during market hours (09:15-15:30).
    """
    # Check market hours
    now = datetime.now()
    current_time = now.time()

    if current_time < time.fromisoformat(MARKET_OPEN_TIME) or current_time > time.fromisoformat(MARKET_CLOSE_TIME):
        return {"status": "outside_market_hours", "message": f"Market closed ({current_time})"}

    # Ensure tables exist
    init_intraday_tables()

    # Fetch live data
    live_data = fetch_live_snapshot()
    if not live_data:
        return {"status": "failed", "message": "No data fetched"}

    # Aggregate to 5-min candles
    candles = aggregate_to_5min_candles(live_data)

    # Store
    stored = store_intraday_candles(candles)

    return {
        "status": "success",
        "symbols_fetched": len(live_data),
        "candles_stored": stored,
        "timestamp": now.isoformat(),
    }


def add_symbol_to_tracking(symbol: str) -> bool:
    """Add a symbol to the intraday tracking list."""
    return add_tracked_symbol(symbol, "MANUAL")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "--add":
        sym = sys.argv[2].upper()
        add_symbol_to_tracking(sym)
        print(f"Added {sym} to tracking")
    else:
        result = run_intraday_ingest()
        print(result)