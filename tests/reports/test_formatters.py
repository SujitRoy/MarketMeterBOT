"""
tests/reports/test_formatters.py — pure-function tests for reports/formatters.py.

These are the most important tests for Path A's speed claim: they have
NO database, NO network, and run in microseconds. They prove the new
None-safe formatters fix the pre-existing NoneType.__format__ bug that
crashed the morning report on symbols with no close yet.
"""
from __future__ import annotations

import math

import pytest

from marketmeter.reports.formatters import (
    NA_DASH, NA_EMDASH,
    _has, fmt, price_rupees, price_rupees_compact, signed_pct,
    fmt_int, fmt_mcap, gap_pct, vol_ratio,
)


class TestHas:
    def test_none_is_not_a_value(self):
        assert _has(None) is False

    def test_int_is_a_value(self):
        assert _has(0) is True
        assert _has(42) is True
        assert _has(-1) is True

    def test_zero_float_is_a_value_but_zero_int(self):
        # NOTE: 0 IS renderable; only None / NaN are "not a value"
        assert _has(0.0) is True

    def test_nan_is_not_a_value(self):
        assert _has(float("nan")) is False

    def test_str_zero_is_a_value(self):
        # _has only checks for None / NaN. Strings (including empty) are
        # considered renderable values; the format() call decides whether to
        # actually render them.
        assert _has("0") is True
        assert _has("") is True
        assert _has("foo") is True

    def test_bool_is_treated_as_value(self):
        # bool is a subclass of int, so it IS a value
        assert _has(True) is True
        assert _has(False) is True


class TestFmt:
    def test_default_format(self):
        assert fmt(1234.5) == "1,234.5"

    def test_custom_spec(self):
        assert fmt(1234.5, ",.2f") == "1,234.50"
        assert fmt(1234.5678, ",.4f") == "1,234.5678"

    def test_integer(self):
        assert fmt(42, "d") == "42"
        assert fmt(1000, ",d") == "1,000"

    def test_none_returns_dash(self):
        assert fmt(None) == "-"
        assert fmt(None, ",.2f") == "-"

    def test_none_with_em_dash_fallback(self):
        assert fmt(None, fallback="—") == "—"

    def test_nan_returns_fallback(self):
        assert fmt(float("nan")) == "-"
        assert fmt(float("nan"), fallback="—") == "—"

    def test_invalid_format_returns_fallback(self):
        # Passing a string where a number is expected → format() raises ValueError
        # → fmt returns the fallback rather than crashing
        result = fmt("not a number", ",.2f")
        assert result == "-"


class TestPriceRupees:
    def test_basic(self):
        assert price_rupees(2500.5) == "₹2,500.50"
        assert price_rupees(2500) == "₹2,500.00"

    def test_none_renders_as_dash(self):
        # This is the fix for the pre-existing NoneType.__format__ crash
        # that crashed the morning report on symbols with no close yet.
        assert price_rupees(None) == "₹-"

    def test_compact(self):
        assert price_rupees_compact(2500.5) == "₹2,500"
        assert price_rupees_compact(None) == "₹-"


class TestSignedPct:
    def test_positive(self):
        assert signed_pct(1.5) == "+1.50%"
        assert signed_pct(0.5) == "+0.50%"

    def test_negative(self):
        assert signed_pct(-3.25) == "-3.25%"

    def test_zero(self):
        assert signed_pct(0) == "+0.00%"

    def test_none(self):
        assert signed_pct(None) == NA_EMDASH  # default em-dash


class TestFmtInt:
    def test_basic(self):
        assert fmt_int(1_000_000) == "1,000,000"
        assert fmt_int(42) == "42"

    def test_none(self):
        assert fmt_int(None) == NA_DASH


class TestFmtMcap:
    def test_small_mcap(self):
        # 1e7 raw = 1 Crore. The function formats as K Cr (1000 Cr = 1K Cr).
        # So 1 Cr renders as 0.00K Cr.
        result = fmt_mcap(1e7)
        assert "Cr" in result
        assert "0.00K Cr" in result

    def test_medium_mcap(self):
        # 1e10 raw = 1000 Cr = 1K Cr
        result = fmt_mcap(1e10)
        assert "K Cr" in result
        assert "1.00K Cr" in result

    def test_large_mcap(self):
        # 1e12 raw = 100K Cr = 1L Cr
        result = fmt_mcap(1e12)
        assert "L Cr" in result
        assert "1.00L Cr" in result

    def test_none(self):
        assert fmt_mcap(None) == NA_DASH


class TestGapPct:
    def test_positive_gap(self):
        # EOD 100, live 103 → +3.00%
        assert gap_pct(103.0, 100.0) == pytest.approx(3.0)

    def test_negative_gap(self):
        # EOD 100, live 97 → -3.00%
        assert gap_pct(97.0, 100.0) == pytest.approx(-3.0)

    def test_zero_gap(self):
        assert gap_pct(100.0, 100.0) == 0.0

    def test_none_eod_returns_none(self):
        assert gap_pct(100.0, None) is None

    def test_none_live_returns_none(self):
        assert gap_pct(None, 100.0) is None

    def test_zero_eod_returns_none(self):
        # Division by zero guard
        assert gap_pct(100.0, 0.0) is None


class TestVolRatio:
    def test_normal(self):
        assert vol_ratio(1_000_000, 500_000) == 2.0
        assert vol_ratio(500_000, 1_000_000) == 0.5

    def test_none_returns_none(self):
        assert vol_ratio(None, 1_000_000) is None
        assert vol_ratio(1_000_000, None) is None

    def test_zero_avg_returns_none(self):
        # Division by zero guard
        assert vol_ratio(1_000_000, 0) is None


class TestNaGlyphs:
    def test_constants(self):
        assert NA_DASH == "-"
        assert NA_EMDASH == "—"
