"""
Combined Pre-Market Report — Historical + Live Data Merge
Generates 9:00 AM report merging morning report historical data with live pre-market prices.
"""
import asyncio
import logging
from datetime import date
from typing import Optional

from config import (
    OWNER_CHAT_ID, REPORT_TABLE_ROWS, REPORT_TOP_PICKS,
    TRADINGVIEW_SESSION_ID,
)
from database import (
    get_latest_analysis, get_resolved_analysis_date, get_db_stats,
)
from intraday_fetcher import fetch_live_snapshot
from bot import _send_rich_chunks, _needs_rich

logger = logging.getLogger(__name__)


# ─── Column Configuration ───────────────────────────────────────────

HISTORICAL_COLS = [
    "close", "change", "volume", "avg_price",
    "rsi_14", "adx_14", "macd_line", "signal_line", "macd_hist",
    "sma_20", "sma_50", "sma_200",
    "ema_20", "ema_50", "ema_200",
    "atr_14", "bb_upper", "bb_lower",
    "rel_volume", "obv_trend",
    "composite_score", "recommendation",
]

LIVE_COLS = [
    "close", "change_abs", "change", "volume", "VWAP", "RSI",
]

MERGED_TABLE_COLS = [
    ("Symbol", "symbol"),
    ("EOD Close", "hist_close"),
    ("Live LTP", "live_close"),
    ("Gap%", "gap_pct"),
    ("EOD Chg%", "hist_change"),
    ("Live Chg%", "live_change"),
    ("EOD RSI", "hist_rsi"),
    ("Live RSI", "live_rsi"),
    ("RSI Δ", "rsi_delta"),
    ("EOD Vol", "hist_vol"),
    ("Live Vol", "live_vol"),
    ("Vol Ratio", "vol_ratio"),
    ("VWAP", "live_vwap"),
    ("EOD Rec", "hist_rec"),
]


def _fmt(v, fmt=".2f", na="—"):
    """Format value or return na."""
    if v is None:
        return na
    try:
        return format(v, fmt)
    except (ValueError, TypeError):
        return na


def _gap_pct(live_ltp: float, eod_close: float) -> Optional[float]:
    """Calculate gap percentage: (Live - EOD) / EOD * 100."""
    if live_ltp is None or eod_close is None or eod_close == 0:
        return None
    return ((live_ltp - eod_close) / eod_close) * 100


def _vol_ratio(live_vol: int, avg_vol: float) -> Optional[float]:
    """Live volume / average daily volume."""
    if live_vol is None or avg_vol is None or avg_vol == 0:
        return None
    return live_vol / avg_vol


def _rsi_signal(rsi: Optional[float]) -> str:
    """RSI signal emoji."""
    if rsi is None:
        return "—"
    if rsi >= 70:
        return "🔴"
    if rsi >= 60:
        return "🟢"
    if rsi >= 40:
        return "🟡"
    if rsi >= 30:
        return "🔵"
    return "🔴"


def _gap_emoji(gap: Optional[float]) -> str:
    """Gap emoji."""
    if gap is None:
        return "—"
    if gap >= 2:
        return "🚀"
    if gap >= 1:
        return "📈"
    if gap >= -1:
        return "➡️"
    if gap >= -2:
        return "📉"
    return "💥"


def _vol_emoji(ratio: Optional[float]) -> str:
    """Volume ratio emoji."""
    if ratio is None:
        return "—"
    if ratio >= 2:
        return "🔥"
    if ratio >= 1:
        return "📊"
    return "💤"


def merge_historical_live(historical: list[dict], live_data: list[dict]) -> list[dict]:
    """
    Merge historical analysis data with live pre-market data.
    Returns list of merged dicts for each symbol.
    """
    # Build live lookup
    live_lookup = {d["symbol"]: d for d in live_data}
    
    merged = []
    for h in historical:
        sym = h["symbol"]
        live = live_lookup.get(sym)
        
        merged_row = {
            "symbol": sym,
            # Historical (EOD)
            "hist_close": h.get("close"),
            "hist_change": h.get("change"),
            "hist_vol": h.get("volume"),
            "hist_avg_vol": h.get("volume"),  # We don't have avg_vol in analysis, use volume as proxy
            "hist_rsi": h.get("rsi_14"),
            "hist_adx": h.get("adx_14"),
            "hist_macd": h.get("macd_line"),
            "hist_macd_sig": h.get("signal_line"),
            "hist_sma20": h.get("sma_20"),
            "hist_sma50": h.get("sma_50"),
            "hist_sma200": h.get("sma_200"),
            "hist_ema20": h.get("ema_20"),
            "hist_ema50": h.get("ema_50"),
            "hist_ema200": h.get("ema_200"),
            "hist_atr": h.get("atr_14"),
            "hist_bb_upper": h.get("bb_upper"),
            "hist_bb_lower": h.get("bb_lower"),
            "hist_rel_vol": h.get("rel_volume"),
            "hist_obv": h.get("obv_trend"),
            "hist_avg_price": h.get("avg_price"),
            "hist_score": h.get("composite_score"),
            "hist_rec": h.get("recommendation"),
            # Live (pre-market)
            "live_close": live.get("close") if live else None,
            "live_change_abs": live.get("change_abs") if live else None,
            "live_change": live.get("change") if live else None,
            "live_volume": live.get("volume") if live else None,
            "live_vwap": live.get("VWAP") if live else None,
            "live_rsi": live.get("RSI") if live else None,
            # Derived
            "gap_pct": _gap_pct(live.get("close"), h.get("close")) if live else None,
            "rsi_delta": (live.get("RSI") - h.get("rsi_14")) if live and h.get("rsi_14") else None,
            "vol_ratio": _vol_ratio(live.get("volume"), h.get("volume")) if live else None,
        }
        merged.append(merged_row)
    
    return merged


