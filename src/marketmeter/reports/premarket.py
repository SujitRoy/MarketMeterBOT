"""
reports/premarket — unified pre-market reports (live, open cross-check, combined).

Three modes:
- "live":        09:00 IST live prices for top symbols (premarket_live)
- "open":        09:15 IST cross-check EOD vs live (premarket_open)
- "combined":    09:00 IST historical + live merged (premarket_combined)
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal, Optional

from marketmeter.core.config import (
    OWNER_CHAT_ID, REPORT_TABLE_ROWS, REPORT_TOP_PICKS,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import get_latest_analysis, get_resolved_analysis_date
from marketmeter.sources.tradingview import fetch_live_snapshot
from marketmeter.reports.formatters import (
    fmt, price_rupees, signed_pct, gap_pct, vol_ratio, NA_EMDASH,
)

logger = get_logger(__name__)


# ── Inlined label helpers (from deleted labels.py) ──────────────────

def rsi_signal(rsi: Optional[float]) -> str:
    """RSI signal emoji. 70+ red, 60+ green, 40+ yellow, 30+ blue, else red."""
    if rsi is None:
        return NA_EMDASH
    if rsi >= 70:
        return "🔴"
    if rsi >= 60:
        return "🟢"
    if rsi >= 40:
        return "🟡"
    if rsi >= 30:
        return "🔵"
    return "🔴"


def gap_emoji(gap: Optional[float]) -> str:
    """Gap emoji by magnitude of live-vs-EOD gap."""
    if gap is None:
        return NA_EMDASH
    if gap >= 2:
        return "🚀"
    if gap >= 1:
        return "📈"
    if gap >= -1:
        return "➡️"
    if gap >= -2:
        return "📉"
    return "💥"


def vol_emoji(ratio: Optional[float]) -> str:
    """Volume-ratio emoji. 2x+ fire, 1x+ chart, else sleeper."""
    if ratio is None:
        return NA_EMDASH
    if ratio >= 2:
        return "🔥"
    if ratio >= 1:
        return "📊"
    return "💤"


def verdict(gap: Optional[float], rec: str) -> str:
    """Mark morning-vs-open agreement."""
    if gap is None:
        return "·"
    bullish = rec in ("STRONG_BUY", "BUY", "ACCUMULATE")
    if bullish and gap >= 0.5:
        return "✓"
    if bullish and gap <= -0.5:
        return "✗"
    return "·"


PremarketMode = Literal["live", "open", "combined"]


# ─── Shared helpers ─────────────────────────────────────────────────

async def _fetch_live(symbols: list[str]) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_live_snapshot, symbols)


async def _send_report(app, message: str) -> dict:
    """Send via Rich transport, return send stats."""
    try:
        from marketmeter.telegram.rich import _send_rich_chunks, _needs_rich
        if _needs_rich(message):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, message)
        else:
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=message, parse_mode="Markdown")
        return {"sent": 1, "failed": 0, "total": 1}
    except Exception as e:
        logger.error("Failed to send pre-market report: %s", e)
        return {"sent": 0, "failed": 1, "total": 1}


# ─── Mode: LIVE (09:00) ────────────────────────────────────────────

def _build_live_message(live_data: list[dict]) -> str:
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

        chg_str = signed_pct(chg) if chg is not None else NA_EMDASH
        pct_str = fmt(pct, "+.2f") + "%" if pct is not None else NA_EMDASH
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


async def _send_live(app) -> dict:
    logger.info("Generating pre-market live prices report for top 25...")

    analysis_date = get_resolved_analysis_date()
    if not analysis_date:
        return {"sent": 0, "failed": 1, "total": 1}

    analysis = get_latest_analysis(analysis_date)
    if not analysis:
        return {"sent": 0, "failed": 1, "total": 1}

    top25 = sorted(analysis, key=lambda x: x.get("composite_score", 0), reverse=True)[:REPORT_TABLE_ROWS]
    symbols = [s["symbol"] for s in top25]

    live_data = await _fetch_live(symbols)
    if not live_data:
        return {"sent": 0, "failed": 1, "total": 1}

    message = _build_live_message(live_data)
    return await _send_report(app, message)


# ─── Mode: OPEN (09:15) ────────────────────────────────────────────

OPEN_REPORT_TOP_N = 15


def _select_top(historical: list[dict]) -> list[dict]:
    top = sorted(historical, key=lambda x: x.get('composite_score', 0), reverse=True)
    return top[:OPEN_REPORT_TOP_N]


def _build_open_message(historical: list[dict], live_data: list[dict], analysis_date: date) -> str:
    historical = _select_top(historical)
    live_lookup = {d["symbol"]: d for d in live_data}

    lines = []
    lines.append(f"🧭 **Market-Open Cross-Check — {analysis_date.strftime('%d %b %Y')} 09:15 IST**")
    lines.append("")
    live_n = sum(1 for h in historical if h["symbol"] in live_lookup)
    lines.append(f"⏰ **Snapshot:** 09:15 IST | Live: {live_n}/{len(historical)} symbols")
    lines.append("")

    lines.append("| Sym | EOD Close | 9:15 LTP | Gap% | Live RSI | Live Vol | Rec | Call |")
    lines.append("|:----|----------:|---------:|-----:|---------:|---------:|:----|:---:|")

    pos = neg = ok = 0
    for h in historical:
        sym = h["symbol"]
        live = live_lookup.get(sym)
        eod_close = h.get("close")
        rec = (h.get("recommendation") or NA_EMDASH).replace('_', ' ')
        ltp = live.get("close") if live else None
        lrsi = live.get("RSI") if live else None
        lvol = live.get("volume") if live else None
        g = gap_pct(ltp, eod_close)
        v = verdict(g, rec)
        if g is not None:
            if g >= 0.5:
                pos += 1
            elif g <= -0.5:
                neg += 1
            if v == "✓":
                ok += 1
        lines.append(
            f"| {sym} | {fmt(eod_close, ',.1f')} | {fmt(ltp, ',.1f')} | {signed_pct(g)} | "
            f"{fmt(lrsi, '.1f')} | {fmt(lvol, ',.0f')} | {rec} | {v} |"
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


async def _send_open(app) -> dict:
    logger.info("Generating 09:15 market-open cross-check report...")
    analysis_date = get_resolved_analysis_date()
    if not analysis_date:
        return {"sent": 0, "failed": 1, "total": 1}

    analysis = get_latest_analysis(analysis_date)
    if not analysis:
        return {"sent": 0, "failed": 1, "total": 1}

    top = _select_top(analysis)
    symbols = [s["symbol"] for s in top]
    live = await _fetch_live(symbols)
    if not live:
        return {"sent": 0, "failed": 1, "total": 1}

    report = _build_open_message(top, live, analysis_date)
    return await _send_report(app, report)


# ─── Mode: COMBINED (09:00) ────────────────────────────────────────

def _build_combined_message(merged: list[dict], analysis_date: date) -> str:
    if not merged:
        return "📊 **Pre-Market Combined Report**\n\n⚠️ No data available."

    lines = []
    lines.append(f"📊 **Pre-Market Combined Report — {analysis_date.strftime('%d %b %Y')} 09:00 IST**")
    lines.append("")
    lines.append(f"_Historical (EOD) + Live (TradingView) merged for {len(merged)} symbols._")
    lines.append("")

    lines.append(f"**🎯 Top {REPORT_TOP_PICKS} Picks — Historical vs Live**")
    lines.append("")

    top_n = min(REPORT_TOP_PICKS, len(merged))
    lines.append("| # | Symbol | EOD Close | Live LTP | Gap% | RSI Δ | Vol Ratio | Rec |")
    lines.append("|:-:|:------|----------:|---------:|-----:|------:|----------:|:----|")

    for i, m in enumerate(merged[:top_n], 1):
        hist_rec = (m.get('hist_rec') or NA_EMDASH).replace('_', ' ')
        lines.append(
            f"| {i} | {m['symbol']} "
            f"| ₹{fmt(m.get('hist_close'), ',.2f')} "
            f"| ₹{fmt(m.get('live_close'), ',.2f')} "
            f"| {gap_emoji(m.get('gap_pct'))} {signed_pct(m.get('gap_pct'))} "
            f"| {fmt(m.get('rsi_delta'), '+.1f')} "
            f"| {vol_emoji(m.get('vol_ratio'))} {fmt(m.get('vol_ratio'), '.2f')}x "
            f"| {rsi_signal(m.get('hist_rsi'))} {hist_rec} |"
        )
    lines.append("")

    lines.append(f"**📋 Full Scan — Top {REPORT_TABLE_ROWS}**")
    lines.append("")
    lines.append("| Symbol | EOD Chg% | Live Chg% | EOD RSI | Live RSI | VWAP | EOD Vol | Live Vol |")
    lines.append("|:-------|---------:|----------:|--------:|---------:|-----:|--------:|---------:|")
    for m in merged[:REPORT_TABLE_ROWS]:
        lines.append(
            f"| {m['symbol']} "
            f"| {signed_pct(m.get('hist_change'))} "
            f"| {signed_pct(m.get('live_change'))} "
            f"| {fmt(m.get('hist_rsi'), '.1f')} "
            f"| {fmt(m.get('live_rsi'), '.1f')} "
            f"| ₹{fmt(m.get('live_vwap'), ',.2f')} "
            f"| {fmt(m.get('hist_vol'), ',.0f')} "
            f"| {fmt(m.get('live_volume'), ',.0f')} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Legend:**")
    lines.append("• Gap emoji: 🚀 ≥2% | 📈 ≥1% | ➡️ flat | 📉 ≥-2% | 💥 <-2%")
    lines.append("• Vol emoji: 🔥 ≥2x | 📊 ≥1x | 💤 <1x")
    lines.append("• RSI signal: 🔴 ≥70 | 🟢 ≥60 | 🟡 ≥40 | 🔵 ≥30 | 🔴 <30")
    lines.append("")
    lines.append("_Source: EOD BhavCopy analysis + Live TradingView @ 09:00 IST._")
    lines.append("⚠️ Indicative only. Not financial advice.")
    return "\n".join(lines)


def _merge_historical_live(historical: list[dict], live_data: list[dict]) -> list[dict]:
    live_lookup = {d["symbol"]: d for d in live_data}

    merged = []
    for h in historical:
        sym = h["symbol"]
        live = live_lookup.get(sym)

        merged.append({
            "symbol": sym,
            "hist_close": h.get("close"),
            "hist_change": h.get("change"),
            "hist_vol": h.get("volume"),
            "hist_rsi": h.get("rsi_14"),
            "hist_rec": h.get("recommendation"),
            "hist_score": h.get("composite_score"),
            "live_close": live.get("close") if live else None,
            "live_change": live.get("change") if live else None,
            "live_volume": live.get("volume") if live else None,
            "live_vwap": live.get("VWAP") if live else None,
            "live_rsi": live.get("RSI") if live else None,
            "gap_pct": gap_pct(live.get("close"), h.get("close")) if live else None,
            "rsi_delta": (live.get("RSI") - h.get("rsi_14")) if live and h.get("rsi_14") else None,
            "vol_ratio": vol_ratio(live.get("volume"), h.get("volume")) if live else None,
        })
    return merged


async def _send_combined(app) -> dict:
    logger.info("Generating combined pre-market report...")
    analysis_date = get_resolved_analysis_date()
    if not analysis_date:
        return {"sent": 0, "failed": 1, "total": 1}

    historical = get_latest_analysis(analysis_date)
    if not historical:
        return {"sent": 0, "failed": 1, "total": 1}

    top = sorted(historical, key=lambda x: x.get("composite_score", 0), reverse=True)[:REPORT_TABLE_ROWS]
    symbols = [s["symbol"] for s in top]
    live = await _fetch_live(symbols)
    if not live:
        return {"sent": 0, "failed": 1, "total": 1}

    merged = _merge_historical_live(top, live)
    report = _build_combined_message(merged, analysis_date)
    return await _send_report(app, report)


# ─── Public entry point ────────────────────────────────────────────

async def send_premarket_report(app, mode: PremarketMode = "live") -> dict:
    """
    Unified entry point for all pre-market report modes.

    Args:
        app: Bot application
        mode: "live" (09:00), "open" (09:15), or "combined" (09:00 merged)
    """
    if mode == "live":
        return await _send_live(app)
    elif mode == "open":
        return await _send_open(app)
    elif mode == "combined":
        return await _send_combined(app)
    else:
        raise ValueError(f"Unknown premarket mode: {mode}")


__all__ = [
    "send_premarket_report",
    "OPEN_REPORT_TOP_N",
]