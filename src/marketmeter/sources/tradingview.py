"""
sources/tradingview — TradingView scanner + symbol-search provider (Phase 3 home).

Phase 3 moves two chunks of code here:

  1. From /intraday_fetcher.py:
     - build_query, fetch_live_snapshot, aggregate_to_5min_candles,
       store_intraday_candles, run_intraday_ingest, add_symbol_to_tracking
  2. From /search_handler.py:
     - tv_symbol_lookup (was a free function used by the Telegram /search
       handler; now exposed as a Provider member so other consumers can
       use it too)

The /intraday_fetcher.py shim at the project root re-exports this module's
public surface (except tv_symbol_lookup, which is reached through
marketmeter.sources.tradingview directly). Phase 5 of the refactor retires
the duplicate in search_handler.py.

Why TradingView is its own provider: see docs/REFACTOR_PLAN.md §5.
A future Zerodha Kite provider slots in beside this one without touching
the analyzer or report code.
"""
from __future__ import annotations

import re
from datetime import datetime, time
from typing import Optional

import requests

from marketmeter.core.config import (
    TRADINGVIEW_SESSION_ID, MARKET_OPEN_TIME, MARKET_CLOSE_TIME,
    INTRADAY_SYMBOLS,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import (
    upsert_intraday_candles, get_tracked_symbols, add_tracked_symbol,
    init_intraday_tables,
)

logger = get_logger(__name__)

# ── TradingView Scanner (intraday snapshots) ──────────────────────────

TV_SCAN_URL = "https://scanner.tradingview.com/india/scan"
TV_HEADERS = {
    "content-type": "application/json",
    "accept": "text/plain, */*; q=0.01",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin": "https://www.tradingview.com",
    "referer": "https://www.tradingview.com/",
}


def build_query(symbols: list[str]) -> dict:
    """Build TradingView scanner query for given symbols using tickers."""
    # Use tickers format: NSE:SYMBOL
    tickers = [f"NSE:{s}" for s in symbols]
    return {
        "markets": ["india"],
        "symbols": {"tickers": tickers},
        "options": {"lang": "en"},
        "columns": [
            "name",
            "description",
            # Price + intraday (existing)
            "close", "open", "high", "low", "volume",
            "change", "change_abs", "change_from_open", "change_from_open_abs",
            "gap", "gap_percent", "VWAP",
            # Technical indicators (existing)
            "RSI", "MACD.macd", "MACD.signal",
            # Moving averages (existing)
            "EMA9", "EMA21", "EMA50", "EMA200",
            "SMA20", "SMA50", "SMA200",
            # Volume context (existing)
            "relative_volume_10d_calc",
            # Fundamentals (existing)
            "market_cap_basic", "price_earnings_ttm",
            "earnings_per_share_diluted_ttm", "dividends_yield_current",
            # ---- additions for /search enrichment (consumers use .get, safe to add) ----
            # TradingView's own recommendation rating
            "Recommend.All", "Recommend.MA", "Recommend.Other",
            # Sector / industry classification
            "sector", "industry",
            # Extra oscillators and volatility
            "Stoch.K", "Stoch.D", "ADX", "ADX+DI", "ADX-DI", "ATR",
            # Bollinger Bands
            "BB.upper", "BB.lower", "BB.basis",
            # 52-week / all-time reference levels
            "high_52w", "low_52w",
            "all_time_high", "all_time_low",
            # Margins (Mold-Tek type context)
            "gross_margin_ttm", "net_margin_ttm",
        ],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, len(symbols)],
        # ignore_unknown_fields=True keeps the response forward-compatible: TV
        # can drop or rename a column without us crashing the whole snapshot.
        "ignore_unknown_fields": True,
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


# ── TradingView Symbol Search (fuzzy resolution) ────────────────────
#
# Phase 3: this was a free function in /search_handler.py. Now it lives
# here so the symbol-search contract is owned by the TradingView provider.
# /search_handler.py keeps a re-export shim through Phase 5, when the
# handler itself moves to telegram/search/ and the duplicate is retired.

# TradingView's own fuzzy symbol search (resolves company names → symbols).
_TV_SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/"
_TV_SEARCH_HEADERS = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin": "https://in.tradingview.com",
    "referer": "https://in.tradingview.com/",
}

# Compile once, reuse per request.
_TAG = re.compile(r"<[^>]+>")


def tv_symbol_lookup(text: str, limit: int = 8) -> list[dict]:
    """
    Query TradingView's authoritative symbol search. Resolves company names,
    partial tickers and typos → canonical NSE symbol + company description.

    Returns list of {symbol, description, exchange}. Empty on any failure.

    TradingView highlights matches with HTML tags in both symbol and
    description fields (case-varied: <em>, <EM>). We strip ALL <...> tags,
    not just literal <em>, so <EM>ADANI</EM>PORTS renders as ADANIPORTS.
    """
    text = (text or "").strip()
    if not text:
        return []
    cookies = {"sessionid": TRADINGVIEW_SESSION_ID} if TRADINGVIEW_SESSION_ID else None
    try:
        resp = requests.get(
            _TV_SEARCH_URL,
            params={
                "text": text, "hl": "1", "lang": "en",
                "exchange": "NSE", "type": "stock", "domain": "production",
            },
            headers=_TV_SEARCH_HEADERS,
            cookies=cookies,
            timeout=8,
        )
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            logger.warning("TV lookup %r: JSON parse failed (%s); raw=%r",
                           text, exc, resp.text[:120])
            return []
        items = payload if isinstance(payload, list) else (
            payload.get("symbols", []) if isinstance(payload, dict) else []
        )

        out: list[dict] = []
        seen: set[str] = set()
        NON_STOCK = {"fund", "etf", "dr", "warrant", "structured", "index"}
        for item in items:
            item_type = str(item.get("type", "")).lower()
            if item_type in NON_STOCK:
                continue
            sym = _TAG.sub("", str(item.get("symbol", ""))).split(":")[-1].upper().strip()
            if not sym or not sym.isascii() or len(sym) > 20 or sym in seen:
                continue
            seen.add(sym)
            out.append({
                "symbol": sym,
                "description": _TAG.sub("", str(item.get("description", ""))).strip(),
                "exchange": item.get("exchange", "NSE"),
                "type": item_type,
            })
            if len(out) >= limit:
                break
        return out
    except Exception as exc:
        logger.warning("TV symbol lookup failed for %r: %s", text, exc)
        return []


__all__ = [
    # intraday
    "build_query",
    "fetch_live_snapshot",
    "aggregate_to_5min_candles",
    "store_intraday_candles",
    "run_intraday_ingest",
    "add_symbol_to_tracking",
    # symbol search
    "tv_symbol_lookup",
    # constants (useful for tests / callers that want to reuse endpoints)
    "TV_SCAN_URL",
    "TV_HEADERS",
]