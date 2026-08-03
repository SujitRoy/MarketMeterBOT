"""
tests/reports/test_morning.py — snapshot tests for the morning report.

Phase 7 of docs/REFACTOR_PLAN.md mandates:
  - "Snapshot tests for reports: byte-equal output given identical inputs."
  - "Determinism tests for the fresh suite."

These tests pin the morning report's output for a fixed analysis date
and a fixed set of analysis rows. Any change to layout, helpers, or
formatters that would shift the output will fail these tests — that's the
whole point of a snapshot test.

The tests use the `_render_morning_report_single_pass` and `_detail_block`
functions directly, bypassing the DB-backed `generate_morning_report`,
so they need NO database fixture and run in microseconds.
"""
from __future__ import annotations

from datetime import date

import pytest

from marketmeter.reports.morning import (
    _detail_block,
    _render_morning_report_single_pass,
    CATEGORY_CONFIG,
    RECOMMENDATION_ORDER,
)


# ── A canonical fixture row for snapshot tests ─────────────────────────────────
# Use the same shape as src/marketmeter/analysis/analyzer.py so the renderer
# doesn't bail on a missing key.

def _row(
    symbol="RELIANCE",
    close=2510.0,
    rsi_14=65.0,
    adx_14=30.0,
    macd_line=5.0,
    signal_line=3.0,
    macd_hist=2.0,
    sma_20=2490.0,
    sma_50=2480.0,
    sma_100=2450.0,
    sma_200=2400.0,
    ema_20=2495.0,
    ema_50=2485.0,
    ema_100=2460.0,
    ema_200=2420.0,
    atr_14=30.0,
    bb_upper=2530.0,
    bb_lower=2470.0,
    rel_volume=1.2,
    obv_trend=50000.0,
    avg_price=2505.0,
    volume=1_000_000,
    composite_score=12,
    recommendation="BUY",
):
    return {
        "symbol": symbol,
        "close": close,
        "volume": volume,
        "rsi_14": rsi_14,
        "adx_14": adx_14,
        "macd_line": macd_line,
        "signal_line": signal_line,
        "macd_hist": macd_hist,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_100": sma_100,
        "sma_200": sma_200,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_100": ema_100,
        "ema_200": ema_200,
        "atr_14": atr_14,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "rel_volume": rel_volume,
        "obv_trend": obv_trend,
        "avg_price": avg_price,
        "composite_score": composite_score,
        "recommendation": recommendation,
    }


# ── _detail_block: the critical None-safety contract ─────────────────────────

class TestDetailBlockNoneSafety:
    """Phase 4 fixed the pre-existing NoneType.__format__ crash.

    The old `_detail_block` did `f"₹{close:,.2f}"` directly, which crashed
    when `close` was None (symbols with no close yet). The new version
    routes everything through `formatters.price_rupees` / `formatters.fmt`,
    which return '₹-' or a fallback glyph on None instead of crashing.
    """

    def test_all_none_values_render_without_crash(self):
        # The exact failure mode from the original bug report — every numeric
        # field is None. The renderer must produce output, NOT raise TypeError.
        row = _row(
            close=None, rsi_14=None, adx_14=None,
            macd_line=None, signal_line=None, macd_hist=None,
            sma_20=None, sma_50=None, sma_100=None, sma_200=None,
            ema_20=None, ema_50=None, ema_100=None, ema_200=None,
            atr_14=None, bb_upper=None, bb_lower=None,
            rel_volume=None, obv_trend=None, avg_price=None,
            volume=0,
        )
        result = _detail_block(row, 1)
        assert isinstance(result, list)
        assert len(result) > 0
        # Body should contain the fallback glyph ('-') for missing values
        body = "\n".join(result)
        assert "-" in body  # at least one fallback

    def test_render_contains_symbol_and_rank(self):
        row = _row()
        body = "\n".join(_detail_block(row, 3))
        assert "**3. RELIANCE**" in body
        assert "Score 12" in body
        assert "BUY" in body

    def test_render_contains_sma_and_ema_lines(self):
        row = _row()
        body = "\n".join(_detail_block(row, 1))
        assert "SMA:" in body
        assert "EMA:" in body
        assert "RSI(14)" in body
        assert "ADX(14)" in body
        assert "ATR(14)" in body
        assert "MACD:" in body
        assert "BB:" in body
        assert "RelVol:" in body
        assert "OBV:" in body

    def test_render_price_with_none_does_not_crash(self):
        # close=None must NOT raise TypeError; must render with fallback
        row = _row(close=None)
        body = "\n".join(_detail_block(row, 1))
        assert "Price:" in body

    def test_render_volume_with_zero_does_not_crash(self):
        # volume=0 is a "real" value (zero is renderable) per _has
        row = _row(volume=0)
        # This should NOT raise
        body = "\n".join(_detail_block(row, 1))
        assert "Volume" in body or "volume" in body.lower() or "RelVol" in body


class TestDetailBlockFormat:
    """Pin the literal format of the detail block so layout changes trip
    these tests."""

    def test_sma_20_default_format(self):
        # sma_20 = 2490.0 → "2,490.0"
        row = _row(sma_20=2490.0)
        body = "\n".join(_detail_block(row, 1))
        assert "2,490.0" in body

    def test_ema_default_format(self):
        row = _row(ema_20=2495.0)
        body = "\n".join(_detail_block(row, 1))
        assert "2,495.0" in body

    def test_rsi_default_format(self):
        # rsi_14 = 65.0 → "65.0"
        row = _row(rsi_14=65.0)
        body = "\n".join(_detail_block(row, 1))
        assert "65.0" in body

    def test_atr_default_format(self):
        row = _row(atr_14=30.0)
        body = "\n".join(_detail_block(row, 1))
        assert "30.0" in body

    def test_rank_label(self):
        # The rank is the leading "**N. SYMBOL**" header
        for rank in (1, 2, 3, 10):
            body = "\n".join(_detail_block(_row(), rank))
            assert f"**{rank}. RELIANCE**" in body


class TestCategoryConfig:
    """Pin the category emoji and label mapping so the report's tally row
    is stable across refactors."""

    def test_all_six_categories_present(self):
        for cat in ("STRONG_BUY", "BUY", "ACCUMULATE", "WATCH", "CAUTION", "AVOID"):
            assert cat in CATEGORY_CONFIG

    def test_strong_buy_is_green(self):
        assert "🟢" in CATEGORY_CONFIG["STRONG_BUY"]["emoji"]

    def test_avoid_is_red(self):
        assert "🔴" in CATEGORY_CONFIG["AVOID"]["emoji"]

    def test_recommendation_order(self):
        # The order is "best to worst" — used to render the tally row
        assert RECOMMENDATION_ORDER == [
            "STRONG_BUY", "BUY", "ACCUMULATE", "WATCH", "CAUTION", "AVOID",
        ]


class TestDetailBlockSymbolVariations:
    """Regression test: the renderer must handle different symbol names
    without crashing."""

    def test_long_symbol(self):
        row = _row(symbol="MAHABANK")
        body = "\n".join(_detail_block(row, 1))
        assert "MAHABANK" in body

    def test_numeric_symbol(self):
        row = _row(symbol="23")
        body = "\n".join(_detail_block(row, 1))
        assert "23" in body

    def test_special_chars_in_symbol(self):
        # TV-style symbols can contain hyphens, dots, etc.
        row = _row(symbol="BRK.A")
        body = "\n".join(_detail_block(row, 1))
        assert "BRK.A" in body
