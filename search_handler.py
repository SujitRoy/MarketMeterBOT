"""
Search Command Handler — /search with fuzzy matching + live data
"""
import asyncio
import logging
from datetime import datetime, time
from typing import Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    INTRADAY_SYMBOLS, MARKET_OPEN_TIME, MARKET_CLOSE_TIME, TRADINGVIEW_SESSION_ID,
)
from database import get_connection
from intraday_fetcher import fetch_live_snapshot

# TradingView's own fuzzy symbol search (resolves company names → symbols).
_TV_SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/"
_TV_SEARCH_HEADERS = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin": "https://in.tradingview.com",
    "referer": "https://in.tradingview.com/",
}

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

def _load_symbol_index() -> list[str]:
    """
    Build the searchable symbol index from the live bhavcopy DB
    (all ~3068 EQ symbols), falling back to the static seed list if the
    DB is unavailable/empty. Deduped, order-preserved.
    """
    index: list[str] = []
    seen: set[str] = set()

    def _add(symbols) -> None:
        for s in symbols:
            s = (s or "").upper().strip()
            if s and s.isascii() and s not in seen:
                seen.add(s)
                index.append(s)

    try:
        # All EQ-series symbols ever present in the bhavcopy. read-only conn.
        with get_connection() as conn:
            db_symbols = [r[0] for r in conn.execute(
                "SELECT DISTINCT symbol FROM bhavcopy WHERE series = 'EQ'"
            ).fetchall()]
    except Exception as exc:  # pragma: no cover - DB hiccup
        logger.warning("Search index: DB load failed (%s); static list only", exc)
        db_symbols = []

    _add(db_symbols)
    _add(_BASE_SYMBOLS)  # ensure static seeds present even if DB is fresh
    logger.info("Search index built: %d symbols", len(index))
    return index


def get_symbols() -> list[str]:
    """Lazy-load and cache the symbol index."""
    global NSE_SYMBOLS
    if NSE_SYMBOLS is None:
        NSE_SYMBOLS = _load_symbol_index()
    return NSE_SYMBOLS


NSE_SYMBOLS: list[str] | None = None


def fuzzy_search(query: str, limit: int = 10) -> list[tuple[str, int]]:
    """
    Search the full NSE symbol universe with ranking:
      exact (100) > prefix (95) > substring (90) > fuzzy token_set (70+).

    Returns list of (symbol, int_score) tuples, sorted best-first,
    deduplicated, capped at `limit`.
    """
    from rapidfuzz import process, fuzz

    q = query.upper().strip()
    if not q:
        return []

    universe = get_symbols()
    scored: dict[str, int] = {}

    # Exact match — immediate
    if q in universe:
        return [(q, 100)]

    # Prefix matches (strong)
    for s in universe:
        if s.startswith(q) and s not in scored:
            scored[s] = 95

    # Substring matches (e.g. PPL inside PPLPHARMA)
    for s in universe:
        if q in s and s not in scored:
            scored[s] = 90

    # Fuzzy fallback — catches typos that prefix/substring miss.
    # token_set_ratio ignores token order/duplication; cutoff 70 avoids
    # the WRatio 60-cutoff garbage (UPL 60%, RAMRAT 60%).
    for sym, score, _ in process.extract(
        q, universe, scorer=fuzz.token_set_ratio,
        limit=limit * 3, score_cutoff=70,
    ):
        if sym not in scored:
            scored[sym] = int(round(score))

    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:limit]


def tv_symbol_lookup(text: str, limit: int = 6) -> list[dict]:
    """
    Query TradingView's authoritative symbol search. Resolves company names,
    partial tickers and typos → canonical NSE symbol + company description.

    Returns list of {symbol, description, exchange}. Empty on any failure -
    the local fuzzy_search() index is always the fallback.
    """
    import re

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
        out: list[dict] = []
        for item in resp.json():
            # strip <em></em> highlight tags TV wraps around the match
            sym = re.sub(r"</?em>", "", item.get("symbol", "")).upper().strip()
            if not sym:
                continue
            out.append({
                "symbol": sym,
                "description": item.get("description", ""),
                "exchange": item.get("exchange", "NSE"),
            })
            if len(out) >= limit:
                break
        return out
    except Exception as exc:
        logger.warning("TV symbol lookup failed for %r: %s", text, exc)
        return []


