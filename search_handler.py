"""
Search Command Handler — /search with fuzzy matching + live data
"""
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import INTRADAY_SYMBOLS
from intraday_fetcher import fetch_live_snapshot

logger = logging.getLogger(__name__)

# ─── NSE Symbol List (for fuzzy matching) ───────────────────────────
# Loaded from config's INTRADAY_SYMBOLS + common NSE stocks
# ─── NSE Symbol List (for fuzzy matching) ───────────────────────────
# Loaded from config's INTRADAY_SYMBOLS + common NSE stocks
# Deduplicated while preserving order

_BASE_SYMBOLS = list(INTRADAY_SYMBOLS) + [
    # NIFTY 50
    "RELIANCE", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "TCS",
    "INFY", "ITC", "SBIN", "LT", "HINDUNILVR",
    "BAJFINANCE", "KOTAKBANK", "AXISBANK", "MARUTI", "SUNPHARMA",
    "TITAN", "ULTRACEMCO", "HCLTECH", "BAJAJFINSV", "NTPC",
    "POWERGRID", "NESTLEIND", "ONGC", "JSWSTEEL", "TECHM",
    "WIPRO", "ADANIENT", "ADANIPORTS", "COALINDIA", "TATAMOTORS",
    "TATASTEEL", "ASIANPAINT", "DRREDDY", "CIPLA", "GRASIM",
    "HINDALCO", "BPCL", "EICHERMOT", "HEROMOTOCO", "BRITANNIA",
    "DIVISLAB", "SBILIFE", "HDFCLIFE", "UPL", "APOLLOHOSP",

    # NIFTY NEXT 50 + Midcaps
    "ABB", "ACC", "ADANIGREEN", "ADANIPOWER", "ALKEM",
    "AMBUJACEM", "AUBANK", "AUROPHARMA", "BALKRISIND", "BANDHANBNK",
    "BANKBARODA", "BATAINDIA", "BEL", "BERGEPAINT", "BHEL",
    "BIOCON", "BOSCHLTD", "CANBK", "CANFINHOME", "CHOLAFIN",
    "COLPAL", "CONCOR", "COROMANDEL", "CROMPTON", "DABUR",
    "DALBHARAT", "DEEPAKNTR", "DLF", "DMART", "EXIDEIND",
    "FEDERALBNK", "GAIL", "GLAXO", "GLENMARK", "GMRINFRA",
    "GODREJCP", "GODREJPROP", "GRANULES", "GUJGASLTD", "HAVELLS",
    "HINDPETRO", "ICICIGI", "ICICIPRULI", "IDEA", "IDFCFIRSTB",
    "IGL", "INDIGO", "INDUSINDBK", "INDUSTOWER", "IPCALAB",
    "JINDALSTEL", "JUBLFOOD", "LAURUSLABS", "LICHSGFIN", "LTIM",
    "LTFH", "LUPIN", "MANAPPURAM", "MCDOWELL-N", "MFSL",
    "MGL", "MOTHERSON", "MPHASIS", "MRF", "MUTHOOTFIN",
    "NAUKRI", "NAVINFLUOR", "NBCC", "NMDC", "OBEROIRLTY",
    "OFSS", "PAGEIND", "PERSISTENT", "PETRONET", "PFC",
    "PIDILITIND", "PNB", "POLYCAB", "PRESTIGE", "PVRINOX",
    "RAMCOCEM", "RBLBANK", "RECLTD", "SAIL", "SBICARD",
    "SHREECEM", "SIEMENS", "SRF", "SUNDARMFIN", "SUNDRMFAST",
    "SYNGENE", "TATACHEM", "TATACOMM", "TATACONSUM", "TATAELXSI",
    "TATAPOWER", "TORNTPHARM", "TORNTPOWER", "TRENT", "TVSMOTOR",
    "UBL", "UNITDSPR", "VBL", "VEDL", "VOLTAS",
    "WHIRLPOOL", "WOCKPHARMA", "ZOMATO", "ZYDUSLIFE",

    # Report top picks / smallcaps
    "ORISSAMINE", "TIPSFILMS", "APCOTEXIND", "ARTEMISMED", "ASAHISONG",
    "CENTENKA", "CPEDU", "EXPLEOSOL", "OAL", "PARADEEP",
    "RAMRAT", "DIVISLAB", "RADICO", "MOLDTECH", "ALLDIGI",
    "NBIFIN", "RPSGVENT", "SAPPHIRE", "SHIVATEX", "BLUESTONE",
    "KAYNES", "LALPATHLAB", "MASTEK",
]

