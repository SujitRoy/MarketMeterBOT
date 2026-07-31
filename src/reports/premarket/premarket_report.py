"""
Pre-Market Reports Module
Generates the 09:00 AM combined report and 09:15 AM open cross-check.
"""
import logging

from src.core.config import OWNER_CHAT_ID
from src.data.transformers import (
    merge_historical_live,
)
from src.reports.base import BaseReport, ReportContext, ReportResult
from src.reports.registry import register_report

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────

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


def _gap_emoji(gap: float | None) -> str:
    if gap is None:
        return "—"
    if gap >= 2: return "🚀"
    if gap >= 1: return "📈"
    if gap >= -1: return "➡️"
    if gap >= -2: return "📉"
    return "💥"


def _rsi_emoji(rsi: float | None) -> str:
    if rsi is None: return "—"
    if rsi >= 70: return "🔴"
    if rsi >= 60: return "🟢"
    if rsi >= 40: return "🟡"
    if rsi >= 30: return "🔵"
    return "🔴"


def _vol_emoji(ratio: float | None) -> str:
    if ratio is None: return "—"
    if ratio >= 2: return "🔥"
    if ratio >= 1: return "📊"
    return "💤"


def _rec_emoji(rec: str) -> str:
    return {
        "STRONG_BUY": "🟢🟢", "BUY": "🟢", "ACCUMULATE": "🟡",
        "WATCH": "🔵", "CAUTION": "🟠", "AVOID": "🔴",
    }.get(rec, "⚪")


# ── 09:15 Open Cross-Check Report ───────────────────────────────────

@register_report("open_crosscheck")
class OpenCrossCheckReport(BaseReport):
    """09:15 Market-Open Cross-Check Report (Owner only)."""

    kind = "open_crosscheck"
    name = "Market-Open Cross-Check"
    description = "09:15 IST cross-check merging EOD analysis with live open prices"
    OPEN_REPORT_TOP_N = 15

    def _select_top(self, historical: list[dict]) -> list[dict]:
        top = sorted(historical, key=lambda x: x.get('composite_score', 0), reverse=True)
        return top[:self.OPEN_REPORT_TOP_N]

    def _gap(self, live: float | None, eod: float | None) -> float | None:
        if live is None or eod is None or eod == 0:
            return None
        return (live - eod) / eod * 100.0

    def _verdict(self, gap: float | None, rec: str) -> str:
        if gap is None:
            return "·"
        bullish = rec in ("STRONG_BUY", "BUY", "ACCUMULATE")
        if bullish and gap >= 0.5:
            return "✓"
        if bullish and gap <= -0.5:
            return "✗"
        return "·"

    def build(self) -> ReportResult:
        historical = self.context.grouped_data.get("all_stocks", [])
        live_data = self.context.live_data or []
        analysis_date = self.context.analysis_date

        if not historical:
            return ReportResult(
                content="No historical data for cross-check",
                chunks=["No historical data for cross-check"]
            )

        top = self._select_top(historical)
        live_lookup = {d["symbol"]: d for d in live_data}

        lines = []
        lines.append(f"🧭 **Market-Open Cross-Check — {analysis_date.strftime('%d %b %Y')} 09:15 IST**")
        lines.append("")
        live_n = sum(1 for h in top if h["symbol"] in live_lookup)
        lines.append(f"⏰ **Snapshot:** 09:15 IST | Live: {live_n}/{len(top)} symbols")
        lines.append("")

        # Merged table
        lines.append("| Sym | EOD Close | 9:15 LTP | Gap% | Live RSI | Live Vol | Rec | Call |")
        lines.append("|:----|----------:|---------:|-----:|---------:|---------:|:----|:---:|")

        pos = neg = ok = 0
        for h in top:
            sym = h["symbol"]
            live = live_lookup.get(sym)
            eod_close = h.get("close")
            rec = h.get("recommendation", "—")
            ltp = live.get("close") if live else None
            lrsi = live.get("RSI") if live else None
            lvol = live.get("volume") if live else None
            g = self._gap(ltp, eod_close)
            v = self._verdict(g, rec)

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
        lines.append(f"**📊 Open scorecard:** {pos} gapping up · {neg} gapping down · {ok} morning bullish calls on track")
        lines.append("")
        lines.append("_Source: EOD BhavCopy analysis (08:30 morning report) + Live TradingView @ 09:15._")
        lines.append("⚠️ Indicative only. Not financial advice.")

        content = "\n".join(lines)
        chunks = self.chunk_message(content)
        return ReportResult(content=content, chunks=chunks)