def build_search_keyboard(matches: list[tuple[str, int]], query: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with search results."""
    buttons = []
    for symbol, score in matches:
        label = f"{symbol} ({int(round(score))}%)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"search_select|{symbol}")])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="search_cancel")])
    return InlineKeyboardMarkup(buttons)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /search <symbol|company>

    Flow:
      1. Exact symbol match in the local index → show live detail directly.
      2. Else ask TradingView's symbol search (resolves company names & typos
         → canonical symbol). A confident exact hit → live detail directly.
      3. Else offer candidates (TV candidates first, then local fuzzy) as
         buttons for the user to pick.
    """
    from bot import _reply

    if not context.args:
        await _reply(update, (
            "🔍 **Search Usage**\n\n"
            "`/search RELIANCE` — exact symbol\n"
            "`/search piramal` — by company name\n"
            "`/search RELI` — prefix match\n"
            "`/search TATAMTR` — fuzzy / typo-tolerant\n\n"
            "Exact symbol → live detail instantly. Otherwise tap a candidate."
        ))
        return

    query = " ".join(context.args).strip()
    q = query.upper()

    # 1) Exact symbol in local index → direct detail
    if q in get_symbols():
        await send_live_stock_detail(update, q)
        return

    # 2) TradingView authoritative lookup (company names, typos, partials)
    loop = asyncio.get_running_loop()
    tv_hits = await loop.run_in_executor(None, tv_symbol_lookup, query)
    if tv_hits:
        exact = [h for h in tv_hits if h["symbol"] == q]
        if exact:
            await send_live_stock_detail(update, exact[0]["symbol"])
            return

    # 3) Build picker: TV candidates first (with company names), then local fuzzy
    candidates: list[str] = []
    names: dict[str, str] = {}
    for h in tv_hits:
        if h["symbol"] not in candidates:
            candidates.append(h["symbol"])
            if h.get("description"):
                names[h["symbol"]] = h["description"]
    for sym, _score in fuzzy_search(query, limit=6):
        if sym not in candidates:
            candidates.append(sym)
    candidates = candidates[:8]

    if not candidates:
        await _reply(update, f"🔍 No match for **'{query}'**. Try a symbol or company name.")
        return

    keyboard = _build_candidate_keyboard(candidates, names)
    await _reply(update, (
        f"🔍 **'{query}'** — {len(candidates)} match(es). Tap to view live detail:"
    ), reply_markup=keyboard)


def _build_candidate_keyboard(
    candidates: list[str], names: dict[str, str]
) -> InlineKeyboardMarkup:
    """Inline keyboard: symbol + company description if available."""
    buttons = []
    for sym in candidates:
        label = f"{sym}"
        if names.get(sym):
            label += f" · {names[sym]}"
        buttons.append([InlineKeyboardButton(label[:64], callback_data=f"search_select|{sym}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="search_cancel")])
    return InlineKeyboardMarkup(buttons)


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
    # Keyboard is attached to the first chunk inside _send_rich_chunks.
    await _send_rich_chunks(
        query.get_bot(), query.message.chat.id, message,
        reply_markup=_chart_keyboard(symbol),
    )

    # Delete the loading message
    try:
        await query.delete_message()
    except Exception:
        pass


async def fetch_live_for_symbol(symbol: str) -> Optional[dict]:
    """Fetch live data for a single symbol via TradingView."""
    try:
        # get_running_loop() is the only correct API inside a running coroutine;
        # get_event_loop() raises DeprecationWarning and, in nested handlers, can
        # raise RuntimeError because no loop is set on the current thread.
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, fetch_live_snapshot, [symbol])
        if results:
            return results[0]
    except Exception as e:
        logger.error("Live fetch failed for %s: %s", symbol, e)
    return None


# ─── Formatting helpers (render None/0 as '—' so the UI is honest) ──

def _has(v) -> bool:
    """True if v is a usable number (not None, not 0, not NaN)."""
    if v is None:
        return False
    if isinstance(v, bool):
        return False
    if isinstance(v, float):
        # NaN check (NaN != NaN)
        return v == v and v != 0.0
    return v != 0


def _fmt_price(v) -> str:
    """₹ price, or '—' when missing."""
    return f"₹{v:,.2f}" if _has(v) else "—"


def _fmt_num(v, fmt: str = ",.2f") -> str:
    """Number with caller-supplied format, or '—'."""
    return f"{v:{fmt}}" if _has(v) else "—"


def _fmt_signed(v) -> str:
    """Signed number (e.g. +9.22), or '—'."""
    return f"{v:+.2f}" if _has(v) else "—"


def _fmt_pct(v) -> str:
    """Signed percent, or '—'."""
    return f"{v:+.2f}%" if _has(v) else "—"


def _fmt_int(v) -> str:
    """Integer with thousands separators, or '—'."""
    return f"{int(v):,}" if _has(v) else "—"


def _fmt_mcap(v) -> str:
    """
    Humanize INR market cap.
    TradingView scanner returns market_cap_basic in INR (NSE listing currency).
    """
    if not _has(v):
        return "—"
    cr = v / 1e7
    if cr < 1000:
        return f"₹{cr:,.0f} Cr"
    if cr < 100000:
        return f"₹{cr/1000:,.2f}K Cr"
    return f"₹{cr/100000:,.2f}L Cr"


def _rvol_signal(rv) -> str:
    """
    Volume bucket.
    Old code used a binary High/Normal/Low with 1.5x cutoff — labelled a 5x
    burst the same as a 1.6x uptick. A trader treats those very differently.
    """
    if not _has(rv):
        return "—"
    if rv > 3:
        return "🔥 Spike"
    if rv > 1.5:
        return "High"
    if rv > 0.8:
        return "Normal"
    return "Low"


def _tv_rating_label(rec) -> str:
    """
    Map TradingView's -1.5..+1.5 recommendation score to a human label.
    https://www.tradingview.com/support/folders/43000556872-buy-sell-indicators/
    """
    if not _has(rec):
        return "—"
    if rec >= 1.0:
        return "Strong Buy"
    if rec >= 0.5:
        return "Buy"
    if rec > -0.5:
        return "Neutral"
    if rec > -1.0:
        return "Sell"
    return "Strong Sell"


def _market_state() -> tuple[str, datetime]:
    """
    Return (state_label, now). State is 'open', 'pre-market', or 'closed'
    based on the server's local clock (which is IST on this host).
    """
    now = datetime.now()
    open_t = time.fromisoformat(MARKET_OPEN_TIME)
    close_t = time.fromisoformat(MARKET_CLOSE_TIME)
    current_t = now.time()
    if current_t < open_t:
        return "pre-market", now
    if current_t > close_t:
        return "closed", now
    return "open", now


def _position_in_range(ltp, low, high) -> Optional[float]:
    """Where in the day's range LTP sits (0=at low, 1=at high)."""
    if not (_has(ltp) and _has(low) and _has(high)) or high <= low:
        return None
    return (ltp - low) / (high - low)


def _position_label(pos: Optional[float]) -> str:
    if pos is None:
        return "—"
    pct = pos * 100
    if pct >= 90:
        return f"{pct:.0f}% (near high)"
    if pct >= 70:
        return f"{pct:.0f}% (upper half)"
    if pct >= 30:
        return f"{pct:.0f}% (mid)"
    if pct >= 10:
        return f"{pct:.0f}% (lower half)"
    return f"{pct:.0f}% (near low)"


def _chart_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """
    Public TradingView symbol page. This URL works without our sessionid
    cookie (the personal /chart/<id>/?symbol=... URL does NOT — see audit).
    """
    url = f"https://in.tradingview.com/symbols/NSE-{symbol}/"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Open Chart", url=url)],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"search_select|{symbol}")],
    ])


def format_live_detail(symbol: str, data: dict) -> str:
    """
    Format live stock data as Rich Markdown with tables.

    Layout:
      1. Header (symbol, LTP, change, sector/industry, market state)
      2. Price Summary table
      3. Intraday Analytics (gap, change-from-open, day-range position)
      4. TradingView Rating (overall / MA / oscillators)
      5. Technical Indicators (RSI, MACD, Stochastic, ADX, ATR)
      6. Bollinger Bands
      7. Moving Averages (EMA/SMA spread)
      8. 52-Week Position
      9. Fundamentals (market cap, valuation, margins, sector)
      10. Footer (timestamp, source)
    """
    ltp = data.get("close")
    chg = data.get("change_abs")
    chg_pct = data.get("change")
    vol = data.get("volume")
    high = data.get("high")
    low = data.get("low")
    opn = data.get("open")
    vwap = data.get("VWAP")
    rsi = data.get("RSI")
    macd = data.get("MACD.macd")
    macd_sig = data.get("MACD.signal")
    rel_vol = data.get("relative_volume_10d_calc")
    ema9 = data.get("EMA9")
    ema21 = data.get("EMA21")
    ema50 = data.get("EMA50")
    ema200 = data.get("EMA200")
    sma20 = data.get("SMA20")
    sma50 = data.get("SMA50")
    sma200 = data.get("SMA200")
    mcap = data.get("market_cap_basic")
    pe = data.get("price_earnings_ttm")
    eps = data.get("earnings_per_share_diluted_ttm")
    div_yield = data.get("dividends_yield_current")
    exchange = data.get("exchange", "NSE")
    description = data.get("description", "")

    # New fields (added in 2026-07-30 /search enrichment)
    chg_from_open = data.get("change_from_open_abs")
    chg_from_open_pct = data.get("change_from_open")
    gap_pct = data.get("gap")
    rec_all = data.get("Recommend.All")
    rec_ma = data.get("Recommend.MA")
    rec_osc = data.get("Recommend.Other")
    stoch_k = data.get("Stoch.K")
    stoch_d = data.get("Stoch.D")
    adx = data.get("ADX")
    adx_pos = data.get("ADX+DI")
    adx_neg = data.get("ADX-DI")
    atr = data.get("ATR")
    bb_upper = data.get("BB.upper")
    bb_lower = data.get("BB.lower")
    bb_basis = data.get("BB.basis")
    high_52w = data.get("high_52w")
    low_52w = data.get("low_52w")
    gross_m = data.get("gross_margin_ttm")
    net_m = data.get("net_margin_ttm")
    sector = data.get("sector")
    industry = data.get("industry")

    # Derived signals
    trend = (
        "🟢 BULLISH" if _has(ltp) and _has(vwap) and ltp > vwap
        else "🔴 BEARISH" if _has(ltp) and _has(vwap) and ltp < vwap
        else "🟡 NEUTRAL"
    )
    rsi_zone = (
        "Overbought" if _has(rsi) and rsi > 70
        else "Oversold" if _has(rsi) and rsi < 30
        else "Neutral"
    )
    macd_trend = "Bullish" if _has(macd) and _has(macd_sig) and macd > macd_sig else "Bearish"

    # Build the body via the helper; the dead-code fallback below is removed.
    lines: list[str] = []
    return _build_detail_body(
        symbol=symbol, exchange=exchange, description=description,
        ltp=ltp, chg=chg, chg_pct=chg_pct, vol=vol, high=high, low=low,
        opn=opn, vwap=vwap, rel_vol=rel_vol,
        rsi=rsi, macd=macd, macd_sig=macd_sig,
        stoch_k=stoch_k, stoch_d=stoch_d, adx=adx, adx_pos=adx_pos, adx_neg=adx_neg, atr=atr,
        bb_upper=bb_upper, bb_lower=bb_lower, bb_basis=bb_basis,
        ema9=ema9, ema21=ema21, ema50=ema50, ema200=ema200,
        sma20=sma20, sma50=sma50, sma200=sma200,
        high_52w=high_52w, low_52w=low_52w,
        mcap=mcap, pe=pe, eps=eps, div_yield=div_yield,
        gross_m=gross_m, net_m=net_m,
        sector=sector, industry=industry,
        chg_from_open=chg_from_open, chg_from_open_pct=chg_from_open_pct, gap_pct=gap_pct,
        rec_all=rec_all, rec_ma=rec_ma, rec_osc=rec_osc,
        trend=trend, rsi_zone=rsi_zone, macd_trend=macd_trend,
    )


def _build_detail_body(
    *,
    symbol: str, exchange: str, description: str = "",
    ltp, chg, chg_pct, vol, high, low,
    opn, vwap, rel_vol,
    rsi, macd, macd_sig,
    stoch_k, stoch_d, adx, adx_pos, adx_neg, atr,
    bb_upper, bb_lower, bb_basis,
    ema9, ema21, ema50, ema200,
    sma20, sma50, sma200,
    high_52w, low_52w,
    mcap, pe, eps, div_yield,
    gross_m, net_m,
    sector, industry,
    chg_from_open, chg_from_open_pct, gap_pct,
    rec_all, rec_ma, rec_osc,
    trend: str, rsi_zone: str, macd_trend: str,
) -> str:
    """
    Render the full Rich-Markdown body for one symbol. Pulled out of
    format_live_detail so the parameter list there stays short.
    """
    lines: list[str] = []

    # ── Header ─────────────────────────────────────────────────
    state_label, now = _market_state()
    state_banner = {
        "open": "🟢 Market open",
        "pre-market": "🟡 Pre-market",
        "closed": "🔴 Market closed",
    }[state_label]
    ltp_str = _fmt_price(ltp)
    chg_str = _fmt_signed(chg)
    pct_str = _fmt_pct(chg_pct)
    lines.append(f"📈 **{symbol}** — {ltp_str} ({exchange})")
    if description:
        lines.append(f"_🏢 {description}_")
    lines.append(f"**{trend}** · {chg_str} ({pct_str})")
    if sector or industry:
        lines.append(f"_📂 {sector or '?'} · {industry or '?'}_")
    lines.append(f"{state_banner} · Snapshot {now.strftime('%d %b %Y, %H:%M IST')}")
    lines.append("")

    # ── Price Summary ─────────────────────────────────────────
    lines.append("**💰 Price Summary**")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|:-------|------:|")
    lines.append(f"| **LTP** | {ltp_str} |")
    lines.append(f"| **Change** | {chg_str} ({pct_str}) |")
    lines.append(f"| **Open** | {_fmt_price(opn)} |")
    lines.append(f"| **High** | {_fmt_price(high)} |")
    lines.append(f"| **Low** | {_fmt_price(low)} |")
    lines.append(f"| **VWAP** | {_fmt_price(vwap)} |")
    lines.append(f"| **Volume** | {_fmt_int(vol)} |")
    lines.append(f"| **Rel Vol (10d)** | {_fmt_num(rel_vol, ',.2f')}x | {_rvol_signal(rel_vol)} |")
    lines.append("")

    # ── Intraday Analytics ────────────────────────────────────
    pos = _position_in_range(ltp, low, high)
    day_range = (
        f"{_fmt_price(low)} – {_fmt_price(high)} ({(high-low):,.2f})"
        if _has(low) and _has(high) and high > low else "—"
    )
    lines.append("**📊 Intraday Analytics**")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|:-------|------:|")
    lines.append(f"| **Change from Open** | {_fmt_signed(chg_from_open)} ({_fmt_pct(chg_from_open_pct)}) |")
    lines.append(f"| **Gap (vs prev close)** | {_fmt_pct(gap_pct)} |")
    lines.append(f"| **Day Range** | {day_range} |")
    lines.append(f"| **Position in Range** | {_position_label(pos)} |")
    lines.append("")

    # ── TradingView Rating ────────────────────────────────────
    if _has(rec_all) or _has(rec_ma) or _has(rec_osc):
        lines.append("**🎯 TradingView Rating**")
        lines.append("")
        lines.append("| Type | Score | Signal |")
        lines.append("|:-----|------:|:-------|")
        if _has(rec_all):
            lines.append(f"| **Overall** | {rec_all:+.2f} | {_tv_rating_label(rec_all)} |")
        if _has(rec_ma):
            lines.append(f"| **Moving Averages** | {rec_ma:+.2f} | {_tv_rating_label(rec_ma)} |")
        if _has(rec_osc):
            lines.append(f"| **Oscillators** | {rec_osc:+.2f} | {_tv_rating_label(rec_osc)} |")
        lines.append("")

    # ── Technical Indicators ──────────────────────────────────
    if _has(rsi) or _has(macd) or _has(stoch_k) or _has(adx) or _has(atr):
        lines.append("**📈 Technical Indicators**")
        lines.append("")
        lines.append("| Indicator | Value | Signal |")
        lines.append("|:----------|------:|:-------|")
        if _has(rsi):
            lines.append(f"| **RSI(14)** | {rsi:.1f} | {rsi_zone} |")
        if _has(macd) and _has(macd_sig):
            lines.append(f"| **MACD** | {macd:.2f} / {macd_sig:.2f} | {macd_trend} |")
        elif _has(macd):
            lines.append(f"| **MACD** | {macd:.2f} | — |")
        if _has(stoch_k) and _has(stoch_d):
            stoch_sig = "Overbought" if stoch_k > 80 else "Oversold" if stoch_k < 20 else "Neutral"
            lines.append(f"| **Stoch %K/D** | {stoch_k:.1f} / {stoch_d:.1f} | {stoch_sig} |")
        if _has(adx):
            trend_strength = "Strong" if adx > 25 else "Moderate" if adx > 20 else "Weak"
            if _has(adx_pos) and _has(adx_neg):
                direction = "Up" if adx_pos > adx_neg else "Down"
                lines.append(f"| **ADX / DI+ / DI−** | {adx:.1f} / {adx_pos:.1f} / {adx_neg:.1f} | {trend_strength} · {direction} |")
            else:
                lines.append(f"| **ADX(14)** | {adx:.1f} | {trend_strength} |")
        if _has(atr):
            lines.append(f"| **ATR(14)** | ₹{atr:,.2f} | — |")
        lines.append("")

    # ── Bollinger Bands ───────────────────────────────────────
    if _has(bb_upper) and _has(bb_lower) and _has(bb_basis):
        lines.append("**📉 Bollinger Bands (20,2)**")
        lines.append("")
        lines.append("| Band | Value |")
        lines.append("|:-----|------:|")
        lines.append(f"| **Upper** | {_fmt_price(bb_upper)} |")
        lines.append(f"| **Basis** | {_fmt_price(bb_basis)} |")
        lines.append(f"| **Lower** | {_fmt_price(bb_lower)} |")
        if _has(ltp):
            if ltp > bb_upper:
                lines.append(f"\n_LTP above upper band — momentum extended._")
            elif ltp < bb_lower:
                lines.append(f"\n_LTP below lower band — oversold._")
            else:
                pct = (ltp - bb_lower) / (bb_upper - bb_lower) * 100
                lines.append(f"\n_LTP inside bands ({pct:.0f}% of range)._")
        lines.append("")

    # ── Moving Averages ───────────────────────────────────────
    ma_pairs = [
        ("EMA9", ema9), ("EMA21", ema21), ("EMA50", ema50), ("EMA200", ema200),
        ("SMA20", sma20), ("SMA50", sma50), ("SMA200", sma200),
    ]
    ma_rows = []
    for name, val in ma_pairs:
        if not _has(val):
            continue
        if _has(ltp) and val:
            diff_pct = (ltp - val) / val * 100
            vs = f"{diff_pct:+.1f}%"
        else:
            vs = "—"
        ma_rows.append(f"| {name} | {_fmt_price(val)} | {vs} |")
    if ma_rows:
        lines.append("**📈 Moving Averages**")
        lines.append("")
        lines.append("| MA | Value | LTP vs MA |")
        lines.append("|:---|------:|---------:|")
        lines.extend(ma_rows)
        lines.append("")

    # ── 52-Week Position ──────────────────────────────────────
    if _has(high_52w) or _has(low_52w):
        lines.append("**📅 52-Week Position**")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|:-------|------:|")
        if _has(high_52w) and _has(low_52w):
            lines.append(f"| **52w Range** | {_fmt_price(low_52w)} – {_fmt_price(high_52w)} |")
        if _has(high_52w) and _has(ltp) and high_52w > 0:
            dist_high = (ltp / high_52w - 1) * 100
            lines.append(f"| **Distance from 52w High** | {dist_high:+.1f}% |")
        if _has(low_52w) and _has(ltp) and low_52w > 0:
            dist_low = (ltp / low_52w - 1) * 100
            lines.append(f"| **Distance from 52w Low** | {dist_low:+.1f}% |")
        lines.append("")

    # ── Fundamentals ──────────────────────────────────────────
    has_fund = any(_has(v) for v in (mcap, pe, eps, div_yield, gross_m, net_m))
    if has_fund:
        lines.append("**🏢 Fundamentals**")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|:-------|------:|")
        if _has(mcap):
            lines.append(f"| **Market Cap** | {_fmt_mcap(mcap)} |")
        if _has(pe):
            lines.append(f"| **P/E (TTM)** | {pe:.1f} |")
        if _has(eps):
            lines.append(f"| **EPS (TTM)** | ₹{eps:,.2f} |")
        if _has(div_yield):
            lines.append(f"| **Div Yield** | {div_yield:.2f}% |")
        if _has(gross_m):
            lines.append(f"| **Gross Margin** | {gross_m:.1f}% |")
        if _has(net_m):
            lines.append(f"| **Net Margin** | {net_m:.1f}% |")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append(f"_Source: TradingView Scanner · Snapshot {now.strftime('%d %b %Y, %H:%M IST')}_")
    lines.append("_Tap **📊 Open Chart** for the full TradingView page._")

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
    await _send_rich_chunks(
        update.get_bot(), update.effective_chat.id, message,
        reply_markup=_chart_keyboard(symbol),
    )


# ─── Handler Export ─────────────────────────────────────────────────

search_handlers = [
    CommandHandler("search", cmd_search),
    CallbackQueryHandler(on_search_select, pattern=r"^search_(select|cancel)"),
]