"""
Pre-Market Live Prices Report
Fetches live NSE prices via TradingView at 9:00 AM and sends to owner + subscribers.
"""
import asyncio
import logging
from typing import Optional

from config import (
    OWNER_CHAT_ID, INTRADAY_SYMBOLS,
    TELEGRAM_API_BASE_URL,
)
from database import get_active_subscribers, get_tracked_symbols, add_tracked_symbol
from bot import _send_rich_chunks, _needs_rich
from intraday_fetcher import fetch_live_snapshot

logger = logging.getLogger(__name__)


def build_premarket_message(live_data: list[dict]) -> str:
    """Build Rich Markdown message with live prices."""
    if not live_data:
        return "📊 **Pre-Market Live Prices — 09:00 IST**\n\n⚠️ No live data available."

    lines = []
    lines.append("📊 **Pre-Market Live Prices — 09:00 IST**")
    lines.append("")

    # Table header
    lines.append("| Symbol | LTP | Change | Change% | VWAP | Vol | RSI |")
    lines.append("|:-------|----:|-------:|--------:|-----:|----:|----:|")

    for d in live_data:
        sym = d.get("symbol", "?")
        ltp = d.get("close", 0)
        chg = d.get("change_abs", 0)
        pct = d.get("change", 0)
        vwap = d.get("VWAP", 0)
        vol = d.get("volume", 0)
        rsi = d.get("RSI", 0)

        chg_str = f"{chg:+.2f}" if chg else "-"
        pct_str = f"{pct:+.2f}%" if pct else "-"
        vwap_str = f"{vwap:,.1f}" if vwap else "-"
        vol_str = f"{vol:,.0f}" if vol else "-"
        rsi_str = f"{rsi:.1f}" if rsi else "-"

        lines.append(f"| {sym} | ₹{ltp:,.1f} | {chg_str} | {pct_str} | {vwap_str} | {vol_str} | {rsi_str} |")

    lines.append("")
    lines.append(f"_Tracked: {len(live_data)} symbols | Source: TradingView Scanner (real-time)_")
    lines.append("")
    lines.append("💡 **Commands:** `/intraday` for on-demand snapshot | `/track SYMBOL` to add")

    return "\n".join(lines)


async def send_premarket_report(app):
    """
    Main entry: fetch live data and broadcast to owner + subscribers.
    Called by scheduler at 09:00 IST (Mon-Fri).
    """
    logger.info("Generating pre-market live prices report...")

    # Combine INTRADAY_SYMBOLS from config + tracked symbols from DB
    symbols = list(INTRADAY_SYMBOLS)
    tracked = get_tracked_symbols()
    for t in tracked:
        if t['symbol'] not in symbols:
            symbols.append(t['symbol'])

    logger.info("Fetching live prices for %d symbols", len(symbols))

    # Fetch live data (runs in executor to avoid blocking)
    loop = asyncio.get_event_loop()
    live_data = await loop.run_in_executor(None, fetch_live_snapshot, symbols)

    if not live_data:
        logger.warning("No live data fetched for pre-market report")
        return {"sent": 0, "failed": 0, "total": 0}

    # Build message
    message = build_premarket_message(live_data)

    # Send to owner first
    try:
        if _needs_rich(message):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, message)
        else:
            await app.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=message,
                parse_mode="Markdown",
            )
        logger.info("Sent pre-market report to owner")
    except Exception as e:
        logger.error("Failed to send pre-market to owner: %s", e)

    # Broadcast to subscribers
    subscribers = get_active_subscribers()
    total = len(subscribers)
    sent = 0
    failed = 0

    for sub in subscribers:
        chat_id = sub['chat_id']
        try:
            if _needs_rich(message):
                await _send_rich_chunks(app.bot, chat_id, message, disable_notification=True)
            else:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown",
                    disable_notification=True,
                )
            sent += 1
        except Exception as e:
            logger.warning("Failed to send pre-market to %d: %s", chat_id, e)
            failed += 1

        # Rate limit
        if sent % 25 == 0:
            await asyncio.sleep(1)

    logger.info("Pre-market broadcast complete: %d sent, %d failed, %d total", sent, failed, total)
    return {"sent": sent, "failed": failed, "total": total}


if __name__ == "__main__":
    # Manual test
    import sys
    sys.path.insert(0, ".")
    from bot import create_application
    import os
    os.environ.setdefault("MARKETMETER_BOT_TOKEN", "dummy")
    os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "123456")

    app = create_application()
    import asyncio
    result = asyncio.run(send_premarket_report(app))
    print(result)