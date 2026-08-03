# ruff: noqa: E701, E702  # pre-existing compact one-line style
"""
reports/labels — single source of truth for categorical signal labels.

Phase 4 consolidation. Previously duplicated across:

    report_generator.py     _obv_label, _macd_label, _bb_pos, _narrative
    premarket_combined_report.py _rsi_signal, _gap_emoji, _vol_emoji
    search_handler.py       _rvol_signal, _tv_rating_label, _market_state,
                            _position_label, _position_in_range

These helpers take a numeric input and return a categorical label (emoji,
word, or short phrase). Consolidating them here means a new report section
that needs a "fill bucket" or "trend label" has one canonical implementation.

Each function is pure: no state, no I/O. Tests can pin their behaviour.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from marketmeter.core.config import MARKET_OPEN_TIME, MARKET_CLOSE_TIME
from marketmeter.reports.formatters import _has, NA_EMDASH


# ── OBV trend labels (from report_generator) ─────────────────────────

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


# ── MACD label (from report_generator) ───────────────────────────────

def macd_label(macd_line, signal_line, hist=None) -> str:
    """Bullish / Bearish based on macd_line vs signal_line."""
    if macd_line is None or signal_line is None:
        return "-"
    return "Bullish" if macd_line > signal_line else "Bearish"


# ── Bollinger Band position (from report_generator) ──────────────────

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


# ── Relative Volume signal (from search_handler) ─────────────────────

def rvol_signal(rv) -> str:
    """Volume bucket: 🔥 Spike / High / Normal / Low. Not binary like 1.5x cutoff."""
    if not _has(rv):
        return NA_EMDASH
    if rv > 3:
        return "🔥 Spike"
    if rv > 1.5:
        return "High"
    if rv > 0.8:
        return "Normal"
    return "Low"


# ── TradingView's own recommendation score (from search_handler) ─────

def tv_rating_label(rec) -> str:
    """Map TradingView's -1.5..+1.5 recommendation score to a human label.

    https://www.tradingview.com/support/folders/43000556872-buy-sell-indicators/
    """
    if not _has(rec):
        return NA_EMDASH
    if rec >= 1.0:
        return "Strong Buy"
    if rec >= 0.5:
        return "Buy"
    if rec > -0.5:
        return "Neutral"
    if rec > -1.0:
        return "Sell"
    return "Strong Sell"


# ── RSI signal emoji (from premarket_combined) ──────────────────────

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


# ── Gap emoji (from premarket_combined) ─────────────────────────────

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


# ── Volume ratio emoji (from premarket_combined) ───────────────────

def vol_emoji(ratio: Optional[float]) -> str:
    """Volume-ratio emoji. 2x+ fire, 1x+ chart, else sleeper."""
    if ratio is None:
        return NA_EMDASH
    if ratio >= 2:
        return "🔥"
    if ratio >= 1:
        return "📊"
    return "💤"


# ── Verdict symbol (from premarket_open) ───────────────────────────

def verdict(gap: Optional[float], rec: str) -> str:
    """Mark morning-vs-open agreement.

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


# ── Market state (from search_handler) ─────────────────────────────

def market_state(now: Optional[datetime] = None) -> tuple[str, datetime]:
    """Return (state_label, now). State is 'open', 'pre-market', or 'closed'.

    Uses server local clock. On this host the local clock is IST, so this
    is correct for the 09:15 open / 15:30 close boundary.
    """
    now = now or datetime.now()
    open_t = time.fromisoformat(MARKET_OPEN_TIME)
    close_t = time.fromisoformat(MARKET_CLOSE_TIME)
    current_t = now.time()
    if current_t < open_t:
        return "pre-market", now
    if current_t > close_t:
        return "closed", now
    return "open", now


# ── Position in day's range (from search_handler) ──────────────────

def position_in_range(ltp, low, high) -> Optional[float]:
    """Where in the day's range LTP sits (0=at low, 1=at high)."""
    if not (_has(ltp) and _has(low) and _has(high)) or high <= low:
        return None
    return (ltp - low) / (high - low)


def position_label(pos: Optional[float]) -> str:
    """Human label for position-in-range (0..100%)."""
    if pos is None:
        return NA_EMDASH
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


# ── One-line narrative (from report_generator) ────────────────────

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


# ── Backward-compat aliases (Phase 4 callers reference both names) ─

# report_generator historically used _format-prefixed names; we expose
# both styles so the new modules can use the clean names and the shim
# can keep the underscore names without a translation pass.
_obv_label = obv_label
_macd_label = macd_label
_bb_pos = bb_pos
_rvol_signal = rvol_signal
_tv_rating_label = tv_rating_label
_rsi_signal = rsi_signal
_gap_emoji = gap_emoji
_vol_emoji = vol_emoji
_verdict = verdict
_market_state = market_state
_position_in_range = position_in_range
_position_label = position_label
_narrative = narrative


__all__ = [
    "obv_label", "macd_label", "bb_pos",
    "rvol_signal", "tv_rating_label",
    "rsi_signal", "gap_emoji", "vol_emoji", "verdict",
    "market_state", "position_in_range", "position_label",
    "narrative",
    # underscore aliases for shim and old callers
    "_obv_label", "_macd_label", "_bb_pos",
    "_rvol_signal", "_tv_rating_label",
    "_rsi_signal", "_gap_emoji", "_vol_emoji", "_verdict",
    "_market_state", "_position_in_range", "_position_label",
    "_narrative",
]