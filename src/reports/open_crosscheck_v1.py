"""
Market-Open Cross-Check report — 09:15 IST (Mon-Fri), owner-only.

Merges the EOD analysis (the same data behind the 08:30 MarketMeter Morning Report)
with live 09:15 prices so the owner can validate the morning calls against the
actual open. Distinct from the 09:00 pre-market snapshot (which shows pre-open):
this reports the real open ~15 minutes into the session.

Design decisions:
- Top-N by composite_score (matches the morning report's ranking of "best setups").
- Sent to OWNER only; broadcast to subscribers is a later, explicit choice.
- Gap% is EOD-close -> 9:15 live; Score is a simple direction tally of the top picks.
- Live data comes from the same TradingView scanner used by the pre-market report.
"""
import asyncio
import logging
from datetime import date
from typing import Optional

from src.core.config import OWNER_CHAT_ID, REPORT_TABLE_ROWS
from src.database import get_latest_analysis, get_resolved_analysis_date
from intraday_fetcher import fetch_live_snapshot
from src.bot.bot import _send_rich_chunks, _needs_rich

logger = logging.getLogger(__name__)

# Top picks to cross-check. 15 keeps the table readable inside one message.
OPEN_REPORT_TOP_N = 15


def _select_top(historical: list[dict]) -> list[dict]:
    """Top-N by composite score. min(len, N) so small test fixtures survive."""
    top = sorted(historical, key=lambda x: x.get('composite_score', 0), reverse=True)
    return top[:OPEN_REPORT_TOP_N]


def build_open_crosscheck(historical: list[dict], live_data: list[dict],
                          analysis_date: date) -> str:
    """Build the 09:15 cross-check Rich Markdown. Top-N merged + scorecard."""
    historical = _select_top(historical)
    live_lookup = {d["symbol"]: d for d in live_data}


def _gap(live: Optional[float], eod: Optional[float]) -> Optional[float]:
    """Live-vs-EOD percentage move."""
    if live is None or eod is None or eod == 0:
        return None
    return (live - eod) / eod * 100.0


def _fmt(v, d=2, na="—"):
    if v is None:
        return na
    try:
        return format(v, f",.{d}f")
    except (ValueError, TypeError):
        return na


def _signed_pct(v, d=2):
    if v is None:
        return "—"
    return f"{v:+.{d}f}%"


def _verdict(gap: Optional[float], rec: str) -> str:
    """
    Did the morning call work at the open?
    Bullish call (STRONG_BUY/BUY/ACCUMULATE) + gap up   -> ✓ on track
    Bullish call + big gap down                          -> ✗ fading
    Anything else                                        -> · neutral
    """
    if gap is None:
        return "·"
    bullish = rec in ("STRONG_BUY", "BUY", "ACCUMULATE")
    if bullish and gap >= 0.5:
        return "✓"
    if bullish and gap <= -0.5:
        return "✗"
    return "·"


def build_open_crosscheck(historical: list[dict], live_data: list[dict],
                          analysis_date: date) -> str:
    """Build the 09:15 cross-check Rich Markdown. Top-N merged + scorecard."""
    live_lookup = {d["symbol"]: d for d in live_data}

    lines = []
    lines.append(f"🧭 **Market-Open Cross-Check — {analysis_date.strftime('%d %b %Y')} 09:15 IST**")
    lines.append("")
    live_n = sum(1 for h in historical if h["symbol"] in live_lookup)
    lines.append(f"⏰ **Snapshot:** 09:15 IST | Live: {live_n}/{len(historical)} symbols")
    lines.append("")

    # ── Merged table ──
    lines.append("| Sym | EOD Close | 9:15 LTP | Gap% | Live RSI | Live Vol | Rec | Call |")
    lines.append("|:----|----------:|---------:|-----:|---------:|---------:|:----|:---:|")

    pos = neg = ok = 0
    for h in historical:
        sym = h["symbol"]
        live = live_lookup.get(sym)
        eod_close = h.get("close")
        rec = h.get("recommendation", "—")
        ltp = live.get("close") if live else None
        lrsi = live.get("RSI") if live else None
        lvol = live.get("volume") if live else None
        g = _gap(ltp, eod_close)
        v = _verdict(g, rec)
        if g is not None:
            if g >= 0.5: pos += 1
            elif g <= -0.5: neg += 1
            if v == "✓": ok += 1
        lines.append(
            f"| {sym} | {_fmt(eod_close,1)} | {_fmt(ltp,1)} | {_signed_pct(g)} | "
            f"{_fmt(lrsi,1)} | {_fmt(lvol,0)} | {rec.replace('_',' ')} | {v} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**📊 Open scorecard:** {pos} gapping up · {neg} gapping down "
                 f"· {ok} morning bullish calls on track")
    lines.append("")
    lines.append("_Source: EOD BhavCopy analysis (08:30 morning report) + Live TradingView @ 09:15._")
    lines.append("⚠️ Indicative only. Not financial advice.")
    return "\n".join(lines)


async def send_open_crosscheck_report(app) -> dict:
    """Entry point for the 09:15 IST job. Owner-only; returns send stats."""
    logger.info("Generating 09:15 market-open cross-check report...")
    try:
        analysis_date = get_resolved_analysis_date()
        if not analysis_date:
            logger.warning("No analysis date; skipping open cross-check")
            return {"sent": 0, "failed": 1, "total": 1}

        analysis = get_latest_analysis(analysis_date)
        if not analysis:
            logger.warning("No analysis rows; skipping open cross-check")
            return {"sent": 0, "failed": 1, "total": 1}

        top = _select_top(analysis)
        symbols = [s["symbol"] for s in top]

        loop = asyncio.get_event_loop()
        live = await loop.run_in_executor(None, fetch_live_snapshot, symbols)
        if not live:
            logger.warning("No live data at 09:15")
            return {"sent": 0, "failed": 1, "total": 1}

        report = build_open_crosscheck(top, live, analysis_date)

        if _needs_rich(report):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, report)
        else:
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=report,
                                       parse_mode="Markdown")
        logger.info("Sent 09:15 open cross-check to owner")
        return {"sent": 1, "failed": 0, "total": 1}
    except Exception as e:
        logger.error("Open cross-check failed: %s", e, exc_info=True)
        return {"sent": 0, "failed": 1, "total": 1}