# ── 09:00 Combined Pre-Market Report ────────────────────────────────

@register_report("combined_premarket")
class CombinedPreMarketReport(BaseReport):
    """09:00 Combined Pre-Market Report (Historical + Live)."""

    kind = "combined_premarket"
    name = "Combined Pre-Market Report"
    description = "09:00 IST report merging historical analysis with live pre-market data"

    def build(self) -> ReportResult:
        historical = self.context.grouped_data.get("all_stocks", [])
        live_data = self.context.live_data or []
        analysis_date = self.context.analysis_date

        if not historical:
            return ReportResult(
                content="No historical data for combined report",
                chunks=["No historical data for combined report"]
            )

        # Merge historical + live
        merged = merge_historical_live(historical, live_data)
        live_count = sum(1 for m in merged if m.get("live_close") is not None)

        lines = []

        # Header
        lines.append(f"📊 **Pre-Market Combined Report — {analysis_date.strftime('%d %b %Y')} 09:00 IST**")
        lines.append("")
        lines.append(f"⏰ **Snapshot:** 09:00 IST | **Live Data:** {live_count}/{len(merged)} symbols")
        lines.append("")

        # Main combined table
        lines.append("| Sym | EOD Close | Live LTP | Gap% | EOD Chg% | Live Chg% | EOD RSI | Live RSI | ΔRSI | EOD Vol | Live Vol | Vol× | VWAP | EOD Rec |")
        lines.append("|:----|----------:|---------:|-----:|---------:|----------:|--------:|---------:|-----:|--------:|---------:|-----:|-----:|:-------|")

        for m in merged:
            sym = m["symbol"]

            h_close = _fmt(m.get("hist_close"), ",.1f")
            h_change = _fmt(m.get("hist_change"), "+.2f") + "%" if m.get("hist_change") is not None else "—"
            h_rsi = _fmt(m.get("hist_rsi"), ".1f")
            h_rec = m.get("hist_rec", "—")
            h_vol = _fmt(m.get("hist_vol"), ",.0f") if m.get("hist_vol") else "—"

            l_close = _fmt(m.get("live_close"), ",.1f") if m.get("live_close") else "—"
            l_change = _fmt(m.get("live_change"), "+.2f") + "%" if m.get("live_change") else "—"
            l_rsi = _fmt(m.get("live_rsi"), ".1f") if m.get("live_rsi") else "—"
            l_vol = _fmt(m.get("live_volume"), ",.0f") if m.get("live_volume") else "—"
            vwap = _fmt(m.get("live_vwap"), ",.1f") if m.get("live_vwap") else "—"

            gap = _fmt(m.get("gap_pct"), "+.2f") + "%" if m.get("gap_pct") is not None else "—"
            rsi_d = _fmt(m.get("rsi_delta"), "+.1f") if m.get("rsi_delta") is not None else "—"
            vol_r = _fmt(m.get("vol_ratio"), ".2f") + "x" if m.get("vol_ratio") else "—"

            gap_emoji = _gap_emoji(m.get("gap_pct"))
            rsi_e = _rsi_emoji(m.get("live_rsi"))
            vol_e = _vol_emoji(m.get("vol_ratio"))

            lines.append(
                f"| {sym} | {h_close} | {l_close} | {gap_emoji}{gap} | "
                f"{h_change} | {l_change} | {h_rsi} | {rsi_e}{l_rsi} | {rsi_d} | "
                f"{h_vol} | {vol_e}{l_vol} | {vol_r} | {vwap} | {h_rec} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

        # Gap Analysis
        lines.append("### 🎯 **Gap Analysis**")
        lines.append("")

        gapped = [m for m in merged if m.get("gap_pct") is not None]
        if gapped:
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
        lines.append("_Source: Historical (EOD BhavCopy) + Live (TradingView Scanner)_")
        lines.append(f"_Generated: 09:00 IST | {live_count}/{len(merged)} live_")
        lines.append("")
        lines.append("⚠️ _Pre-market data indicative only. Not financial advice._")

        content = "\n".join(lines)
        chunks = self.chunk_message(content)
        return ReportResult(content=content, chunks=chunks)


async def send_open_crosscheck_report(app) -> dict:
    """Send 09:15 cross-check report to owner."""
    from bot import _needs_rich, _send_rich_chunks
    from src.database.repositories import AnalysisReadRepository, SyncReadRepository

    logger.info("Generating 09:15 market-open cross-check report...")
    try:
        sync_repo = SyncReadRepository()
        analysis_date = sync_repo.get_last_synced_date()
        if not analysis_date:
            return {"sent": 0, "failed": 1, "total": 1}

        analysis_repo = AnalysisReadRepository()
        analysis = analysis_repo.get_latest_analysis(analysis_date)
        if not analysis:
            return {"sent": 0, "failed": 1, "total": 1}

        # Get all stocks flat
        all_stocks = [s for v in analysis for s in v] if isinstance(analysis, dict) else analysis

        report_instance = OpenCrossCheckReport(ReportContext(
            analysis_date=analysis_date,
            grouped_data={"all_stocks": all_stocks},
            outlook={},
            live_data=[],
        ))

        result = report_instance.build()

        if _needs_rich(result.content):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, result.content)
        else:
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=result.content, parse_mode="Markdown")

        return {"sent": 1, "failed": 0, "total": 1}
    except Exception as e:
        logger.error("Open cross-check failed: %s", e, exc_info=True)
        return {"sent": 0, "failed": 1, "total": 1}