def build_combined_report(merged: list[dict], analysis_date: date) -> str:
    """Build Rich Markdown combined pre-market report."""
    lines = []
    
    # Header
    lines.append(f"📊 **Pre-Market Combined Report — {analysis_date.strftime('%d %b %Y')} 09:00 IST**")
    lines.append("")
    
    # Market status
    live_count = sum(1 for m in merged if m.get("live_close") is not None)
    lines.append(f"⏰ **Snapshot:** 09:00 IST | **Live Data:** {live_count}/{len(merged)} symbols")
    lines.append("")
    
    # Main combined table
    lines.append("| Sym | EOD Close | Live LTP | Gap% | EOD Chg% | Live Chg% | EOD RSI | Live RSI | ΔRSI | EOD Vol | Live Vol | Vol× | VWAP | EOD Rec |")
    lines.append("|:----|----------:|---------:|-----:|---------:|----------:|--------:|---------:|-----:|--------:|---------:|-----:|-----:|:-------|")
    
    for m in merged:
        sym = m["symbol"]
        
        # Historical
        h_close = _fmt(m.get("hist_close"), ",.1f")
        h_change = _fmt(m.get("hist_change"), "+.2f") + "%" if m.get("hist_change") is not None else "—"
        h_rsi = _fmt(m.get("hist_rsi"), ".1f")
        h_rec = m.get("hist_rec", "—")
        h_vol = _fmt(m.get("hist_vol"), ",.0f") if m.get("hist_vol") else "—"
        
        # Live
        l_close = _fmt(m.get("live_close"), ",.1f") if m.get("live_close") else "—"
        l_change = _fmt(m.get("live_change"), "+.2f") + "%" if m.get("live_change") else "—"
        l_rsi = _fmt(m.get("live_rsi"), ".1f") if m.get("live_rsi") else "—"
        l_vol = _fmt(m.get("live_volume"), ",.0f") if m.get("live_volume") else "—"
        vwap = _fmt(m.get("live_vwap"), ",.1f") if m.get("live_vwap") else "—"
        
        # Derived
        gap = _fmt(m.get("gap_pct"), "+.2f") + "%" if m.get("gap_pct") is not None else "—"
        rsi_d = _fmt(m.get("rsi_delta"), "+.1f") if m.get("rsi_delta") is not None else "—"
        vol_r = _fmt(m.get("vol_ratio"), ".2f") + "x" if m.get("vol_ratio") else "—"
        
        # Emojis
        gap_emoji = _gap_emoji(m.get("gap_pct"))
        rsi_e = _rsi_signal(m.get("live_rsi"))
        vol_e = _vol_emoji(m.get("vol_ratio"))
        
        lines.append(
            f"| {sym} | {h_close} | {l_close} | {gap_emoji}{gap} | "
            f"{h_change} | {l_change} | {h_rsi} | {rsi_e}{l_rsi} | {rsi_d} | "
            f"{h_vol} | {vol_e}{l_vol} | {vol_r} | {vwap} | {h_rec} |"
        )
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Gap Analysis Section
    lines.append("### 🎯 **Gap Analysis**")
    lines.append("")
    
    gapped = [m for m in merged if m.get("gap_pct") is not None]
    if gapped:
        # Top gappers
        up = sorted([m for m in gapped if m.get("gap_pct", 0) > 0], 
                    key=lambda x: x.get("gap_pct", 0), reverse=True)[:5]
        down = sorted([m for m in gapped if m.get("gap_pct", 0) < 0], 
                      key=lambda x: x.get("gap_pct", 0))[:5]
        
        if up:
            lines.append("**🚀 Top Gaps Up:**")
            for m in up:
                gap = _fmt(m.get("gap_pct"), "+.2f")
                lines.append(f"• **{m['symbol']}** {gap}% → Live ₹{_fmt(m.get('live_close'), ',.1f')}")
            lines.append("")
        
        if down:
            lines.append("**💥 Top Gaps Down:**")
            for m in down:
                gap = _fmt(m.get("gap_pct"), "+.2f")
                lines.append(f"• **{m['symbol']}** {gap}% → Live ₹{_fmt(m.get('live_close'), ',.1f')}")
            lines.append("")
    
    # Volume Surge
    vol_surged = [m for m in merged if m.get("vol_ratio") and m["vol_ratio"] >= 2]
    if vol_surged:
        lines.append("### 🔥 **Pre-Market Volume Surge (≥2x)**")
        for m in sorted(vol_surged, key=lambda x: x.get("vol_ratio", 0), reverse=True)[:5]:
            lines.append(f"• **{m['symbol']}** {_fmt(m.get('vol_ratio'), '.2f')}x "
                         f"(Live {_fmt(m.get('live_volume'), ',.0f')} vs EOD {_fmt(m.get('hist_vol'), ',.0f')})")
        lines.append("")
    
    # RSI Momentum Shift
    rsi_shifted = [m for m in merged if m.get("rsi_delta") and abs(m["rsi_delta"]) >= 10]
    if rsi_shifted:
        lines.append("### 📊 **RSI Momentum Shift (≥10 pts)**")
        for m in sorted(rsi_shifted, key=lambda x: abs(x.get("rsi_delta", 0)), reverse=True)[:5]:
            delta = _fmt(m.get("rsi_delta"), "+.1f")
            direction = "⬆️" if m.get("rsi_delta", 0) > 0 else "⬇️"
            lines.append(f"• **{m['symbol']}** RSI {delta} {direction} "
                         f"(EOD {_fmt(m.get('hist_rsi'), '.1f')} → Live {_fmt(m.get('live_rsi'), '.1f')})")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append(f"_Source: Historical (EOD BhavCopy) + Live (TradingView Scanner)_")
    lines.append(f"_Generated: 09:00 IST | {live_count}/{len(merged)} live_")
    lines.append("")
    lines.append("⚠️ _Pre-market data indicative only. Not financial advice._")
    
    return "\n".join(lines)


