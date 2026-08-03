"""
telegram/search/detail — format and send live stock detail.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, time
from typing import Optional

from telegram import Update

from marketmeter.core.config import (
    MARKET_OPEN_TIME, MARKET_CLOSE_TIME,
)
from marketmeter.sources.tradingview import fetch_live_snapshot
from marketmeter.telegram.search.keyboards import _chart_keyboard
from marketmeter.telegram.rich.send import _send_rich_chunks


# ─── Formatting helpers (render None/0 as '—' so the UI is honest) ──

def _has(v) -> bool:
    """True if v is a usable number (not None, not 0, not NaN)."""
    if v is None:
        return False
    if isinstance(v, bool):
        return False
    if isinstance(v, float):
        # NaN check (NaN != NaN)
        return v == v and v != 0.0
    return v != 0


def _fmt_price(v) -> str:
    """₹ price, or '—' when missing."""
    return f"₹{v:,.2f}" if _has(v) else "—"


def _fmt_num(v, fmt: str = ",.2f") -> str:
    """Number with caller-supplied format, or '—'."""
    return f"{v:{fmt}}" if _has(v) else "—"


def _fmt_signed(v) -> str:
    """Signed number (e.g. +9.22), or '—'."""
    return f"{v:+.2f}" if _has(v) else "—"


def _fmt_pct(v) -> str:
    """Signed percent, or '—'."""
    return f"{v:+.2f}%" if _has(v) else "—"


def _fmt_int(v) -> str:
    """Integer with thousands separators, or '—'."""
    return f"{int(v):,}" if _has(v) else "—"


def _fmt_mcap(v) -> str:
    """
    Humanize INR market cap.
    TradingView scanner returns market_cap_basic in INR (NSE listing currency).
    """
    if not _has(v):
        return "—"
    cr = v / 1e7
    if cr < 1000:
        return f"₹{cr:,.0f} Cr"
    if cr < 100000:
        return f"₹{cr/1000:,.2f}K Cr"
    return f"₹{cr/100000:,.2f}L Cr"


def _rvol_signal(rv) -> str:
    """Volume bucket."""
    if not _has(rv):
        return "—"
    if rv > 3:
        return "🔥 Spike"
    if rv > 1.5:
        return "High"
    if rv > 0.8:
        return "Normal"
    return "Low"


def _tv_rating_label(rec) -> str:
    """Map TradingView's -1.5..+1.5 recommendation score to a human label."""
    if not _has(rec):
        return "—"
    if rec >= 1.0:
        return "Strong Buy"
    if rec >= 0.5:
        return "Buy"
    if rec > -0.5:
        return "Neutral"
    if rec > -1.0:
        return "Sell"
    return "Strong Sell"


def _market_state() -> tuple[str, datetime]:
    """Return (state_label, now). State is 'open', 'pre-market', or 'closed'."""
    now = datetime.now()
    open_t = time.fromisoformat(MARKET_OPEN_TIME)
    close_t = time.fromisoformat(MARKET_CLOSE_TIME)
    current_t = now.time()
    if current_t < open_t:
        return "pre-market", now
    if current_t > close_t:
        return "closed", now
    return "open", now


def _position_in_range(ltp, low, high) -> Optional[float]:
    """Where in the day's range LTP sits (0=at low, 1=at high)."""
    if not (_has(ltp) and _has(low) and _has(high)) or high <= low:
        return None
    return (ltp - low) / (high - low)


def _position_label(pos: Optional[float]) -> str:
    if pos is None:
        return "—"
    pct = pos * 100
    if pct >= 90:
        return f"{pct:.0f}% (near high)"
    if pct >= 70:
        return f"{pct:.0f}% (upper half)"
    if pct >= 30:
        return f"{pct:.0f}% (mid)"
    if pct >= 10:
        return f"{pct:.0f}% (lower half)"
    return f"{pct:.0f}% (near low)"


# ─── Live fetch ───────────────────────────────────────────────────

async def fetch_live_for_symbol(symbol: str) -> Optional[dict]:
    """Fetch live data for a single symbol via TradingView."""
    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, fetch_live_snapshot, [symbol])
        if results:
            return results[0]
    except Exception as e:
        from marketmeter.core.logging import get_logger
        logger = get_logger(__name__)
        logger.error("Live fetch failed for %s: %s", symbol, e)
    return None


