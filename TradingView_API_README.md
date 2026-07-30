# TradingView Scanner API Integration

Complete documentation for live NSE/BSE data fetching via TradingView's public scanner endpoint.

---

## 📋 Overview

| Property | Value |
|----------|-------|
| **Endpoint** | `https://scanner.tradingview.com/india/scan` |
| **Method** | `POST` |
| **Content-Type** | `application/json` |
| **Auth** | Optional `sessionid` cookie for real-time data |
| **Rate Limit** | ~60 req/min (generous for polling) |
| **Latency** | 200-500ms per request |

---

## 🔑 Authentication (Real-Time Data)

Free real-time data requires a `sessionid` cookie from a logged-in TradingView session.

### Getting the Cookie
1. Open https://in.tradingview.com in browser
2. Log in (free account works)
3. Open DevTools → Application → Cookies → `https://scanner.tradingview.com`
4. Copy `sessionid` value (format: `5v7916xbkrhr0dfr3m42q63zkgw52kp1`)

### Usage
```python
cookies = {"sessionid": "5v7916xbkrhr0dfr3m42q63zkgw52kp1"}
requests.post(url, json=payload, cookies=cookies)
```

**Without cookie**: Data is delayed (~15 min), but all indicators still work.

---

## 📦 Request Payload Structure

```json
{
  "markets": ["india"],
  "symbols": {},
  "options": {"lang": "en"},
  "columns": [
    "name", "close", "volume", "change", "change_abs",
    "high", "low", "open", "VWAP", "RSI",
    "MACD.macd", "MACD.signal", "relative_volume_10d_calc",
    "EMA9", "EMA21", "EMA50", "EMA200",
    "SMA20", "SMA50", "SMA200",
    "market_cap_basic"
  ],
  "filter": [
    {"left": "name", "operation": "in_range", "right": ["RELIANCE", "HDFCBANK"]}
  ],
  "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
  "range": [0, 50],
  "ignore_unknown_fields": false
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `markets` | array | `["india"]` for NSE/BSE |
| `columns` | array | Fields to return (see full list below) |
| `filter` | array | Filter conditions |
| `filter2` | object | Complex AND/OR filters |
| `sort` | object | Sort column & order |
| `range` | array | `[offset, limit]` for pagination |

---

## 📊 Available Columns (NSE/India)

### Price & Volume
| Column | Description | Example |
|--------|-------------|---------|
| `name` | Symbol name | `RELIANCE` |
| `close` | Last traded price | `2428.50` |
| `volume` | Volume (shares) | `7428623` |
| `change` | Change % | `0.71` |
| `change_abs` | Change absolute | `17.20` |
| `high` | Day high | `2435.00` |
| `low` | Day low | `2405.00` |
| `open` | Day open | `2410.00` |
| `VWAP` | Session VWAP | `2418.33` |

### Technical Indicators (Computed Server-Side)
| Column | Description |
|--------|-------------|
| `RSI` | RSI(14) on daily timeframe |
| `MACD.macd` | MACD line (12,26) |
| `MACD.signal` | MACD signal (9) |
| `MACD.hist` | MACD histogram |
| `EMA9` / `EMA21` / `EMA50` / `EMA200` | Exponential MAs |
| `SMA20` / `SMA50` / `SMA200` | Simple MAs |
| `relative_volume_10d_calc` | Volume / 10-day avg volume |

### Fundamentals
| Column | Description |
|--------|-------------|
| `market_cap_basic` | Market cap (₹) |
| `price_earnings_ttm` | P/E ratio TTM |
| `earnings_per_share_diluted_ttm` | EPS TTM |
| `dividends_yield_current` | Dividend yield % |

### Metadata
| Column | Description |
|--------|-------------|
| `type` | `stock`, `fund`, `dr` |
| `typespecs` | `["common"]`, `["preferred"]` |
| `currency` | `INR` |
| `exchange` | `NSE`, `BSE` |
| `sector.tr` | Sector name (translated) |
| `industry.tr` | Industry name |

---

## 🔍 Filter Operations

### Basic Filters (in `filter` array)
```json
{"left": "name", "operation": "in_range", "right": ["RELIANCE", "TCS"]}
{"left": "close", "operation": "greater", "right": 1000}
{"left": "volume", "operation": "greater", "right": 100000}
{"left": "RSI", "operation": "less", "right": 30}
{"left": "change", "operation": "greater", "right": 5}
```

### Supported Operations
| Operation | Description |
|-----------|-------------|
| `equal` | Exact match |
| `not_equal` | Not equal |
| `greater` | `>` |
| `less` | `<` |
| `in_range` | Value in array |
| `not_in_range` | Value not in array |
| `has` | Array contains |
| `has_none_of` | Array has none of |

### Complex Filters (in `filter2`)
```json
{
  "filter2": {
    "operator": "and",
    "operands": [
      {"expression": {"left": "close", "operation": "greater", "right": 500}},
      {"expression": {"left": "RSI", "operation": "less", "right": 70}},
      {"expression": {"left": "volume", "operation": "greater", "right": 1000000}}
    ]
  }
}
```

---

## 📈 Response Format

```json
{
  "totalCount": 2,
  "data": [
    {
      "s": "NSE:RELIANCE",
      "d": [
        "RELIANCE",      // name
        2428.50,         // close
        7428623,         // volume
        0.71,            // change %
        17.20,           // change abs
        2435.00,         // high
        2405.00,         // low
        2410.00,         // open
        2418.33,         // VWAP
        48.5,            // RSI
        -8.30,           // MACD.macd
        -7.39,           // MACD.signal
        0.62,            // relative_volume_10d_calc
        2420.1,          // EMA9
        2415.2,          // EMA21
        ...
      ]
    }
  ]
}
```

### Parsing
```python
columns = payload["columns"]  # matches request order
for row in response["data"]:
    symbol = row["s"].split(":")[1]  # "NSE:RELIANCE" -> "RELIANCE"
    data = dict(zip(columns, row["d"]))
    data["symbol"] = symbol
    data["exchange"] = row["s"].split(":")[0]