async def send_combined_premarket_report(app) -> dict:
    """
    Main entry: Generate and send combined pre-market report to owner.
    Called by scheduler at 09:00 IST (Mon-Fri).
    """
    logger.info("Generating combined pre-market report...")
    
    try:
        # 1. Get morning report analysis (top 25)
        analysis_date = get_resolved_analysis_date()
        if not analysis_date:
            logger.warning("No analysis date available")
            return {"sent": 0, "failed": 1, "total": 1}
        
        analysis = get_latest_analysis(analysis_date)
        if not analysis:
            logger.warning("No analysis data available")
            return {"sent": 0, "failed": 1, "total": 1}
        
        # Top 25 by composite_score
        top25 = sorted(analysis, key=lambda x: x.get("composite_score", 0), reverse=True)[:25]
        
        # 2. Fetch live data for all 25
        symbols = [s["symbol"] for s in top25]
        logger.info("Fetching live data for %d symbols", len(symbols))
        
        live_data = await asyncio.get_event_loop().run_in_executor(
            None, fetch_live_snapshot, symbols
        )
        
        if not live_data:
            logger.warning("No live data fetched")
            return {"sent": 0, "failed": 1, "total": 1}
        
        # 3. Merge historical + live
        merged = merge_historical_live(top25, live_data)
        live_count = sum(1 for m in merged if m.get("live_close") is not None)
        
        # 4. Build combined report
        report = build_combined_report(merged, analysis_date)
        
        # 5. Send to owner only
        if _needs_rich(report):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, report)
        else:
            await app.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=report,
                parse_mode="Markdown",
            )
        
        logger.info("Sent combined pre-market report to owner (%d live)", live_count)
        return {"sent": 1, "failed": 0, "total": 1}
        
    except Exception as e:
        logger.error("Failed to send combined pre-market report: %s", e, exc_info=True)
        return {"sent": 0, "failed": 1, "total": 1}


# ─── Manual Test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, ".")
    os.environ.setdefault("MARKETMETER_BOT_TOKEN", "dummy")
    os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "123456")
    
    from bot import create_application
    import asyncio
    
    async def test():
        app = create_application()
        await app.initialize()
        result = await send_combined_premarket_report(app)
        print(f"Result: {result}")
        await app.shutdown()
    
    asyncio.run(test())