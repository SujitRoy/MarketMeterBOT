# ruff: noqa: E701, E702  # pre-existing compact one-line style from original
"""
reports/morning — the 8:30 AM market report (the headline output of this bot).

Phase 4 split: the morning-report-specific functions from /report_generator.py
live here. The original `_detail_block`, `_render_morning_report`,
`_render_morning_report_single_pass`, and the helpers used only by the
morning report (`CATEGORY_CONFIG`, `RECOMMENDATION_ORDER`) all moved here.

CRITICAL Phase 4 fix: the original line 110 did `f"₹{close:,.2f}"` which
crashed on None close prices. The new version routes through
`formatters.price_rupees()` which is None-safe. This is what unblocks the
5 pre-existing test failures in test_fix_c.py and test_perf_smoke.py.

The single-pass render reads daily_analysis ONCE via get_analysis_aggregate
(BUG-C fix preserved verbatim from the original).
"""
from __future__ import annotations

from datetime import date  # noqa: F401
from typing import Optional

from marketmeter.core.time import today_ist
from marketmeter.core.config import (
    BOT_DISPLAY_NAME, REPORT_TOP_PICKS, REPORT_TABLE_ROWS,
)
from marketmeter.core.logging import get_logger
from marketmeter.db import (
    get_db_stats, get_resolved_analysis_date,
    get_cached_report, put_cached_report,
)
# Module-level reference for test patchability. Tests can do
# `patch.object(marketmeter.reports.morning, '_aggregate')` to mock the
# aggregate call. The renderer reads through this module attribute, not the
# function-local binding, so the mock is picked up.
from marketmeter.analysis import get_analysis_aggregate as _aggregate
from marketmeter.reports.formatters import (
    fmt, price_rupees, price_rupees_compact,
)
from marketmeter.reports.cache import _no_data_report

logger = get_logger(__name__)


# ── Inlined label helpers (from deleted labels.py) ──────────────────

def obv_label(obv_trend: float, volume: int) -> str:
    """One-word OBV trend: Surging / Rising / Steady / Falling / Weak / Flat."""
    if volume is None or volume <= 0:
        return "↔ Flat"
    if obv_trend is None:
        return "↔ Flat"
    pct = abs(obv_trend) / volume
    if obv_trend > 0:
        return "↑ Surging" if pct > 0.5 else ("↑ Rising" if pct > 0.1 else "↑ Steady")
    if obv_trend < 0:
        return "↓ Falling" if pct > 0.1 else "↓ Weak"
    return "↔ Flat"


def macd_label(macd_line, signal_line, hist=None) -> str:
    """Bullish / Bearish based on macd_line vs signal_line."""
    if macd_line is None or signal_line is None:
        return "-"
    return "Bullish" if macd_line > signal_line else "Bearish"


def bb_pos(close, bb_upper, bb_lower) -> str:
    """Where price sits within the Bollinger Band range."""
    if close is None or bb_upper is None or bb_lower is None or bb_upper == bb_lower:
        return "-"
    pct = (close - bb_lower) / (bb_upper - bb_lower)
    if pct >= 0.9:
        return "Near Upper"
    if pct >= 0.5:
        return "Mid-Upper"
    if pct >= 0.1:
        return "Mid-Lower"
    return "Near Lower"


def narrative(s: dict) -> str:
    """One-line narrative from actual indicator values."""
    parts = []
    rsi = s.get('rsi_14')
    adx = s.get('adx_14')
    rv  = s.get('rel_volume')
    macd_b = (s.get('macd_line') or 0) > (s.get('signal_line') or 0)
    sma20  = s.get('sma_20')
    close  = s.get('close')

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
    if sma20 and close is not None and close > sma20: parts.append("above SMA20")
    return "; ".join(parts[:4]) if parts else "Insufficient signal"


CATEGORY_CONFIG = {
    "STRONG_BUY":  {"emoji": "🟢", "label": "STRONG BUY",   "limit": 5},
    "BUY":         {"emoji": "🟢", "label": "BUY",           "limit": 10},
    "ACCUMULATE":  {"emoji": "🟡", "label": "ACCUMULATE",    "limit": 10},
    "WATCH":       {"emoji": "🔵", "label": "WATCH",          "limit": 10},
    "CAUTION":     {"emoji": "🟠", "label": "CAUTION",       "limit": 5},
    "AVOID":       {"emoji": "🔴", "label": "AVOID",         "limit": 5},
}

RECOMMENDATION_ORDER = ["STRONG_BUY", "BUY", "ACCUMULATE", "WATCH", "CAUTION", "AVOID"]


# ── Detail block for one top pick ────────────────────────────────────