# ─── Detail rendering ─────────────────────────────────────────────

def format_live_detail(symbol: str, data: dict) -> str:
    """
    Format live stock data as Rich Markdown with tables.

    Layout:
      1. Header (symbol, LTP, change, sector/industry, market state)
      2. Price Summary table
      3. Intraday Analytics (gap, change-from-open, day-range position)
      4. TradingView Rating (overall / MA / oscillators)
      5. Technical Indicators (RSI, MACD, Stochastic, ADX, ATR)
      6. Bollinger Bands
      7. Moving Averages (EMA/SMA spread)
      8. 52-Week Position
      9. Fundamentals (market cap, valuation, margins, sector)
      10. Footer (timestamp, source)
    """
    ltp = data.get("close")
    chg = data.get("change_abs")
    chg_pct = data.get("change")
    vol = data.get("volume")
    high = data.get("high")
    low = data.get("low")
    opn = data.get("open")
    vwap = data.get("VWAP")
    rsi = data.get("RSI")
    macd = data.get("MACD.macd")
    macd_sig = data.get("MACD.signal")
    rel_vol = data.get("relative_volume_10d_calc")
    ema9 = data.get("EMA9")
    ema21 = data.get("EMA21")
    ema50 = data.get("EMA50")
    ema200 = data.get("EMA200")
    sma20 = data.get("SMA20")
    sma50 = data.get("SMA50")
    sma200 = data.get("SMA200")
    mcap = data.get("market_cap_basic")
    pe = data.get("price_earnings_ttm")
    eps = data.get("earnings_per_share_diluted_ttm")
    div_yield = data.get("dividends_yield_current")
    exchange = data.get("exchange", "NSE")
    description = data.get("description", "")

    # New fields (added in 2026-07-30 /search enrichment)
    chg_from_open = data.get("change_from_open_abs")
    chg_from_open_pct = data.get("change_from_open")
    gap_pct = data.get("gap")
    rec_all = data.get("Recommend.All")
    rec_ma = data.get("Recommend.MA")
    rec_osc = data.get("Recommend.Other")
    stoch_k = data.get("Stoch.K")
    stoch_d = data.get("Stoch.D")
    adx = data.get("ADX")
    adx_pos = data.get("ADX+DI")
    adx_neg = data.get("ADX-DI")
    atr = data.get("ATR")
    bb_upper = data.get("BB.upper")
    bb_lower = data.get("BB.lower")
    bb_basis = data.get("BB.basis")
    high_52w = data.get("high_52w")
    low_52w = data.get("low_52w")
    all_time_high = data.get("all_time_high")
    all_time_low = data.get("all_time_low")
    gross_m = data.get("gross_margin_ttm")
    net_m = data.get("net_margin_ttm")
    sector = data.get("sector")
    industry = data.get("industry")

    # Derived signals
    trend = (
        "🟢 BULLISH" if _has(ltp) and _has(vwap) and ltp > vwap
        else "🔴 BEARISH" if _has(ltp) and _has(vwap) and ltp < vwap
        else "🟡 NEUTRAL"
    )
    rsi_zone = (
        "Overbought" if _has(rsi) and rsi > 70
        else "Oversold" if _has(rsi) and rsi < 30
        else "Neutral"
    )
    macd_trend = "Bullish" if _has(macd) and _has(macd_sig) and macd > macd_sig else "Bearish"

    # Use the helper to build the body
    lines = _build_detail_body(
        symbol=symbol, exchange=exchange, description=description,
        ltp=ltp, chg=chg, chg_pct=chg_pct, vol=vol, high=high, low=low,
        opn=opn, vwap=vwap, rel_vol=rel_vol,
        rsi=rsi, macd=macd, macd_sig=macd_sig,
        stoch_k=stoch_k, stoch_d=stoch_d, adx=adx, adx_pos=adx_pos, adx_neg=adx_neg, atr=atr,
        bb_upper=bb_upper, bb_lower=bb_lower, bb_basis=bb_basis,
        ema9=ema9, ema21=ema21, ema50=ema50, ema200=ema200,
        sma20=sma20, sma50=sma50, sma200=sma200,
        high_52w=high_52w, low_52w=low_52w,
        all_time_high=all_time_high, all_time_low=all_time_low,
        mcap=mcap, pe=pe, eps=eps, div_yield=div_yield,
        gross_m=gross_m, net_m=net_m,
        sector=sector, industry=industry,
        data=data,
        chg_from_open=chg_from_open, chg_from_open_pct=chg_from_open_pct, gap_pct=gap_pct,
        rec_all=rec_all, rec_ma=rec_ma, rec_osc=rec_osc,
        trend=trend, rsi_zone=rsi_zone, macd_trend=macd_trend,
    )
    return "\n".join(lines)