async def send_combined_premarket_report(app) -> dict:
    """Send 09:00 combined pre-market report to owner."""
    import asyncio

    from bot import _needs_rich, _send_rich_chunks
    from src.data.fetchers import fetch_live_snapshot
    from src.database.repositories import AnalysisReadRepository, SyncReadRepository

    logger.info("Generating combined pre-market report...")
    try:
        sync_repo = SyncReadRepository()
        analysis_date = sync_repo.get_last_synced_date()
        if not analysis_date:
            return {"sent": 0, "failed": 1, "total": 1}

        analysis_repo = AnalysisReadRepository()
        analysis = analysis_repo.get_latest_analysis(analysis_date)
        if not analysis:
            return {"sent": 0, "failed": 1, "total": 1}

        all_stocks = [s for v in analysis for s in v] if isinstance(analysis, dict) else analysis
        top25 = sorted(all_stocks, key=lambda x: x.get("composite_score", 0), reverse=True)[:25]

        symbols = [s["symbol"] for s in top25]
        loop = asyncio.get_event_loop()
        live = await loop.run_in_executor(None, fetch_live_snapshot, symbols)

        if not live:
            return {"sent": 0, "failed": 1, "total": 1}

        report_instance = CombinedPreMarketReport(ReportContext(
            analysis_date=analysis_date,
            grouped_data={"all_stocks": top25},
            outlook={},
            live_data=live,
        ))

        result = report_instance.build()

        if _needs_rich(result.content):
            await _send_rich_chunks(app.bot, OWNER_CHAT_ID, result.content)
        else:
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=result.content, parse_mode="Markdown")

        return {"sent": 1, "failed": 0, "total": 1}
    except Exception as e:
        logger.error("Combined pre-market failed: %s", e, exc_info=True)
        return {"sent": 0, "failed": 1, "total": 1}