# Deduplicate while preserving order
_seen = set()
NSE_SYMBOLS = []
for s in _BASE_SYMBOLS:
    if s not in _seen:
        _seen.add(s)
        NSE_SYMBOLS.append(s)


def fuzzy_search(query: str, limit: int = 10) -> list[tuple[str, int]]:
    """
    Fuzzy search NSE symbols using rapidfuzz.
    Returns list of (symbol, score) tuples.
    """
    from rapidfuzz import process, fuzz

    query = query.upper().strip()
    if not query:
        return []

    # Try exact prefix match first
    prefix_matches = [s for s in NSE_SYMBOLS if s.startswith(query)]
    if prefix_matches:
        return [(s, 100) for s in prefix_matches[:limit]]

    # Fuzzy match with rapidfuzz
    results = process.extract(
        query,
        NSE_SYMBOLS,
        scorer=fuzz.WRatio,
        limit=limit,
        score_cutoff=60,
    )
    return [(r[0], r[1]) for r in results]


def build_search_keyboard(matches: list[tuple[str, int]], query: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with search results."""
    buttons = []
    for symbol, score in matches:
        label = f"{symbol} ({score}%)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"search_select|{symbol}")])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="search_cancel")])
    return InlineKeyboardMarkup(buttons)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /search <symbol> or /search <name>
    Fuzzy searches NSE symbols and shows inline keyboard.
    """
    from bot import _reply

    if not context.args:
        await _reply(update, (
            "🔍 **Search Usage**\n\n"
            "`/search RELIANCE` — exact symbol\n"
            "`/search RELI` — prefix match\n"
            "`/search reliance` — case-insensitive\n"
            "`/search oil` — fuzzy match (finds OIL, RELIANCE, etc.)\n\n"
            "Results shown as buttons. Tap to get live price + full details."
        ))
        return

    query = " ".join(context.args).strip()
    matches = fuzzy_search(query, limit=10)

    if not matches:
        await _reply(update, f"🔍 No matches for **'{query}'**. Try a different query.")
        return

    # Exact match — fetch live data directly
    if len(matches) == 1 and matches[0][1] == 100:
        symbol = matches[0][0]
        await send_live_stock_detail(update, symbol)
        return

    # Multiple matches — show keyboard
    keyboard = build_search_keyboard(matches, query)
    await _reply(update, (
        f"🔍 **Search Results for '{query}'**\n\n"
        f"Found {len(matches)} match(es). Tap a symbol for live data:"
    ), reply_markup=keyboard)


async def on_search_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback from search result button."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "search_cancel":
        await query.edit_message_text("🔍 Search cancelled.")
        return

    try:
        _, symbol = data.split("|", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid selection.")
        return

    # Show loading
    await query.edit_message_text(f"📡 Fetching live data for **{symbol}**...")

    # Fetch live data
    live_data = await fetch_live_for_symbol(symbol)

    if not live_data:
        await query.edit_message_text(f"❌ No live data for **{symbol}**.")
        return

    # Format and send rich message
    message = format_live_detail(symbol, live_data)
    from bot import _send_rich_chunks
    await _send_rich_chunks(query.get_bot(), query.message.chat.id, message)


async def fetch_live_for_symbol(symbol: str) -> Optional[dict]:
    """Fetch live data for a single symbol via TradingView."""
    try:
        loop = __import__('asyncio').get_event_loop()
        results = await loop.run_in_executor(None, fetch_live_snapshot, [symbol])
        if results:
            return results[0]
    except Exception as e:
        logger.error("Live fetch failed for %s: %s", symbol, e)
    return None


def format_live_detail(symbol: str, data: dict) -> str:
    """
    Format live stock data as Rich Markdown with tables.
    """
    ltp = data.get("close", 0)
    chg = data.get("change_abs", 0)
    chg_pct = data.get("change", 0)
    vol = data.get("volume", 0)
    high = data.get("high", 0)
    low = data.get("low", 0)
    opn = data.get("open", 0)
    vwap = data.get("VWAP", 0)
    rsi = data.get("RSI", 0)
    macd = data.get("MACD.macd", 0)
    macd_sig = data.get("MACD.signal", 0)
    rel_vol = data.get("relative_volume_10d_calc", 0)
    ema9 = data.get("EMA9", 0)
    ema21 = data.get("EMA21", 0)
    ema50 = data.get("EMA50", 0)
    ema200 = data.get("EMA200", 0)
    sma20 = data.get("SMA20", 0)
    sma50 = data.get("SMA50", 0)
    sma200 = data.get("SMA200", 0)
    mcap = data.get("market_cap_basic", 0)
    pe = data.get("price_earnings_ttm", 0)
    eps = data.get("earnings_per_share_diluted_ttm", 0)
    div_yield = data.get("dividends_yield_current", 0)
    exchange = data.get("exchange", "NSE")

    trend = "🟢 BULLISH" if ltp > vwap else "🔴 BEARISH" if ltp < vwap else "🟡 NEUTRAL"
    rsi_zone = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
    macd_trend = "Bullish" if macd > macd_sig else "Bearish"

    lines = []

    lines.append(f"📈 **{symbol}** — Live Quote ({exchange})")
    lines.append(f"*{trend}*")
    lines.append("")

    # Price Card
    chg_str = f"{chg:+.2f}" if chg else "-"
    pct_str = f"{chg_pct:+.2f}%" if chg_pct else "-"
    lines.append("**💰 Price Summary**")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|:-------|------:|")
    lines.append(f"| **LTP** | ₹{ltp:,.2f} |")
    lines.append(f"| **Change** | {chg_str} ({pct_str}) |")
    lines.append(f"| **Open** | ₹{opn:,.2f} |")
    lines.append(f"| **High** | ₹{high:,.2f} |")
    lines.append(f"| **Low** | ₹{low:,.2f} |")
    lines.append(f"| **VWAP** | ₹{vwap:,.2f} |")
    lines.append(f"| **Volume** | {vol:,.0f} |")
    lines.append("")

    # Technical Indicators
    lines.append("**📊 Technical Indicators**")
    lines.append("")
    lines.append("| Indicator | Value | Signal |")
    lines.append("|:----------|------:|:-------|")
    lines.append(f"| **RSI(14)** | {rsi:.1f} | {rsi_zone} |")
    lines.append(f"| **MACD** | {macd:.2f} | {macd_trend} |")
    lines.append(f"| **MACD Signal** | {macd_sig:.2f} | — |")
    lines.append(f"| **Rel Volume (10d)** | {rel_vol:.2f}x | {'High' if rel_vol > 1.5 else 'Normal' if rel_vol > 0.8 else 'Low'} |")
    lines.append("")

    # Moving Averages
    lines.append("**📈 Moving Averages**")
    lines.append("")
    lines.append("| MA | Value | Price vs MA |")
    lines.append("|:---|------:|:------------|")
    for name, val in [("EMA9", ema9), ("EMA21", ema21), ("EMA50", ema50), ("EMA200", ema200),
                      ("SMA20", sma20), ("SMA50", sma50), ("SMA200", sma200)]:
        if val:
            diff_pct = ((ltp - val) / val) * 100
            vs = f"{diff_pct:+.1f}%"
            lines.append(f"| {name} | ₹{val:,.2f} | {vs} |")
    lines.append("")

    # Fundamentals
    if mcap or pe or eps or div_yield:
        lines.append("**🏢 Fundamentals**")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|:-------|------:|")
        if mcap:
            lines.append(f"| **Market Cap** | ₹{mcap/1e7:,.0f} Cr |")
        if pe:
            lines.append(f"| **P/E (TTM)** | {pe:.1f} |")
        if eps:
            lines.append(f"| **EPS (TTM)** | ₹{eps:.2f} |")
        if div_yield:
            lines.append(f"| **Div Yield** | {div_yield:.2f}% |")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("_Data source: TradingView Scanner (real-time with session)_")
    lines.append("_Use /search for another symbol_")

    return "\n".join(lines)


async def send_live_stock_detail(update: Update, symbol: str):
    """Fetch and send live detail for a symbol directly."""
    temp = await update.message.reply_text(f"📡 Fetching **{symbol}**...")
    data = await fetch_live_for_symbol(symbol)
    try:
        await temp.delete()
    except Exception:
        pass

    if not data:
        await update.message.reply_text(f"❌ No live data for **{symbol}**.")
        return

    from bot import _send_rich_chunks
    message = format_live_detail(symbol, data)
    await _send_rich_chunks(update.get_bot(), update.effective_chat.id, message)


# ─── Handler Export ─────────────────────────────────────────────────

search_handlers = [
    CommandHandler("search", cmd_search),
    CallbackQueryHandler(on_search_select, pattern=r"^search_(select|cancel)"),
]