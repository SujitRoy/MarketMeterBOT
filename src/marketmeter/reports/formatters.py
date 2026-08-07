"""
reports/formatters — single source of truth for all numeric/string formatting.

Phase 4 consolidation. These helpers were previously duplicated across:

    report_generator.py     _fmt, _fmt_price, _fmt_num, _fmt_pct, _fmt_int, _fmt_mcap
    premarket_report.py     uses _fmt inline
    premarket_open_report.py _fmt, _signed_pct, _gap
    premarket_combined_report.py _fmt, _gap_pct, _vol_ratio
    search_handler.py       _fmt_price, _fmt_num, _fmt_signed, _fmt_pct, _fmt_int, _fmt_mcap, _has

Four slightly different `_fmt` signatures existed:
    report_generator.py:       _fmt(v, fmt=".1f", fallback="-")
    premarket_open_report.py:   _fmt(v, d=2, na="—")
    premarket_combined_report.py: _fmt(v, fmt=".2f", na="—")
    premarket_report.py:        no helper, formats inline

This module unifies them into one signature:
    fmt(v, spec=",.1f", fallback="-")

The default fallback is "-" (matches report_generator's report entry style).
Pass `fallback="—"` for em-dash entries (matches premarket style).

Critical Phase 4 fix: the OLD _fmt returned `'-'` when v was None, but the
morning report's `_detail_block` line 110 did `f"₹{close:,.2f}"` directly,
bypassing _fmt. When `close` was None (stocks with no close yet), the
report crashed with "unsupported format string passed to NoneType.__format__".
That crash is the cause of 5 pre-existing failing tests (test_fix_c.py and
test_perf_smoke.py). Phase 4 fixes it by routing all price-rendering through
fmt(), which is None-safe.
"""
from __future__ import annotations

from typing import Optional

# Re-export the canonical NA glyphs. Different sections use different ones:
# '-' for scan tables (compact), '—' for detail blocks (easier to read).
NA_DASH = "-"
NA_EMDASH = "—"


def _has(v) -> bool:
    """True if v is a real value (not None, not NaN).

    Replaces the per-file `_has` shim. Used everywhere a renderable-row
    predicate is needed.
    """
    if v is None:
        return False
    # float('nan') survives type checks but isn't renderable. Avoid importing
    # numpy here — call sites that store NaN use stdlib float('nan') and we
    # only need to filter the one case that matters.
    try:
        return v == v  # NaN != NaN
    except Exception:
        return False


def fmt(v, spec: str = ",.1f", fallback: str = NA_DASH) -> str:
    """Generic safe formatter. Returns `fallback` for None / NaN / non-numeric.

    Args:
        v: value to format
        spec: Python format spec, e.g. ",.2f" for "1,234.56"
        fallback: what to return when v is None/NaN/garbage

    Examples:
        fmt(1234.5)              -> "1,234.5"
        fmt(1234.5, ",.2f")      -> "1,234.50"
        fmt(None)                -> "-"
        fmt(None, fallback="—")  -> "—"
        fmt(float('nan'))        -> "-"
    """
    if not _has(v):
        return fallback
    try:
        return format(v, spec)
    except (ValueError, TypeError):
        return fallback


def price_rupees(v, spec: str = ",.2f", fallback: str = NA_DASH) -> str:
    """Format as ₹ value. e.g. price_rupees(2500.5) -> "₹2,500.50"."""
    return f"₹{fmt(v, spec, fallback)}"


def price_rupees_compact(v, spec: str = ",.0f", fallback: str = NA_DASH) -> str:
    """Compact rupee price for scan tables (no decimals)."""
    return f"₹{fmt(v, spec, fallback)}"


def signed_pct(v, decimals: int = 2, fallback: str = NA_EMDASH) -> str:
    """Format with explicit + sign. e.g. signed_pct(1.5) -> "+1.50%"."""
    if not _has(v):
        return fallback
    try:
        return f"{v:+.{decimals}f}%"
    except (ValueError, TypeError):
        return fallback


def fmt_int(v, fallback: str = NA_DASH) -> str:
    """Integer with thousand separators."""
    return fmt(v, ",d", fallback)


def fmt_mcap(v, fallback: str = NA_DASH) -> str:
    """Format a market-cap value (in raw currency, not lakhs).

    Returns "₹X.XXK Cr" for values < 1L Cr and "₹X.XXL Cr" otherwise.
    Used by /search live-detail.
    """
    if not _has(v):
        return fallback
    cr = v / 1e7  # raw → Crore
    if cr < 1e5:
        return f"₹{cr/1000:,.2f}K Cr"
    return f"₹{cr/100000:,.2f}L Cr"


def gap_pct(live: Optional[float], eod: Optional[float]) -> Optional[float]:
    """Live vs EOD percentage move. Returns None when inputs unusable.

    Centralised here because the same _gap/_gap_pct logic appeared in
    premarket_open_report.py and premarket_combined_report.py with subtle
    differences (one returns the float, the other returns the formatted
    string). This is the raw-float version. For the formatted string, use
    signed_pct(gap_pct(live, eod)).
    """
    if live is None or eod is None or eod == 0:
        return None
    return (live - eod) / eod * 100.0


def vol_ratio(live_vol: Optional[int], avg_vol: Optional[float]) -> Optional[float]:
    """Live volume / average daily volume. Returns None when inputs unusable."""
    if live_vol is None or avg_vol is None or avg_vol == 0:
        return None
    return live_vol / avg_vol


__all__ = [
    "NA_DASH",
    "NA_EMDASH",
    "_has",
    "fmt",
    "price_rupees",
    "price_rupees_compact",
    "signed_pct",
    "fmt_int",
    "fmt_mcap",
    "gap_pct",
    "vol_ratio",
]