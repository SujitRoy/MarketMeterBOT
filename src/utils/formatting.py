"""
Formatting Utilities
Number, price, and percentage formatting for display.
"""


def fmt_price(value: float | int | None, na: str = "—") -> str:
    """Format price with ₹ symbol."""
    if value is None:
        return na
    return f"₹{value:,.2f}"


def fmt_price_int(value: float | int | None, na: str = "—") -> str:
    """Format price as integer with ₹ symbol."""
    if value is None:
        return na
    return f"₹{int(value):,}"


def fmt_number(value: float | int | None, decimals: int = 2, na: str = "—") -> str:
    """Format number with commas."""
    if value is None:
        return na
    return f"{value:,.{decimals}f}"


def fmt_int(value: float | int | None, na: str = "—") -> str:
    """Format integer with commas."""
    if value is None:
        return na
    return f"{int(value):,}"


def fmt_pct(value: float | int | None, decimals: int = 2, na: str = "—", signed: bool = True) -> str:
    """Format percentage."""
    if value is None:
        return na
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:.{decimals}f}%"


def fmt_signed(value: float | int | None, decimals: int = 2, na: str = "—") -> str:
    """Format signed number."""
    if value is None:
        return na
    return f"{value:+.{decimals}f}"


def fmt_mcap(value: float | int | None, na: str = "—") -> str:
    """Format market cap in Cr/K Cr/L Cr."""
    if value is None:
        return na

    cr = value / 1e7
    if cr < 1000:
        return f"₹{cr:,.0f} Cr"
    if cr < 100000:
        return f"₹{cr/1000:,.2f}K Cr"
    return f"₹{cr/100000:,.2f}L Cr"


def fmt_volume(value: float | int | None, na: str = "—") -> str:
    """Format volume with K/M/B suffixes."""
    if value is None:
        return na

    if value >= 1e9:
        return f"{value/1e9:.2f}B"
    if value >= 1e6:
        return f"{value/1e6:.2f}M"
    if value >= 1e3:
        return f"{value/1e3:.2f}K"
    return f"{int(value):,}"


def fmt_ratio(value: float | None, decimals: int = 2, na: str = "—") -> str:
    """Format ratio with x suffix."""
    if value is None:
        return na
    return f"{value:.{decimals}f}x"


def fmt_vol_signal(rel_vol: float | None) -> str:
    """Format relative volume signal."""
    if rel_vol is None:
        return "—"
    if rel_vol > 3:
        return "🔥 Spike"
    if rel_vol > 1.5:
        return "High"
    if rel_vol > 0.8:
        return "Normal"
    return "Low"


def fmt_rsi_zone(rsi: float | None) -> str:
    """Format RSI zone."""
    if rsi is None:
        return "—"
    if rsi > 70:
        return "Overbought"
    if rsi > 60:
        return "Bullish"
    if rsi > 40:
        return "Neutral"
    if rsi > 30:
        return "Bearish"
    return "Oversold"


def fmt_trend_strength(adx: float | None) -> str:
    """Format ADX trend strength."""
    if adx is None:
        return "N/A"
    if adx > 50:
        return "Very Strong"
    if adx > 30:
        return "Strong"
    if adx > 20:
        return "Moderate"
    return "Weak"


def fmt_macd_trend(macd: float | None, signal: float | None) -> str:
    """Format MACD trend."""
    if macd is None or signal is None:
        return "—"
    return "Bullish" if macd > signal else "Bearish"


def fmt_bb_position(close: float | None, upper: float | None, lower: float | None) -> str:
    """Format Bollinger Band position."""
    if close is None or upper is None or lower is None or upper == lower:
        return "—"

    pct = (close - lower) / (upper - lower) * 100
    if pct >= 90:
        return f"{pct:.0f}% (near upper)"
    if pct >= 70:
        return f"{pct:.0f}% (upper half)"
    if pct >= 30:
        return f"{pct:.0f}% (mid)"
    if pct >= 10:
        return f"{pct:.0f}% (lower half)"
    return f"{pct:.0f}% (near lower)"


def fmt_obv_trend(obv: float, volume: int) -> str:
    """Format OBV trend."""
    if volume <= 0:
        return "↔ Flat"
    pct = abs(obv) / volume
    if obv > 0:
        return "↑ Surging" if pct > 0.5 else ("↑ Rising" if pct > 0.1 else "↑ Steady")
    if obv < 0:
        return "↓ Falling" if pct > 0.1 else "↓ Weak"
    return "↔ Flat"


def fmt_tv_rating(rec: float | None) -> str:
    """Format TradingView recommendation."""
    if rec is None:
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


def fmt_stoch_signal(k: float | None, d: float | None) -> str:
    """Format Stochastic signal."""
    if k is None or d is None:
        return "—"
    if k > 80:
        return "Overbought"
    if k < 20:
        return "Oversold"
    return "Neutral"


def format_table_row(cells: list, alignments: list = None) -> str:
    """Format a markdown table row."""
    if alignments is None:
        alignments = [":---"] * len(cells)

    formatted = []
    for i, cell in enumerate(cells):
        align = alignments[i] if i < len(alignments) else ":---"
        formatted.append(str(cell))
    return "| " + " | ".join(formatted) + " |"


def format_table_header(headers: list, alignments: list = None) -> str:
    """Format a markdown table header."""
    if alignments is None:
        alignments = [":---"] * len(headers)

    header_row = "| " + " | ".join(str(h) for h in headers) + " |"
    align_row = "| " + " | ".join(alignments) + " |"
    return header_row + "\n" + align_row
