# ruff: noqa: E701, E702  # pre-existing compact one-line style from original
"""
reports/premarket_combined — combined historical + live pre-market report.

Phase 4 split: merge_historical_live + build_combined_report + send_combined_premarket_report
from /premarket_combined_report.py moved here.

Phase 4 routes every formatter through marketmeter.reports.formatters and every
emoji/signal through marketmeter.reports.labels. None inputs now render as
the configured fallback instead of crashing.
"""
from __future__ import annotations

import asyncio
from datetime import date
from marketmeter.core.config import (
    OWNER_CHAT_ID, REPORT_TABLE_ROWS, REPORT_TOP_PICKS,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import get_latest_analysis, get_resolved_analysis_date
from marketmeter.sources.tradingview import fetch_live_snapshot
from marketmeter.reports.formatters import (
    fmt, signed_pct, gap_pct, vol_ratio, NA_EMDASH,
)
from marketmeter.reports.labels import (
    rsi_signal, gap_emoji, vol_emoji,
)

logger = get_logger(__name__)


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


def merge_historical_live(historical: list[dict], live_data: list[dict]) -> list[dict]:
    """Merge historical analysis data with live pre-market data."""
    live_lookup = {d["symbol"]: d for d in live_data}

    merged = []
    for h in historical:
        sym = h["symbol"]
        live = live_lookup.get(sym)

        merged_row = {
            "symbol": sym,
            "hist_close": h.get("close"),
            "hist_change": h.get("change"),
            "hist_vol": h.get("volume"),
            "hist_avg_vol": h.get("volume"),
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
            "live_close": live.get("close") if live else None,
            "live_change_abs": live.get("change_abs") if live else None,
            "live_change": live.get("change") if live else None,
            "live_volume": live.get("volume") if live else None,
            "live_vwap": live.get("VWAP") if live else None,
            "live_rsi": live.get("RSI") if live else None,
            "gap_pct": gap_pct(live.get("close"), h.get("close")) if live else None,
            "rsi_delta": (live.get("RSI") - h.get("rsi_14")) if live and h.get("rsi_14") else None,
            "vol_ratio": vol_ratio(live.get("volume"), h.get("volume")) if live else None,
        }
        merged.append(merged_row)
    return merged


def build_combined_report(merged: list[dict], analysis_date: date) -> str:
    """Build the combined pre-market report. None-safe."""
    if not merged:
        return "📊 **Pre-Market Combined Report**\n\n⚠️ No data available."

    lines = []
    lines.append(f"📊 **Pre-Market Combined Report — {analysis_date.strftime('%d %b %Y')} 09:00 IST**")
    lines.append("")
    lines.append(f"_Historical (EOD) + Live (TradingView) merged for {len(merged)} symbols._")
    lines.append("")

    # ── Top picks header ──
    lines.append(f"**🎯 Top {REPORT_TOP_PICKS} Picks — Historical vs Live**")
    lines.append("")

    # ── Merged table ──
    top_n = min(REPORT_TOP_PICKS, len(merged))
    lines.append("| # | Symbol | EOD Close | Live LTP | Gap% | RSI Δ | Vol Ratio | Rec |")
    lines.append("|:-:|:------|----------:|---------:|-----:|------:|----------:|:----|")

    for i, m in enumerate(merged[:top_n], 1):
        # hist_rec can be None (key present with a None recommendation); the
        # bare .get(key, default) returns None in that case, so coalesce with `or`.
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

    # ── Full table ──
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

    # ── Legend ──
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


async def send_combined_premarket_report(app) -> dict:
    """Entry point for the 09:00 combined report job."""
    logger.info("Generating combined pre-market report...")
    try:
        analysis_date = get_resolved_analysis_date()
        if not analysis_date:
            logger.warning("No analysis date; skipping combined report")
            return {"sent": 0, "failed": 1, "total": 1}

        historical = get_latest_analysis(analysis_date)
        if not historical:
            logger.warning("No historical analysis; skipping combined report")
            return {"sent": 0, "failed": 1, "total": 1}

        top = sorted(historical, key=lambda x: x.get("composite_score", 0), reverse=True)[:REPORT_TABLE_ROWS]
        symbols = [s["symbol"] for s in top]

        loop = asyncio.get_event_loop()
        live = await loop.run_in_executor(None, fetch_live_snapshot, symbols)
        if not live:
            logger.warning("No live data at 09:00")
            return {"sent": 0, "failed": 1, "total": 1}

        merged = merge_historical_live(top, live)
        report = build_combined_report(merged, analysis_date)

        # Rich transport from telegram.rich (shim removed in Phase 5); lazy to
        # avoid the reports -> telegram.rich -> telegram/__init__ -> delivery cycle.
        from marketmeter.telegram.rich import _send_rich_chunks, _needs_rich
        if _needs_rich(report):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, report)
        else:
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=report,
                                       parse_mode="Markdown")
        logger.info("Sent combined pre-market to owner")
        return {"sent": 1, "failed": 0, "total": 1}
    except Exception as e:
        logger.error("Combined pre-market failed: %s", e, exc_info=True)
        return {"sent": 0, "failed": 1, "total": 1}


__all__ = [
    "merge_historical_live",
    "build_combined_report",
    "send_combined_premarket_report",
    "HISTORICAL_COLS",
    "LIVE_COLS",
    "MERGED_TABLE_COLS",
]