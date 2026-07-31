"""
Report generator for MarketMeter.
Formats analysis results into Rich Markdown for Telegram.
"""
import logging
from datetime import date, datetime
from typing import Optional

from config import (
    OWNER_FIRST_NAME, BOT_DISPLAY_NAME, REPORT_TOP_PICKS, REPORT_TABLE_ROWS,
    SYNC_TIME, REPORT_TIME, SYNC_RETRY_INTERVAL_MINUTES,
)
from database import (
    get_analysis_by_recommendation, get_db_stats, get_sync_status,
    get_resolved_analysis_date, get_cached_report, put_cached_report,
)
from analyzer import get_market_outlook, get_analysis_aggregate

logger = logging.getLogger(__name__)

# ── Emoji & Labels ──────────────────────────────────────────────────

CATEGORY_CONFIG = {
    "STRONG_BUY":  {"emoji": "🟢", "label": "STRONG BUY",   "limit": 5},
    "BUY":         {"emoji": "🟢", "label": "BUY",           "limit": 10},
    "ACCUMULATE":  {"emoji": "🟡", "label": "ACCUMULATE",    "limit": 10},
    "WATCH":       {"emoji": "🔵", "label": "WATCH",          "limit": 10},
    "CAUTION":     {"emoji": "🟠", "label": "CAUTION",       "limit": 5},
    "AVOID":       {"emoji": "🔴", "label": "AVOID",         "limit": 5},
}

RECOMMENDATION_ORDER = ["STRONG_BUY", "BUY", "ACCUMULATE", "WATCH", "CAUTION", "AVOID"]


# ── OBV label ──────────────────────────────────────────────────────

def _obv_label(obv_trend: float, volume: int) -> str:
    if volume <= 0:
        return "↔ Flat"
    pct = abs(obv_trend) / volume
    if obv_trend > 0:
        return "↑ Surging" if pct > 0.5 else ("↑ Rising" if pct > 0.1 else "↑ Steady")
    if obv_trend < 0:
        return "↓ Falling" if pct > 0.1 else "↓ Weak"
    return "↔ Flat"


def _macd_label(macd_line, signal_line, hist) -> str:
    if macd_line is None or signal_line is None:
        return "-"
    return "Bullish" if macd_line > signal_line else "Bearish"


def _bb_pos(close, bb_upper, bb_lower) -> str:
    """Where is price within the Bollinger Band?"""
    if bb_upper is None or bb_lower is None or bb_upper == bb_lower:
        return "-"
    pct = (close - bb_lower) / (bb_upper - bb_lower)
    if pct >= 0.9:
        return "Near Upper"
    if pct >= 0.5:
        return "Mid-Upper"
    if pct >= 0.1:
        return "Mid-Lower"
    return "Near Lower"


def _fmt(v, fmt=".1f", fallback="-"):
    return format(v, fmt) if v is not None else fallback


def _narrative(s: dict) -> str:
    """One-line narrative from actual indicator values."""
    parts = []
    rsi = s.get('rsi_14')
    adx = s.get('adx_14')
    rv  = s.get('rel_volume')
    macd_b = (s.get('macd_line') or 0) > (s.get('signal_line') or 0)
    sma20  = s.get('sma_20')
    close  = s.get('close', 0)

    if rsi is not None:
        if rsi > 70:   parts.append("overbought RSI")
        elif rsi > 60: parts.append("bullish RSI")
        elif rsi < 40: parts.append("weak RSI")
    if adx is not None:
        if adx > 50:   parts.append("very strong trend")
        elif adx > 30: parts.append("strong trend")
        elif adx < 20: parts.append("weak trend")
    if rv is not None:
        if rv > 3:     parts.append(f"{rv:.1f}x volume surge")
        elif rv > 1.5: parts.append(f"{rv:.1f}x above avg volume")
    if macd_b:         parts.append("MACD bullish")
    if sma20 and close > sma20: parts.append("above SMA20")
    return "; ".join(parts[:4]) if parts else "Insufficient signal"


