"""
Morning Report Module
Generates the 08:30 AM morning analysis report.
"""
import logging
from datetime import date

from src.analysis import get_analysis_aggregate
from src.core.config import (
    BOT_DISPLAY_NAME,
    REPORT_TABLE_ROWS,
    REPORT_TOP_PICKS,
)
from src.database.repositories import (
    SyncReadRepository,
)
from src.reports.base import BaseReport, ReportContext, ReportResult
from src.reports.registry import register_report

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


# ── Helpers ─────────────────────────────────────────────────────────

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
    lines = []
    sym   = s['symbol']
    close = s.get('close', 0)
    lines.append(f"**{rank}. {sym}**")
    lines.append(f"*{s.get('recommendation','').replace('_',' ')} · Score {s.get('composite_score','-')}*")
    lines.append("")

    avg = s.get('avg_price')
    avg_str = f"₹{avg:,.2f}" if avg else "-"
    lines.append(f"• **Price:** ₹{close:,.2f}  |  **AvgPrice\\*:** {avg_str}")

    lines.append(
        f"• **SMA:** 20={_fmt(s.get('sma_20'),',.1f')}  "
        f"50={_fmt(s.get('sma_50'),',.1f')}  "
        f"100={_fmt(s.get('sma_100'),',.1f')}  "
        f"200={_fmt(s.get('sma_200'),',.1f')}"
    )
    lines.append(
        f"• **EMA:** 20={_fmt(s.get('ema_20'),',.1f')}  "
        f"50={_fmt(s.get('ema_50'),',.1f')}  "
        f"100={_fmt(s.get('ema_100'),',.1f')}  "
        f"200={_fmt(s.get('ema_200'),',.1f')}"
    )
    rsi = s.get('rsi_14'); adx = s.get('adx_14'); atr = s.get('atr_14')
    lines.append(
        f"• **RSI(14):** {_fmt(rsi)}  |  **ADX(14):** {_fmt(adx)}  |  **ATR(14):** {_fmt(atr)}"
    )
    ml = s.get('macd_line'); sl = s.get('signal_line'); mh = s.get('macd_hist')
    lines.append(
        f"• **MACD:** Line={_fmt(ml,'.4f')}  Signal={_fmt(sl,'.4f')}  "
        f"Hist={_fmt(mh,'.4f')}  ({_macd_label(ml,sl,mh)})"
    )
    bu = s.get('bb_upper'); bl2 = s.get('bb_lower')
    lines.append(
        f"• **BB:** Upper={_fmt(bu,',.1f')}  Lower={_fmt(bl2,',.1f')}  "
        f"Pos={_bb_pos(close,bu,bl2)}"
    )
    rv = s.get('rel_volume'); obv = s.get('obv_trend', 0); vol = s.get('volume', 1)
    lines.append(
        f"• **RelVol:** {_fmt(rv,'.2f')}x  |  **OBV:** {_obv_label(obv, vol)}"
    )
    lines.append(f"• _{_narrative(s)}_")
    return lines


@register_report("morning")
class MorningReport(BaseReport):
    """Morning analysis report (08:30 IST)."""

    kind = "morning"
    name = "Morning Report"
    description = "Daily technical analysis report sent at 08:30 IST"

    def build(self) -> ReportResult:
        """Build the morning report using single-pass fetch."""
        analysis_date = self.context.analysis_date

        # Single-pass: read analysis rows once
        grouped, outlook = get_analysis_aggregate(analysis_date)

        total_stocks = sum(len(v) for v in grouped.values())
        if total_stocks == 0:
            return ReportResult(
                content=self._no_data_report(analysis_date),
                chunks=[self._no_data_report(analysis_date)]
            )

        # All stocks ranked by composite_score desc
        all_stocks = sorted(
            [s for v in grouped.values() for s in v],
            key=lambda x: x.get('composite_score', 0), reverse=True
        )

        lines = []

        # Header
        lines.append(f"📊 **{BOT_DISPLAY_NAME} Morning Report — {analysis_date.strftime('%d %b %Y')}**")
        lines.append("")

        # Market Outlook
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

        # Category tally
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

        # Top Picks
        top_n = min(REPORT_TOP_PICKS, len(all_stocks))
        lines.append(f"**🎯 Top {top_n} Picks**")
        lines.append("")
        for i, s in enumerate(all_stocks[:top_n], 1):
            lines.extend(_detail_block(s, i))
            lines.append("")

        lines.append("---")
        lines.append("")

        # Scan Table
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

        # Column Guide (collapsible)
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

        # Data Summary (collapsible)
        lines.append("---")
        lines.append("")
        lines.append("<details><summary>**📌 Data Summary**</summary>")
        lines.append("")
        from src.database.repositories import StatsRepository
        db_stats = StatsRepository().get_stats()
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

        content = "\n".join(lines)
        chunks = self.chunk_message(content)

        return ReportResult(content=content, chunks=chunks)

    def _no_data_report(self, analysis_date: date) -> str:
        return f"""📊 *{BOT_DISPLAY_NAME} Morning Report — {analysis_date.strftime('%d %b %Y')}*

⚠️ *No analysis data available yet.*

Possible reasons:
• Initial data sync is still in progress
• Today is a market holiday
• Sync failed — check /status

💡 The bot syncs data daily at 6:30 PM IST.
Reports are generated automatically at 8:00 AM IST.

_Use /status to check sync progress._"""


def generate_morning_report(analysis_date: date | None = None, use_cache: bool = True) -> str:
    """Convenience function for backward compatibility."""

    if analysis_date is None:
        sync_repo = SyncReadRepository()
        analysis_date = sync_repo.get_last_synced_date() or date.today()

    context = ReportContext(
        analysis_date=analysis_date,
        grouped_data={},
        outlook={},
    )

    report = MorningReport(context)
    result = report.build()
    return result.content
