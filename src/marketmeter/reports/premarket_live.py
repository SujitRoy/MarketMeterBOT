# ruff: noqa: E701, E702  # pre-existing compact one-line style from original
"""
reports/premarket_live — 09:00 IST pre-market live snapshot.

Phase 4 split: build_premarket_message + send_premarket_report from
/premarket_report.py moved here. The /premarket_report.py shim at the
project root re-exports these so existing scheduler wiring keeps working.

Phase 4 also routes every price/number through marketmeter.reports.formatters
so a None ltp no longer crashes the message builder (the original had
inline `f"{ltp:,.1f}"` which fails on None).
"""
from __future__ import annotations

import asyncio

from marketmeter.core.config import (
    OWNER_CHAT_ID, REPORT_TABLE_ROWS,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import get_latest_analysis, get_resolved_analysis_date
from marketmeter.sources.tradingview import fetch_live_snapshot
from marketmeter.reports.formatters import (
    fmt, price_rupees, signed_pct, NA_DASH,
)

logger = get_logger(__name__)


def build_premarket_message(live_data: list[dict]) -> str:
    """Build Rich Markdown message with live prices. None-safe."""
    if not live_data:
        return "📊 **Pre-Market Live Prices — 09:00 IST**\n\n⚠️ No live data available."

    lines = []
    lines.append("📊 **Pre-Market Live Prices — 09:00 IST**")
    lines.append("")

    lines.append("| Symbol | LTP | Change | Change% | VWAP | Vol | RSI |")
    lines.append("|:-------|----:|-------:|--------:|-----:|----:|----:|")

    for d in live_data:
        sym = d.get("symbol", "?")
        ltp = d.get("close")
        chg = d.get("change_abs")
        pct = d.get("change")
        vwap = d.get("VWAP")
        vol = d.get("volume")
        rsi = d.get("RSI")

        # None-safe formatting via fmt()
        chg_str = signed_pct(chg) if chg is not None else NA_DASH
        pct_str = fmt(pct, "+.2f") + "%" if pct is not None else NA_DASH
        vwap_str = fmt(vwap, ",.1f")
        vol_str = fmt(vol, ",.0f")
        rsi_str = fmt(rsi, ".1f")

        lines.append(
            f"| {sym} | {price_rupees(ltp, ',.1f')} | {chg_str} | {pct_str} | "
            f"{vwap_str} | {vol_str} | {rsi_str} |"
        )

    lines.append("")
    lines.append(f"_Tracked: {len(live_data)} symbols | Source: TradingView Scanner (real-time)_")
    lines.append("")
    lines.append("💡 **Commands:** `/intraday` for on-demand snapshot | `/track SYMBOL` to add")

    return "\n".join(lines)


async def send_premarket_report(app) -> dict:
    """
    Main entry: fetch live data for top 25 symbols from morning report and send ONLY to owner.
    Called by scheduler at 09:00 IST (Mon-Fri).
    """
    logger.info("Generating pre-market live prices report for top 25...")

    analysis_date = get_resolved_analysis_date()
    if not analysis_date:
        logger.warning("No analysis date available for pre-market report")
        return {"sent": 0, "failed": 0, "total": 0}

    analysis = get_latest_analysis(analysis_date)
    if not analysis:
        logger.warning("No analysis data available for pre-market report")
        return {"sent": 0, "failed": 0, "total": 0}

    top25 = sorted(analysis, key=lambda x: x.get("composite_score", 0), reverse=True)[:REPORT_TABLE_ROWS]
    symbols = [s["symbol"] for s in top25]

    logger.info("Fetching live prices for top %d symbols: %s", len(symbols), symbols)

    loop = asyncio.get_event_loop()
    live_data = await loop.run_in_executor(None, fetch_live_snapshot, symbols)

    if not live_data:
        logger.warning("No live data fetched for pre-market report")
        return {"sent": 0, "failed": 0, "total": 0}

    message = build_premarket_message(live_data)

    try:
        # Rich transport lives in telegram.rich (the bot.py shim was removed in
        # Phase 5). Imported lazily: a top-level import would create a cycle
        # (reports -> telegram.rich -> telegram/__init__ -> delivery -> reports).
        from marketmeter.telegram.rich import _send_rich_chunks, _needs_rich
        if _needs_rich(message):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, message)
        else:
            await app.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=message,
                parse_mode="Markdown",
            )
        logger.info("Sent pre-market report to owner")
        return {"sent": 1, "failed": 0, "total": 1}
    except Exception as e:
        logger.error("Failed to send pre-market to owner: %s", e)
        return {"sent": 0, "failed": 1, "total": 1}


__all__ = ["build_premarket_message", "send_premarket_report"]