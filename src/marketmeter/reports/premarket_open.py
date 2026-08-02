# ruff: noqa: E701, E702  # pre-existing compact one-line style from original
"""
reports/premarket_open — 09:15 IST market-open cross-check report.

Phase 4 split: build_open_crosscheck + send_open_crosscheck_report from
/premarket_open_report.py moved here.

Phase 4 also fixes a pre-existing duplicate-function bug in the original:
there were TWO `build_open_crosscheck` definitions and the first was a
stub that silently shadowed by nothing. The stub is gone; only the real
implementation remains.

Phase 4 routes all formatting through marketmeter.reports.formatters
so None inputs render as '-' instead of crashing.
"""
from __future__ import annotations

import asyncio
from datetime import date

from marketmeter.core.config import OWNER_CHAT_ID
from marketmeter.core.logging import get_logger
from marketmeter.sources.tradingview import fetch_live_snapshot
from marketmeter.reports.formatters import (
    fmt, signed_pct, gap_pct, NA_EMDASH,
)
from marketmeter.reports.labels import verdict

# Test-back-compat: allow patching these functions via the shim module

logger = get_logger(__name__)

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
        rec = h.get("recommendation") or NA_EMDASH  # None-safe coalesce
        ltp = live.get("close") if live else None
        lrsi = live.get("RSI") if live else None
        lvol = live.get("volume") if live else None
        g = gap_pct(ltp, eod_close)
        v = verdict(g, rec)
        if g is not None:
            if g >= 0.5: pos += 1
            elif g <= -0.5: neg += 1
            if v == "✓": ok += 1
        lines.append(
            f"| {sym} | {fmt(eod_close, ',.1f')} | {fmt(ltp, ',.1f')} | {signed_pct(g)} | "
            f"{fmt(lrsi, '.1f')} | {fmt(lvol, ',.0f')} | {rec.replace('_',' ')} | {v} |"
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
        # Lazy db import (function-level binding preserves runtime patchability).
        # The premarket_open_report shim was removed in Phase 6 — importing it
        # raised ModuleNotFoundError, so the 09:15 cross-check silently never ran.
        from marketmeter.db import get_resolved_analysis_date, get_latest_analysis
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

        # Rich transport from telegram.rich (shim removed); lazy to avoid the
        # reports -> telegram.rich -> telegram/__init__ -> delivery -> reports cycle.
        from marketmeter.telegram.rich import _send_rich_chunks, _needs_rich
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


__all__ = ["build_open_crosscheck", "send_open_crosscheck_report", "OPEN_REPORT_TOP_N"]