def _detail_block(s: dict, rank: int) -> list[str]:
    """Full breakdown block for one top pick."""
    lines = []
    sym   = s['symbol']
    close = s.get('close', 0)
    lines.append(f"**{rank}. {sym}**")
    lines.append(f"*{s.get('recommendation','').replace('_',' ')} · Score {s.get('composite_score','-')}*")
    lines.append("")

    # Price row
    avg = s.get('avg_price')
    avg_str = f"₹{avg:,.2f}" if avg else "-"
    lines.append(f"• **Price:** ₹{close:,.2f}  |  **AvgPrice\\*:** {avg_str}")

    # SMAs
    lines.append(
        f"• **SMA:** 20={_fmt(s.get('sma_20'),',.1f')}  "
        f"50={_fmt(s.get('sma_50'),',.1f')}  "
        f"100={_fmt(s.get('sma_100'),',.1f')}  "
        f"200={_fmt(s.get('sma_200'),',.1f')}"
    )
    # EMAs
    lines.append(
        f"• **EMA:** 20={_fmt(s.get('ema_20'),',.1f')}  "
        f"50={_fmt(s.get('ema_50'),',.1f')}  "
        f"100={_fmt(s.get('ema_100'),',.1f')}  "
        f"200={_fmt(s.get('ema_200'),',.1f')}"
    )
    # Momentum
    rsi = s.get('rsi_14'); adx = s.get('adx_14'); atr = s.get('atr_14')
    lines.append(
        f"• **RSI(14):** {_fmt(rsi)}  |  **ADX(14):** {_fmt(adx)}  |  **ATR(14):** {_fmt(atr)}"
    )
    # MACD
    ml = s.get('macd_line'); sl = s.get('signal_line'); mh = s.get('macd_hist')
    lines.append(
        f"• **MACD:** Line={_fmt(ml,'.4f')}  Signal={_fmt(sl,'.4f')}  "
        f"Hist={_fmt(mh,'.4f')}  ({_macd_label(ml,sl,mh)})"
    )
    # Bollinger
    bu = s.get('bb_upper'); bl2 = s.get('bb_lower')
    lines.append(
        f"• **BB:** Upper={_fmt(bu,',.1f')}  Lower={_fmt(bl2,',.1f')}  "
        f"Pos={_bb_pos(close,bu,bl2)}"
    )
    # Volume
    rv = s.get('rel_volume'); obv = s.get('obv_trend', 0); vol = s.get('volume', 1)
    lines.append(
        f"• **RelVol:** {_fmt(rv,'.2f')}x  |  **OBV:** {_obv_label(obv, vol)}"
    )
    lines.append(f"• _{_narrative(s)}_")
    return lines


# ── Report Builder ──────────────────────────────────────────────────

def generate_morning_report(analysis_date: Optional[date] = None,
                            use_cache: bool = True) -> str:
    """
    Generate the full morning analysis report in Rich Markdown format.
    Uses native Telegram tables, collapsible sections (Bot API 10.1+).

    Served from report_cache when available (~0.08ms vs ~1.1s to render).
    The cache key is the *resolved* analysis date, never date.today(), so an
    empty report is never cached under today's key.
    """
    # Resolve the real date first. Analysis runs after the 6:30 PM sync, so
    # between midnight and the next run date.today() has zero rows.
    if analysis_date is None:
        analysis_date = get_resolved_analysis_date()
        if analysis_date is None:
            # Nothing analysed yet: render the notice, but never cache it.
            return _no_data_report(date.today())

    if use_cache:
        cached = get_cached_report('morning', analysis_date)
        if cached is not None:
            logger.debug("Report cache hit for %s", analysis_date)
            return cached

    report = _render_morning_report(analysis_date)

    # Only cache real reports. Caching a "no data" notice would pin it for the
    # whole retention window.
    if use_cache and not report.startswith(_NO_DATA_MARKER):
        put_cached_report('morning', analysis_date, report)
        logger.info("Report cached for %s (%d chars)", analysis_date, len(report))

    return report


def _render_morning_report(analysis_date: date) -> str:
    """Curated 3-pick + 10-row scan report in Rich Markdown.

    BUG-C (single-pass): previously this called get_analysis_by_recommendation and
    get_market_outlook, each independently re-querying the full daily_analysis table
    (2x the reads for identical rows). Now get_analysis_aggregate reads the rows
    ONCE and returns (grouped, outlook). Output is byte-identical; the change
    strictly halves the analysis-fetch cost of a report render.
    """
    return _render_morning_report_single_pass(analysis_date)