def _build_detail_body(
    *,
    symbol: str, exchange: str, description: str = "",
    data: dict,
    ltp, chg, chg_pct, vol, high, low,
    opn, vwap, rel_vol,
    rsi, macd, macd_sig,
    stoch_k, stoch_d, adx, adx_pos, adx_neg, atr,
    bb_upper, bb_lower, bb_basis,
    ema9, ema21, ema50, ema200,
    sma20, sma50, sma200,
    high_52w, low_52w,
    all_time_high, all_time_low,
    mcap, pe, eps, div_yield,
    gross_m, net_m,
    sector, industry,
    chg_from_open, chg_from_open_pct, gap_pct,
    rec_all, rec_ma, rec_osc,
    trend: str, rsi_zone: str, macd_trend: str,
) -> list[str]:
    """Render the full Rich-Markdown body for one symbol."""
    lines: list[str] = []

    # ── Header ─────────────────────────────────────────────────
    state_label, now = _market_state()
    state_banner = {
        "open": "🟢 Market open",
        "pre-market": "🟡 Pre-market",
        "closed": "🔴 Market closed",
    }[state_label]
    ltp_str = _fmt_price(ltp)
    chg_str = _fmt_signed(chg)
    pct_str = _fmt_pct(chg_pct)
    lines.append(f"📈 **{symbol}** — {ltp_str} ({exchange})")
    if description:
        lines.append(f"_🏢 {description}_")
    lines.append(f"**{trend}** · {chg_str} ({pct_str})")
    if sector or industry:
        lines.append(f"_📂 {sector or '?'} · {industry or '?'}_")
    lines.append(f"{state_banner} · Snapshot {now.strftime('%d %b %Y, %H:%M IST')}")
    lines.append("")

    # ── Price Summary ─────────────────────────────────────────
    lines.append("**💰 Price Summary**")
    lines.append("")
    # 2-column table. Rel Vol previously appended a third cell (the signal),
    # giving the row 3 cells in a 2-col table — Telegram's table parser
    # rejected the card, which is why /search showed a broken table.
    lines.append("| Metric | Value |")
    lines.append("|:-------|------:|")
    lines.append(f"| **LTP** | {ltp_str} |")
    lines.append(f"| **Change** | {chg_str} ({pct_str}) |")
    lines.append(f"| **Open** | {_fmt_price(opn)} |")
    lines.append(f"| **High** | {_fmt_price(high)} |")
    lines.append(f"| **Low** | {_fmt_price(low)} |")
    lines.append(f"| **VWAP** | {_fmt_price(vwap)} |")
    lines.append(f"| **Volume** | {_fmt_int(vol)} |")
    lines.append(f"| **Rel Vol (10d)** | {_fmt_num(rel_vol, ',.2f')}x · {_rvol_signal(rel_vol)} |")
    lines.append("")

    # ── Intraday Analytics ────────────────────────────────────
    pos = _position_in_range(ltp, low, high)
    day_range = (
        f"{_fmt_price(low)} – {_fmt_price(high)} ({(high-low):,.2f})"
        if _has(low) and _has(high) and high > low else "—"
    )
    lines.append("**📊 Intraday Analytics**")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|:-------|------:|")
    lines.append(f"| **Change from Open** | {_fmt_signed(chg_from_open)} ({_fmt_pct(chg_from_open_pct)}) |")
    lines.append(f"| **Gap (vs prev close)** | {_fmt_pct(gap_pct)} |")
    lines.append(f"| **Day Range** | {day_range} |")
    lines.append(f"| **Position in Range** | {_position_label(pos)} |")
    lines.append("")

    # ── TradingView Rating ────────────────────────────────────
    rec_all = data.get("Recommend.All")
    rec_ma = data.get("Recommend.MA")
    rec_osc = data.get("Recommend.Other")
    if _has(rec_all) or _has(rec_ma) or _has(rec_osc):
        lines.append("**🎯 TradingView Rating**")
        lines.append("")
        lines.append("| Type | Score | Signal |")
        lines.append("|:-----|------:|:-------|")
        if _has(rec_all):
            lines.append(f"| **Overall** | {rec_all:+.2f} | {_tv_rating_label(rec_all)} |")
        if _has(rec_ma):
            lines.append(f"| **Moving Averages** | {rec_ma:+.2f} | {_tv_rating_label(rec_ma)} |")
        if _has(rec_osc):
            lines.append(f"| **Oscillators** | {rec_osc:+.2f} | {_tv_rating_label(rec_osc)} |")
        lines.append("")

    # ── Technical Indicators ──────────────────────────────────
    if _has(rsi) or _has(macd) or _has(stoch_k) or _has(adx) or _has(atr):
        lines.append("**📈 Technical Indicators**")
        lines.append("")
        lines.append("| Indicator | Value | Signal |")
        lines.append("|:----------|------:|:-------|")
        if _has(rsi):
            lines.append(f"| **RSI(14)** | {rsi:.1f} | {rsi_zone} |")
        if _has(macd) and _has(macd_sig):
            lines.append(f"| **MACD** | {macd:.2f} / {macd_sig:.2f} | {macd_trend} |")
        elif _has(macd):
            lines.append(f"| **MACD** | {macd:.2f} | — |")
        if _has(stoch_k) and _has(stoch_d):
            stoch_sig = "Overbought" if stoch_k > 80 else "Oversold" if stoch_k < 20 else "Neutral"
            lines.append(f"| **Stoch %K/D** | {stoch_k:.1f} / {stoch_d:.1f} | {stoch_sig} |")
        if _has(adx):
            trend_strength = "Strong" if adx > 25 else "Moderate" if adx > 20 else "Weak"
            if _has(adx_pos) and _has(adx_neg):
                direction = "Up" if adx_pos > adx_neg else "Down"
                lines.append(f"| **ADX / DI+ / DI−** | {adx:.1f} / {adx_pos:.1f} / {adx_neg:.1f} | {trend_strength} · {direction} |")
            else:
                lines.append(f"| **ADX(14)** | {adx:.1f} | {trend_strength} |")
        if _has(atr):
            lines.append(f"| **ATR(14)** | ₹{atr:,.2f} | — |")
        lines.append("")

    # ── Bollinger Bands ───────────────────────────────────────
    if _has(bb_upper) and _has(bb_lower) and _has(bb_basis):
        lines.append("**📉 Bollinger Bands (20,2)**")
        lines.append("")
        lines.append("| Band | Value |")
        lines.append("|:-----|------:|")
        lines.append(f"| **Upper** | {_fmt_price(bb_upper)} |")
        lines.append(f"| **Basis** | {_fmt_price(bb_basis)} |")
        lines.append(f"| **Lower** | {_fmt_price(bb_lower)} |")
        if _has(ltp):
            if ltp > bb_upper:
                lines.append("\n_LTP above upper band — momentum extended._")
            elif ltp < bb_lower:
                lines.append("\n_LTP below lower band — oversold._")
            else:
                pct = (ltp - bb_lower) / (bb_upper - bb_lower) * 100
                lines.append(f"\n_LTP inside bands ({pct:.0f}% of range)._")
        lines.append("")

    # ── Moving Averages ───────────────────────────────────────
    ma_pairs = [
        ("EMA9", ema9), ("EMA21", ema21), ("EMA50", ema50), ("EMA200", ema200),
        ("SMA20", sma20), ("SMA50", sma50), ("SMA200", sma200),
    ]
    ma_rows = []
    for name, val in ma_pairs:
        if not _has(val):
            continue
        if _has(ltp) and val:
            diff_pct = (ltp - val) / val * 100
            vs = f"{diff_pct:+.1f}%"
        else:
            vs = "—"
        ma_rows.append(f"| {name} | {_fmt_price(val)} | {vs} |")
    if ma_rows:
        lines.append("**📈 Moving Averages**")
        lines.append("")
        lines.append("| MA | Value | LTP vs MA |")
        lines.append("|:---|------:|---------:|")
        lines.extend(ma_rows)
        lines.append("")

    # ── 52-Week Position ──────────────────────────────────────
    if _has(high_52w) or _has(low_52w):
        lines.append("**📅 52-Week Position**")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|:-------|------:|")
        if _has(high_52w) and _has(low_52w):
            lines.append(f"| **52w Range** | {_fmt_price(low_52w)} – {_fmt_price(high_52w)} |")
        if _has(high_52w) and _has(ltp) and high_52w > 0:
            dist_high = (ltp / high_52w - 1) * 100
            lines.append(f"| **Distance from 52w High** | {dist_high:+.1f}% |")
        if _has(low_52w) and _has(ltp) and low_52w > 0:
            dist_low = (ltp / low_52w - 1) * 100
            lines.append(f"| **Distance from 52w Low** | {dist_low:+.1f}% |")
        lines.append("")

    # ── All-Time Position ─────────────────────────────────────
    if _has(all_time_high) or _has(all_time_low):
        lines.append("**📈 All-Time Position**")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|:-------|------:|")
        if _has(all_time_high) and _has(all_time_low):
            lines.append(f"| **All-Time Range** | {_fmt_price(all_time_low)} – {_fmt_price(all_time_high)} |")
        if _has(all_time_high) and _has(ltp) and all_time_high > 0:
            dist_high = (ltp / all_time_high - 1) * 100
            lines.append(f"| **Distance from ATH** | {dist_high:+.1f}% |")
        if _has(all_time_low) and _has(ltp) and all_time_low > 0:
            dist_low = (ltp / all_time_low - 1) * 100
            lines.append(f"| **Distance from ATL** | {dist_low:+.1f}% |")
        lines.append("")

    # ── Fundamentals ──────────────────────────────────────────
    has_fund = any(_has(v) for v in (mcap, pe, eps, div_yield, gross_m, net_m))
    if has_fund:
        lines.append("**🏢 Fundamentals**")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|:-------|------:|")
        if _has(mcap):
            lines.append(f"| **Market Cap** | {_fmt_mcap(mcap)} |")
        if _has(pe):
            lines.append(f"| **P/E (TTM)** | {pe:.1f} |")
        if _has(eps):
            lines.append(f"| **EPS (TTM)** | ₹{eps:,.2f} |")
        if _has(div_yield):
            lines.append(f"| **Div Yield** | {div_yield:.2f}% |")
        if _has(gross_m):
            lines.append(f"| **Gross Margin** | {gross_m:.1f}% |")
        if _has(net_m):
            lines.append(f"| **Net Margin** | {net_m:.1f}% |")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────
    state_label, now = _market_state()
    state_banner = {
        "open": "🟢 Market open",
        "pre-market": "🟡 Pre-market",
        "closed": "🔴 Market closed",
    }[state_label]

    lines.append("---")
    lines.append("")
    lines.append(f"_Source: TradingView Scanner · Snapshot {now.strftime('%d %b %Y, %H:%M IST')}_")
    lines.append("_Tap **📊 Open Chart** for the full TradingView page._")

    return lines


async def send_live_stock_detail(update: Update, symbol: str):
    """Fetch and send live detail for a symbol directly."""
    temp = await update.message.reply_text(f"📡 Fetching **{symbol}**...")
    data = await fetch_live_for_symbol(symbol)
    try:
        await temp.delete()
    except Exception:
        pass

    if not data:
        await update.message.reply_text(f"❌ No live data for **{symbol}**.")
        return

    message = format_live_detail(symbol, data)
    await _send_rich_chunks(
        update.get_bot(), update.effective_chat.id, message,
        reply_markup=_chart_keyboard(symbol),
    )


__all__ = [
    "fetch_live_for_symbol",
    "format_live_detail",
    "send_live_stock_detail",
]