def _detail_block(s: dict, rank: int) -> list[str]:
    """Full breakdown block for one top pick.

    Phase 4 fix: every price/number is routed through `fmt()` so None
    inputs render as the fallback glyph instead of crashing with
    "unsupported format string passed to NoneType.__format__".
    """
    lines = []
    sym   = s['symbol']
    close = s.get('close')  # may be None
    lines.append(f"**{rank}. {sym}**")
    # recommendation may be None (not just absent) — coalesce before replace().
    rec_hdr = (s.get('recommendation') or '').replace('_', ' ')
    lines.append(f"*{rec_hdr} · Score {s.get('composite_score','-')}*")
    lines.append("")

    # Price row — was the crash site at the original line 110.
    avg = s.get('avg_price')
    avg_str = price_rupees(avg) if avg is not None else "-"
    lines.append(f"• **Price:** {price_rupees(close)}  |  **AvgPrice\\*:** {avg_str}")

    # SMAs — None-safe via fmt()
    lines.append(
        f"• **SMA:** 20={fmt(s.get('sma_20'),',.1f')}  "
        f"50={fmt(s.get('sma_50'),',.1f')}  "
        f"100={fmt(s.get('sma_100'),',.1f')}  "
        f"200={fmt(s.get('sma_200'),',.1f')}"
    )
    # EMAs
    lines.append(
        f"• **EMA:** 20={fmt(s.get('ema_20'),',.1f')}  "
        f"50={fmt(s.get('ema_50'),',.1f')}  "
        f"100={fmt(s.get('ema_100'),',.1f')}  "
        f"200={fmt(s.get('ema_200'),',.1f')}"
    )
    # Momentum
    rsi = s.get('rsi_14'); adx = s.get('adx_14'); atr = s.get('atr_14')
    lines.append(
        f"• **RSI(14):** {fmt(rsi)}  |  **ADX(14):** {fmt(adx)}  |  **ATR(14):** {fmt(atr)}"
    )
    # MACD
    ml = s.get('macd_line'); sl = s.get('signal_line'); mh = s.get('macd_hist')
    lines.append(
        f"• **MACD:** Line={fmt(ml,'.4f')}  Signal={fmt(sl,'.4f')}  "
        f"Hist={fmt(mh,'.4f')}  ({macd_label(ml, sl, mh)})"
    )
    # Bollinger
    bu = s.get('bb_upper'); bl2 = s.get('bb_lower')
    lines.append(
        f"• **BB:** Upper={fmt(bu,',.1f')}  Lower={fmt(bl2,',.1f')}  "
        f"Pos={bb_pos(close, bu, bl2)}"
    )
    # Volume
    rv = s.get('rel_volume'); obv = s.get('obv_trend', 0); vol = s.get('volume', 1)
    lines.append(
        f"• **RelVol:** {fmt(rv,'.2f')}x  |  **OBV:** {obv_label(obv, vol)}"
    )
    lines.append(f"• _{narrative(s)}_")
    return lines


# ── Single-pass renderer ─────────────────────────────────────────────

def _render_morning_report_single_pass(analysis_date: date) -> str:
    """Render using one analysis-row fetch; outlook + grouping derived in memory."""
    # Lazy import for patchability: tests that mock get_analysis_aggregate via
    # patch.object(report_generator, 'get_analysis_aggregate') need the
    # lookup to happen at call time so the mock is picked up.
    grouped, outlook = _aggregate(analysis_date)
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
    for key in RECOMMENDATION_ORDER:
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
        close = s.get('close')  # may be None
        avg   = s.get('avg_price')
        rsi   = s.get('rsi_14')
        adx   = s.get('adx_14')
        rv    = s.get('rel_volume')
        obv   = s.get('obv_trend', 0)
        vol   = s.get('volume', 1)
        bu    = s.get('bb_upper'); bl2 = s.get('bb_lower')
        ml    = s.get('macd_line'); sl2 = s.get('signal_line'); mh = s.get('macd_hist')
        rec   = (s.get('recommendation') or '').replace('_', ' ')  # None-safe coalesce
        # None-safe rendering: every value goes through fmt() or
        # the corresponding label helper. The original code did
        # `f"₹{close:,.0f}"` directly which crashed on None.
        lines.append(
            f"| {i} | {s['symbol']} "
            f"| {price_rupees_compact(close)} "
            f"| {price_rupees_compact(avg) if avg is not None else '-'} "
            f"| {fmt(rsi,'.0f')} "
            f"| {fmt(adx,'.0f')} "
            f"| {fmt(rv,'.1f')}x "
            f"| {obv_label(obv, vol)} "
            f"| {bb_pos(close, bu, bl2)} "
            f"| {macd_label(ml, sl2, mh)} "
            f"| {rec} |"
        )
    lines.append("")
    lines.append("_\\*AvgPrice = NSE's published average traded price for the day "
                 "(full-day average, not intraday VWAP)_")
    lines.append("")

    # ── Column legend ──
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


def _render_morning_report(analysis_date: date) -> str:
    """Curated 3-pick + 10-row scan report in Rich Markdown.

    BUG-C (single-pass): kept verbatim from the original. The morning
    report calls get_analysis_aggregate which reads daily_analysis once
    and returns (grouped, outlook) — half the DB cost of the old code.
    """
    return _render_morning_report_single_pass(analysis_date)


def generate_morning_report(analysis_date: Optional[date] = None,
                            use_cache: bool = True) -> str:
    """Generate the full morning analysis report. Cached (~0.08ms vs ~1.1s render)."""
    if analysis_date is None:
        analysis_date = get_resolved_analysis_date()
        if analysis_date is None:
            return _no_data_report(today_ist())

    if use_cache:
        cached = get_cached_report('morning', analysis_date)
        if cached is not None:
            logger.debug("Report cache hit for %s", analysis_date)
            return cached

    report = _render_morning_report(analysis_date)

    # Only cache real reports. Caching a "no data" notice would pin it for the
    # whole retention window.
    if use_cache and "No analysis data available" not in report:
        put_cached_report('morning', analysis_date, report)
        logger.info("Report cached for %s (%d chars)", analysis_date, len(report))

    return report


__all__ = [
    "generate_morning_report",
    "_render_morning_report",
    "_render_morning_report_single_pass",
    "_detail_block",
    "CATEGORY_CONFIG",
    "RECOMMENDATION_ORDER",
]