```

---

## 🎯 Complete Python Client

```python
import requests
from typing import Optional

TV_URL = "https://scanner.tradingview.com/india/scan"
TV_HEADERS = {
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin": "https://www.tradingview.com",
    "referer": "https://www.tradingview.com/",
}

DEFAULT_COLUMNS = [
    "name", "close", "volume", "change", "change_abs",
    "high", "low", "open", "VWAP", "RSI",
    "MACD.macd", "MACD.signal", "relative_volume_10d_calc",
    "EMA9", "EMA21", "EMA50", "EMA200",
    "SMA20", "SMA50", "SMA200",
    "market_cap_basic", "price_earnings_ttm",
    "earnings_per_share_diluted_ttm", "dividends_yield_current",
]

def build_query(
    symbols: list[str],
    columns: Optional[list[str]] = None,
    extra_filters: Optional[list[dict]] = None,
    sort_by: str = "market_cap_basic",
    limit: int = 100
) -> dict:
    """Build TradingView scanner query."""
    cols = columns or DEFAULT_COLUMNS
    flt = [{"left": "name", "operation": "in_range", "right": symbols}]
    if extra_filters:
        flt.extend(extra_filters)
    return {
        "markets": ["india"],
        "symbols": {},
        "options": {"lang": "en"},
        "columns": cols,
        "filter": flt,
        "sort": {"sortBy": sort_by, "sortOrder": "desc"},
        "range": [0, limit],
        "ignore_unknown_fields": False,
    }

def fetch_live(
    symbols: list[str],
    session_id: Optional[str] = None,
    columns: Optional[list[str]] = None,
    timeout: int = 15
) -> list[dict]:
    """
    Fetch live data for symbols.
    
    Args:
        symbols: List of symbol names (e.g., ["RELIANCE", "HDFCBANK"])
        session_id: TradingView sessionid cookie for real-time data
        columns: Custom columns (default: price, volume, indicators)
    
    Returns:
        List of dicts with live data, NSE preferred over BSE.
    """
    query = build_query(symbols, columns)
    cookies = {"sessionid": session_id} if session_id else None
    
    resp = requests.post(TV_URL, json=query, headers=TV_HEADERS, cookies=cookies, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    
    results = []
    cols = query["columns"]
    for row in data.get("data", []):
        d = dict(zip(cols, row["d"]))
        d["symbol"] = d.pop("name")
        d["exchange"] = row["s"].split(":")[0]
        results.append(d)
    
    # Deduplicate: prefer NSE over BSE
    seen = {}
    for r in results:
        sym = r["symbol"]
        if sym not in seen or r["exchange"] == "NSE":
            seen[sym] = r
    return list(seen.values())

# ─── Usage ───
if __name__ == "__main__":
    SESSION_ID = "5v7916xbkrhr0dfr3m42q63zkgw52kp1"  # from browser
    symbols = ["RELIANCE", "HDFCBANK", "ICICIBANK", "TCS", "INFY"]
    
    live = fetch_live(symbols, session_id=SESSION_ID)
    for s in live:
        print(f"{s['symbol']} ({s['exchange']}): ₹{s['close']:,.2f} "
              f"({s['change']:+.2f}%) RSI={s['RSI']:.1f} VWAP={s['VWAP']:,.1f}")
```

---

## 📱 MarketMeterBOT Integration

### Files
| File | Purpose |
|------|---------|
| `intraday_fetcher.py` | Core fetcher with `fetch_live_snapshot()` |
| `premarket_report.py` | 9:00 AM report builder + broadcaster |
| `config.py` | `TRADINGVIEW_SESSION_ID`, `INTRADAY_SYMBOLS` |

### Commands
| Command | Description |
|---------|-------------|
| `/intraday` | On-demand live snapshot of tracked symbols |
| `/track SYMBOL` | Add symbol to 9:00 AM tracking list |

### Scheduler
| Job | Time | Days |
|-----|------|------|
| `premarket_report` | 09:00 IST | Mon-Fri |

---

## ⚡ Performance & Limits

| Metric | Value |
|--------|-------|
| Max symbols per request | 500 (tested) |
| Typical latency | 300ms |
| Indicators freshness | Real-time with cookie, 15-min delayed without |
| Rate limit | ~60 req/min (soft) |
| Payload size | ~2 KB for 25 symbols |

---

## 🛠 Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `403 Forbidden` | Missing/invalid sessionid | Re-login to TradingView, copy fresh cookie |
| Delayed data | No sessionid provided | Add `sessionid` cookie |
| `RSI` = `null` | Insufficient history (new listing) | Skip or handle `None` |
| Duplicate NSE/BSE | Same symbol on both exchanges | Dedupe preferring NSE (see `fetch_live`) |
| `in_range` not working | Symbol name case | Use exact uppercase symbol name |

---

## 🔗 References

- TradingView Scanner API: https://github.com/shner-elmo/TradingView-Screener
- Column list: https://shner-elmo.github.io/TradingView-Screener/fields/stocks.html
- Market codes: https://shner-elmo.github.io/TradingView-Screener/markets.html
- Bot API 10.1 Rich Messages: See `telegram-rich-messages/SKILL.md`

---

*Generated for MarketMeterBOT — Live PriceNotifier • Last updated: 2026-07-30*