def _render_morning_report_single_pass(analysis_date: date) -> str:
    """Render using one analysis-row fetch; outlook + grouping derived in memory."""
    grouped, outlook = get_analysis_aggregate(analysis_date)
    db_stats = get_db_stats()

    total_stocks = sum(len(v) for v in grouped.values())
    if total_stocks == 0:
        return _no_data_report(analysis_date)

    # All stocks ranked by composite_score desc for top-picks and scan table
    all_stocks = sorted(
        [s for v in grouped.values() for s in v],
        key=lambda x: x.get('composite_score', 0), reverse=True
    )

    lines = []

    # ── Header ──
    lines.append(f"📊 **{BOT_DISPLAY_NAME} Morning Report — {analysis_date.strftime('%d %b %Y')}**")
    lines.append("")

    # ── Market Outlook ──
    lines.append(f"📈 **Market Outlook:** {outlook['outlook']}")
    lines.append(
        f"• Bullish: {outlook['bullish_pct']}% | Bearish: {outlook['bearish_pct']}% | "
        f"Neutral: {outlook['neutral_pct']}%"
    )
    if outlook['avg_rsi']:
        lines.append(
            f"• Avg RSI: {outlook['avg_rsi']} | Avg ADX: {outlook['avg_adx']} | "
            f"Stocks analyzed: {outlook['total_stocks']}"
        )

    # ── Category tally ──
    tally_parts = []
    for key in ["STRONG_BUY", "BUY", "ACCUMULATE", "WATCH", "CAUTION", "AVOID"]:
        n = len(grouped.get(key, []))
        if n:
            cfg = CATEGORY_CONFIG[key]
            tally_parts.append(f"{cfg['emoji']} {cfg['label']} {n}")
    lines.append("• " + "  ·  ".join(tally_parts))
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Top Picks (detailed) ──
    top_n = min(REPORT_TOP_PICKS, len(all_stocks))
    lines.append(f"**🎯 Top {top_n} Picks**")
    lines.append("")
    for i, s in enumerate(all_stocks[:top_n], 1):
        lines.extend(_detail_block(s, i))
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Scan Table (lean, compressed values) ──
    table_n = min(REPORT_TABLE_ROWS, len(all_stocks))
    lines.append(f"**📋 Top {table_n} Scan**")
    lines.append("")
    lines.append("| # | Symbol | LTP | AvgPrice* | RSI | ADX | RelVol | OBV | BB | MACD | Rec |")
    lines.append("|:-:|:------|----:|----------:|----:|----:|-------:|:----|:---|:-----|:----|")
    for i, s in enumerate(all_stocks[:table_n], 1):
        close = s.get('close', 0)
        avg   = s.get('avg_price')
        rsi   = s.get('rsi_14')
        adx   = s.get('adx_14')
        rv    = s.get('rel_volume')
        obv   = s.get('obv_trend', 0)
        vol   = s.get('volume', 1)
        bu    = s.get('bb_upper'); bl2 = s.get('bb_lower')
        ml    = s.get('macd_line'); sl2 = s.get('signal_line'); mh = s.get('macd_hist')
        rec   = s.get('recommendation', '').replace('_', ' ')
        lines.append(
            f"| {i} | {s['symbol']} "
            f"| ₹{close:,.0f} "
            f"| {f'₹{avg:,.0f}' if avg else '-'} "
            f"| {_fmt(rsi,'.0f')} "
            f"| {_fmt(adx,'.0f')} "
            f"| {f'{rv:.1f}x' if rv else '-'} "
            f"| {_obv_label(obv, vol)} "
            f"| {_bb_pos(close, bu, bl2)} "
            f"| {_macd_label(ml, sl2, mh)} "
            f"| {rec} |"
        )
    lines.append("")
    lines.append("_\\*AvgPrice = NSE's published average traded price for the day "
                 "(full-day average, not intraday VWAP)_")
    lines.append("")

    # ── Column legend ──
    # Abbreviated headers are unreadable without expansion, but a full glossary
    # would blow the payload. Collapsed <details> keeps it one tap away.
    lines.append("<details><summary>**📘 Column Guide**</summary>")
    lines.append("")
    lines.append("| Code | Full Form | Meaning |")
    lines.append("|:-----|:----------|:--------|")
    lines.append("| LTP | Last Traded Price | Closing price |")
    lines.append("| AvgPrice | Average Price | Day's average traded price |")
    lines.append("| RSI | Relative Strength Index | Speed of move (>70 overbought) |")
    lines.append("| ADX | Average Directional Index | Trend strength (>25 strong) |")
    lines.append("| RelVol | Relative Volume | Volume vs 20-day average |")
    lines.append("| OBV | On-Balance Volume | Money flowing in or out |")
    lines.append("| BB | Bollinger Bands | Price vs recent range |")
    lines.append("| MACD | Moving Avg Convergence Divergence | Momentum direction |")
    lines.append("| Rec | Recommendation | Composite signal |")
    lines.append("")
    lines.append("ℹ️ Full explanations: /indicators")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("")
    lines.append("<details><summary>**📌 Data Summary**</summary>")
    lines.append("")
    lines.append(f"• Total records: {db_stats['total_records']:,}")
    lines.append(f"• Unique stocks: {db_stats['unique_symbols']:,}")
    lines.append(f"• Date range: {db_stats['date_from']} to {db_stats['date_to']}")
    lines.append(f"• Active subscribers: {db_stats['active_subscribers']}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("💡 **Commands:** /subscribe | /unsubscribe | /report | /status | /indicators")
    lines.append("")
    lines.append("⚠️ _This is not financial advice. Do your own research before trading._")

    return "\n".join(lines)


def warm_report_cache(analysis_date: Optional[date] = None) -> bool:
    """
    Render and store the morning report ahead of demand.

    Called at the end of run_batch_analysis so the 08:00 broadcast and every
    /report are cache reads. Returns True when a payload was cached.
    """
    if analysis_date is None:
        analysis_date = get_resolved_analysis_date()
    if analysis_date is None:
        logger.info("Nothing analysed yet; report cache not warmed")
        return False

    report = _render_morning_report(analysis_date)
    if report.startswith(_NO_DATA_MARKER):
        logger.info("No analysis rows for %s; report cache not warmed", analysis_date)
        return False

    put_cached_report('morning', analysis_date, report)
    return True


_NO_DATA_MARKER = f"📊 *{BOT_DISPLAY_NAME} Morning Report"


def _no_data_report(analysis_date: date) -> str:
    """Report when no analysis data is available."""
    return f"""📊 *{BOT_DISPLAY_NAME} Morning Report — {analysis_date.strftime('%d %b %Y')}*

⚠️ *No analysis data available yet.*

Possible reasons:
• Initial data sync is still in progress
• Today is a market holiday
• Sync failed — check /status

💡 The bot syncs data daily at 6:30 PM IST.
Reports are generated automatically at 8:00 AM IST.

_Use /status to check sync progress._"""


# ── Sync Status Message ─────────────────────────────────────────────

def generate_sync_status_message(sync_result: dict) -> str:
    """
    Generate a sync completion/failure notification for the owner.
    """
    status = sync_result.get('status', 'unknown')
    now = datetime.now().strftime('%d %b %Y, %I:%M %p IST')

    if status == 'up_to_date':
        return f"""✅ *{BOT_DISPLAY_NAME} Sync Status*

📅 {now}
📊 Status: Already up to date
💾 No new data to sync.

_Everything is current._"""

    if status == 'completed':
        success = sync_result.get('success', 0)
        failed = sync_result.get('failed', 0)
        holidays = sync_result.get('holidays', 0)
        not_available = sync_result.get('not_available', [])
        records = sync_result.get('total_records', 0)
        processed = sync_result.get('dates_processed', 0)

        emoji = "✅" if failed == 0 and not not_available else "⚠️"

        lines = [
            f"{emoji} *{BOT_DISPLAY_NAME} Sync Completed*",
            "",
            f"📅 {now}",
            f"📊 Dates processed: {processed}",
            f"✅ Success: {success} | ❌ Failed: {failed} | 🏖️ Holidays: {holidays} | ⏳ Pending: {len(not_available)}",
            f"📥 Records inserted: {records:,}",
        ]

        if records > 0:
            lines.append("")
            lines.append(f"✅ *BhavCopy data inserted: {records:,} records*")

        if not_available:
            lines.append("")
            lines.append(f"⏳ *Pending dates (NSE not ready):* {', '.join(not_available)}")
            lines.append("_Will retry on next sync._")

        if failed > 0:
            lines.append("")
            lines.append("⚠️ *Failed dates will be retried on next sync.*")

        return "\n".join(lines)

    # Error case
    return f"""❌ *{BOT_DISPLAY_NAME} Sync Failed*

📅 {now}
❌ Status: {status}
📝 {sync_result.get('message', 'Unknown error')}

_Sync will be retried on next schedule._"""


def generate_sync_failure_alert(error_message: str) -> str:
    """Generate an alert when sync completely fails."""
    now = datetime.now().strftime('%d %b %Y, %I:%M %p IST')
    return f"""🚨 *{BOT_DISPLAY_NAME} Sync Alert*

📅 {now}
❌ Sync encountered an error:

```
{error_message[:500]}
```

_The scheduler will retry on the next cycle._
_Check logs for details: `tail -50 logs/bot.log`_"""


# ── Status Command Response ─────────────────────────────────────────

def generate_status_message() -> str:
    """Generate a detailed status message for the /status command."""
    db_stats = get_db_stats()
    sync_logs = get_sync_status(days=5)

    lines = [
        "📊 **MarketMeter Status**",
        "",
        "**Database**",
        f"• Records: {db_stats['total_records']:,}",
        f"• Symbols: {db_stats['unique_symbols']:,}",
        f"• Range: {db_stats['date_from']} → {db_stats['date_to']}",
        f"• Subscribers: {db_stats['active_subscribers']}",
        "",
        "**Recent Syncs**",
        "",  # blank line required: the local Bot API server only parses a
             # pipe-table as a native RichBlockTable when it starts a fresh
             # paragraph. Adjacent to '**Recent Syncs**' it flattened to a
             # paragraph and /status rendered as raw pipe text.
    ]

    if sync_logs:
        lines.append("| Date | Status | Records |")
        lines.append("|:-----|:-------|--------:|")
        for log in sync_logs[:5]:
            status_emoji = {
                'success': '✅', 'failed': '❌',
                'holiday': '🏖️', 'skipped': '⏭️',
                'not_available': '⏳',
            }.get(log['status'], '❓')
            lines.append(
                f"| {log['trade_date']} | {status_emoji} {log['status']} | "
                f"{log['records_count']:,} |"
            )
    else:
        lines.append("• No sync history yet")

    lines.append("")
    lines.append("⏰ **Schedule**")
    lines.append(f"• Sync: {SYNC_TIME} IST daily (retries every "
                 f"{SYNC_RETRY_INTERVAL_MINUTES} min until published)")
    lines.append(f"• Report: {REPORT_TIME} IST daily")

    return "\n".join(lines)


# ── Welcome / Help Message ──────────────────────────────────────────

def generate_indicators_message() -> str:
    """
    Indicator glossary for /indicators, in Rich Markdown.

    Sized to stay inside the Rich Message limits: each <details> block is its own
    unit so _split_rich_markdown can break between blocks without ever cutting
    one open. Blank line after every </summary> so the server parses the body.
    """
    return """📊 **Technical Indicators — Full Forms & Meanings**

Every indicator below feeds the composite score that ranks stocks in /report.

---

**📋 Quick Reference**

| Code | Full Form | Simple Meaning |
|:-----|:----------|:---------------|
| RSI | Relative Strength Index | How fast is it moving? |
| ADX | Average Directional Index | How strong is the move? |
| RelVol | Relative Volume | Are people interested today? |
| OBV | On-Balance Volume | Is money flowing in or out? |
| BB | Bollinger Bands | Is it high or low vs recent prices? |
| MACD | Moving Average Convergence Divergence | Is momentum building or fading? |
| LTP | Last Traded Price | Closing price for the day |
| AvgPrice | Average Price | Day's average traded price |

---

<details><summary>**1️⃣ RSI — Relative Strength Index**</summary>

• **Measures:** speed and magnitude of price changes
• **Range:** 0 to 100
• **> 70** = Overbought (may fall)
• **< 30** = Oversold (may rise)
• **Best for:** spotting potential reversals

**In this bot:** RSI 60-75 scores highest (+3). Above 75 scores +2, since
overbought names can keep running but carry more risk.

</details>

<details><summary>**2️⃣ ADX — Average Directional Index**</summary>

• **Measures:** strength of a trend, not its direction
• **Range:** 0 to 100
• **> 25** = strong trend | **> 50** = very strong | **< 20** = no trend
• **Best for:** confirming a trend is worth following

⚠️ ADX tells you if a trend is STRONG, not whether it is UP or DOWN.

**In this bot:** ADX > 50 scores +3, > 30 scores +2, > 20 scores +1.

</details>

<details><summary>**3️⃣ RelVol — Relative Volume**</summary>

• **Measures:** today's volume against its own 20-day average
• **Formula:** today's volume ÷ average volume (last 20 days)
• **> 1.5x** = above-average interest | **> 2x** = strong | **> 3x** = exceptional
• **Best for:** confirming a price move has real backing

**In this bot:** > 3x scores +3, > 2x scores +2, > 1.5x scores +1.

</details>

<details><summary>**4️⃣ OBV — On-Balance Volume**</summary>

• **Measures:** cumulative buying vs selling pressure
• **Formula:** add volume on up days, subtract on down days
• **↑ Surging / Rising** = buying pressure | **↓ Falling** = selling pressure
• **Divergence** (price up, OBV down) is a warning sign
• **Best for:** checking a trend has volume support

**In this bot:** the 20-day OBV change is compared to daily volume; a rising
OBV scores +1.

</details>

<details><summary>**5️⃣ BB — Bollinger Bands**</summary>

• **Measures:** volatility and where price sits in its recent range
• **Upper** = SMA20 + (2 × StdDev) | **Middle** = SMA20 | **Lower** = SMA20 − (2 × StdDev)
• **Near Upper** = stretched high | **Near Lower** = stretched low
• **Squeeze** (narrow bands) often precedes a large move
• **Best for:** identifying price extremes

**In this bot:** shown as position (Near Upper / Mid-Upper / Mid-Lower / Near Lower).

</details>

<details><summary>**6️⃣ MACD — Moving Average Convergence Divergence**</summary>

• **Measures:** momentum and trend direction
• **MACD Line** = EMA12 − EMA26 | **Signal** = EMA9 of MACD | **Histogram** = MACD − Signal
• **Bullish** = MACD above Signal | **Bearish** = MACD below Signal
• **Best for:** catching trend and momentum changes

**In this bot:** MACD above Signal scores +2. Note a stock can read Bullish
while both lines are still negative — that is momentum improving from a low base.

</details>

<details><summary>**🧮 How the Composite Score Works**</summary>

Each stock earns points, then the total maps to a recommendation.

| Factor | Points |
|:-------|:-------|
| RSI 60-75 | +3 |
| RSI > 75 | +2 |
| RSI > 50 | +1 |
| ADX > 50 | +3 |
| ADX > 30 | +2 |
| ADX > 20 | +1 |
| RelVol > 3x | +3 |
| RelVol > 2x | +2 |
| RelVol > 1.5x | +1 |
| MACD bullish | +2 |
| Above SMA20 | +2 |
| Above SMA50 | +2 |
| Above SMA100 | +1 |
| Price > 5% over SMA20 | +1 |
| OBV rising | +1 |

Higher totals map to STRONG BUY / BUY, mid to ACCUMULATE / WATCH, low to
CAUTION / AVOID. RSI and ADX also gate the final label, so a high score with
extreme RSI can still be downgraded.

</details>

<details><summary>**🎯 Reading Signals Together**</summary>

No single indicator is sufficient; agreement across them is what matters.

| Scenario | What to look for |
|:---------|:-----------------|
| Strong setup | RSI 60-75 + ADX > 25 + RelVol > 1.5x + OBV rising + MACD bullish |
| Warning | RSI > 80 + ADX < 20 + RelVol < 0.8x + OBV falling |
| Trend confirmed | ADX > 30 + MACD bullish + OBV rising |
| Breakout check | RelVol > 2x + RSI > 60 + ADX > 25 + price near BB upper |

</details>

---

📊 All indicators are computed on **full price history** from 2022-01-03, so
the 200-period values are exact rather than approximated.

⚠️ _Not financial advice. Indicators describe past price action and never
guarantee future moves._"""


def generate_welcome_message(first_name: str = "there") -> str:
    """Welcome message for new users. QuicklixBot-style Rich Markdown."""
    return f"""👋 **Hello {first_name}!**

**Welcome to MarketMeter** — your daily NSE stock analysis assistant.

---

**📊 What this bot does:**
📥 Downloads daily BhavCopy data from NSE
📊 Runs technical analysis on all 3,000+ stocks
📈 Sends morning reports with BUY/WATCH/AVOID signals

---

**🎯 Your Daily Edge**

| Feature | Status |
|:--------|:------:|
| **EOD Data** | ✅ 6:30 PM IST |
| **Live Prices** | ✅ 9:00 AM IST |
| **Full History** | ✅ 2022-01-03 → latest trading day |
| **Indicators** | ✅ 15+ technicals |
| **Coverage** | ✅ 3,000+ NSE stocks |

---

**⚡ Quick Commands**

| Command | Description |
|:--------|:------------|
| `/start` | This welcome message |
| `/subscribe` | Get daily morning reports |
| `/unsubscribe` | Stop receiving reports |
| `/report` | Get today's analysis on demand |
| `/status` | Check sync & database status |
| `/indicators` | RSI, ADX, MACD, SMA/EMA explained |
| `/search <symbol|name>` | Live price + full details |
| `/help` | Show detailed help |

---

**🔍 How it works**

```
1️⃣ EOD Sync (6:30 PM) → Download BhavCopy → Store in SQLite
2️⃣ Analysis → RSI, ADX, MACD, EMA/SMA, Volume, OBV
3️⃣ Score → Composite 0-18 → STRONG BUY → AVOID
4️⃣ Report (8:30 AM) → Top 25 + Full scan table
5️⃣ Pre-market (9:00 AM) → Live prices for tracked symbols
```

---

**📈 Report Categories**

<details open><summary>**📊 Signal Legend**</summary>

| Emoji | Signal | Score | Action |
|:-----:|:-------|:-----:|:-------|
| 🟢 | **STRONG BUY** | 12-18 | High conviction entry |
| 🟢 | **BUY** | 10-11 | Strong momentum |
| 🟡 | **ACCUMULATE** | 8-9 | Add on dips |
| 🔵 | **WATCH** | 6-7 | Monitor for setup |
| 🟠 | **CAUTION** | <6 | Overbought/weak |
| 🔴 | **AVOID** | <6 | Poor setup |

</details>

---

**🔔 Pre-Market Live Prices**
• **9:00 AM IST** — Live quotes for tracked symbols
• **/search RELIANCE** — Instant live quote + 15 indicators

---

**💡 Pro Tips**
<details><summary>**📖 Learn More**</summary>

• `/indicators` — Full glossary & scoring rules
• `/search <name>` — Fuzzy search (e.g. `/search airtel` → BHARTIARTL)
• `/status` — Database health, sync history, subscriber count

</details>

---

⚠️ _Not financial advice. All analysis based on technical indicators only._"""


def generate_help_message() -> str:
    """Help message with all commands. Rich Markdown."""
    return """🆘 **MarketMeter Help**

**Commands**

| Command | Description |
|:--------|:------------|
| /start | Welcome message |
| /subscribe | Subscribe to daily reports |
| /unsubscribe | Unsubscribe from reports |
| /report | Get latest analysis report |
| /status | Database & sync status |
| /indicators | Indicator meanings & scoring |
| /search <symbol|name> | Live price & full details |
| /help | This message |

**How it works**

1️⃣ Bot downloads BhavCopy data daily at 6:30 PM IST
2️⃣ Technical analysis runs on all stocks
3️⃣ Morning report sent at 8:30 AM IST with:

<details open><summary>**📊 Report Categories**</summary>

| Emoji | Category |
|:-----:|:---------|
| 🟢 | STRONG BUY / BUY |
| 🟡 | ACCUMULATE |
| 🔵 | WATCH |
| 🟠 | CAUTION |
| 🔴 | AVOID |

</details>

**Pre-market live prices**

• 9:00 AM — Live prices for tracked symbols
• `/search RELIANCE` — instant live quote + indicators

**Scoring factors**

| Factor | Description |
|:-------|:------------|
| RSI | Relative Strength Index |
| ADX | Trend Strength |
| MACD | Momentum |
| SMA/EMA 20/50/100/200 | Moving Averages |
| Relative Volume | Volume vs average |
| OBV | On-Balance Volume |

<details><summary>**ℹ️ Full Indicator Guide**</summary>

Use `/indicators` for detailed explanations of each indicator, scoring rules, and how to read signals together.

</details>

---
⚠️ _Not financial advice. DYOR._"""
