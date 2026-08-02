"""
tests/reports/test_labels.py — pure-function tests for reports/labels.py.

No DB, no network. These run in microseconds and prove the categorical
signal labels (OBV, MACD, BB, RSI, Gap, Vol, Verdict, Position, Narrative)
produce the same output for the same input — the deterministic contract
the report tests will rely on.
"""
from __future__ import annotations

from datetime import datetime, time

import pytest

from marketmeter.reports.labels import (
    obv_label, macd_label, bb_pos, rvol_signal, tv_rating_label,
    rsi_signal, gap_emoji, vol_emoji, verdict,
    market_state, position_in_range, position_label, narrative,
)
from marketmeter.reports.formatters import NA_EMDASH


class TestObvLabel:
    def test_zero_volume_returns_flat(self):
        assert obv_label(0, 0) == "↔ Flat"
        assert obv_label(1000, 0) == "↔ Flat"

    def test_positive_surging(self):
        # > 50% of daily volume
        assert obv_label(600, 1000) == "↑ Surging"

    def test_positive_rising(self):
        # 10-50% of daily volume
        assert obv_label(200, 1000) == "↑ Rising"

    def test_positive_steady(self):
        # < 10% of daily volume
        assert obv_label(50, 1000) == "↑ Steady"

    def test_negative_weakening(self):
        # obv < 0 (volume decrease)
        assert obv_label(-200, 1000) == "↓ Falling"

    def test_negative_weak(self):
        # -50 < obv < 0, smaller magnitude
        assert obv_label(-50, 1000) == "↓ Weak"

    def test_volume_required(self):
        # Even a positive OBV with zero volume must be flat (no volume = no info)
        assert obv_label(500, 0) == "↔ Flat"


class TestMacdLabel:
    def test_bullish(self):
        assert macd_label(5.0, 3.0) == "Bullish"

    def test_bearish(self):
        assert macd_label(2.0, 5.0) == "Bearish"

    def test_equal_neutral(self):
        # macd = signal → not bullish → "Bearish" (the strict inequality)
        assert macd_label(5.0, 5.0) == "Bearish"

    def test_none_returns_dash(self):
        assert macd_label(None, 3.0) == "-"
        assert macd_label(5.0, None) == "-"


class TestBbPos:
    def test_position_fractions(self):
        bb = (100.0, 50.0)  # (upper, lower)
        assert bb_pos(50.0, *bb) == "Near Lower"  # at low
        assert bb_pos(60.0, *bb) == "Mid-Lower"  # 20% of band
        assert bb_pos(75.0, *bb) == "Mid-Upper"  # 50% of band
        assert bb_pos(95.0, *bb) == "Near Upper"  # 90% of band
        assert bb_pos(100.0, *bb) == "Near Upper"  # at high

    def test_none_returns_dash(self):
        assert bb_pos(50.0, None, 0) == "-"
        assert bb_pos(50.0, 100, None) == "-"

    def test_zero_width_returns_dash(self):
        # upper == lower → division by zero
        assert bb_pos(50.0, 100.0, 100.0) == "-"


class TestRvolSignal:
    def test_buckets(self):
        assert rvol_signal(5.0) == "🔥 Spike"
        assert rvol_signal(2.0) == "High"
        assert rvol_signal(1.0) == "Normal"
        assert rvol_signal(0.5) == "Low"

    def test_thresholds(self):
        # The boundary is strict: rv > 3 (not >=), rv > 1.5, rv > 0.8
        assert rvol_signal(3.01) == "🔥 Spike"
        assert rvol_signal(3.0) == "High"  # 3.0 is NOT > 3
        assert rvol_signal(1.6) == "High"
        assert rvol_signal(1.5) == "Normal"  # 1.5 is NOT > 1.5
        assert rvol_signal(0.81) == "Normal"
        assert rvol_signal(0.8) == "Low"  # 0.8 is NOT > 0.8

    def test_none_returns_em_dash(self):
        assert rvol_signal(None) == NA_EMDASH


class TestTkRatingLabel:
    def test_buckets(self):
        assert tv_rating_label(1.5) == "Strong Buy"
        assert tv_rating_label(0.7) == "Buy"
        assert tv_rating_label(0.0) == "Neutral"
        assert tv_rating_label(-0.7) == "Sell"
        assert tv_rating_label(-1.5) == "Strong Sell"

    def test_thresholds(self):
        assert tv_rating_label(1.0) == "Strong Buy"
        assert tv_rating_label(0.5) == "Buy"
        assert tv_rating_label(-0.49) == "Neutral"  # -0.49 is the last Neutral
        assert tv_rating_label(-0.5) == "Sell"  # -0.5 is strict-Sell (boundary)
        assert tv_rating_label(-1.0) == "Strong Sell"
        assert tv_rating_label(-0.99) == "Sell"

    def test_none_returns_em_dash(self):
        assert tv_rating_label(None) == NA_EMDASH


class TestRsiSignal:
    def test_zones(self):
        assert rsi_signal(80) == "🔴"  # >= 70 overbought
        assert rsi_signal(70) == "🔴"
        assert rsi_signal(65) == "🟢"  # 60-79
        assert rsi_signal(60) == "🟢"
        assert rsi_signal(50) == "🟡"  # 40-59
        assert rsi_signal(40) == "🟡"
        assert rsi_signal(35) == "🔵"  # 30-39
        assert rsi_signal(30) == "🔵"
        assert rsi_signal(20) == "🔴"  # < 30 oversold

    def test_none_returns_em_dash(self):
        assert rsi_signal(None) == NA_EMDASH


class TestGapEmoji:
    def test_zones(self):
        assert gap_emoji(3.0) == "🚀"   # >= 2
        assert gap_emoji(2.0) == "🚀"
        assert gap_emoji(1.5) == "📈"   # 1-2
        assert gap_emoji(1.0) == "📈"
        assert gap_emoji(0.0) == "➡️"   # -1 to 1
        assert gap_emoji(-1.5) == "📉"  # -2 to -1
        assert gap_emoji(-3.0) == "💥"  # < -2

    def test_none_returns_em_dash(self):
        assert gap_emoji(None) == NA_EMDASH


class TestVolEmoji:
    def test_zones(self):
        assert vol_emoji(2.5) == "🔥"
        assert vol_emoji(2.0) == "🔥"
        assert vol_emoji(1.5) == "📊"
        assert vol_emoji(1.0) == "📊"
        assert vol_emoji(0.5) == "💤"

    def test_none_returns_em_dash(self):
        assert vol_emoji(None) == NA_EMDASH


class TestVerdict:
    def test_bullish_call_with_gap_up(self):
        assert verdict(1.0, "BUY") == "✓"

    def test_strong_buy_with_big_gap_up(self):
        assert verdict(5.0, "STRONG_BUY") == "✓"

    def test_accumulate_with_gap_up(self):
        assert verdict(0.6, "ACCUMULATE") == "✓"

    def test_bullish_call_with_gap_down(self):
        assert verdict(-1.0, "BUY") == "✗"

    def test_neutral_call_with_gap_up(self):
        # WATCH is not in the bullish list
        assert verdict(1.0, "WATCH") == "·"

    def test_neutral_call_with_gap_down(self):
        assert verdict(-1.0, "WATCH") == "·"

    def test_none_gap_returns_neutral(self):
        assert verdict(None, "BUY") == "·"

    def test_thresholds(self):
        # exactly 0.5 is on track
        assert verdict(0.5, "BUY") == "✓"
        # exactly -0.5 is fading
        assert verdict(-0.5, "BUY") == "✗"
        # 0.49 is neutral
        assert verdict(0.49, "BUY") == "·"


class TestMarketState:
    def test_pre_market(self):
        now = datetime(2026, 7, 31, 8, 0)  # 08:00 IST
        state, _ = market_state(now)
        assert state == "pre-market"

    def test_open(self):
        now = datetime(2026, 7, 31, 10, 0)  # 10:00 IST
        state, _ = market_state(now)
        assert state == "open"

    def test_closed(self):
        now = datetime(2026, 7, 31, 16, 0)  # 16:00 IST
        state, _ = market_state(now)
        assert state == "closed"

    def test_at_open_boundary(self):
        # exactly 09:15 → "open" (>= 09:15)
        now = datetime(2026, 7, 31, 9, 15)
        state, _ = market_state(now)
        assert state == "open"

    def test_at_close_boundary(self):
        # exactly 15:30 → still "open" (the check is `> 15:30`, not `>=`)
        now = datetime(2026, 7, 31, 15, 30)
        state, _ = market_state(now)
        assert state == "open"
        # one second past close
        now = datetime(2026, 7, 31, 15, 31)
        state, _ = market_state(now)
        assert state == "closed"


class TestPositionInRange:
    def test_at_low(self):
        assert position_in_range(50.0, 50.0, 100.0) == 0.0

    def test_at_high(self):
        assert position_in_range(100.0, 50.0, 100.0) == 1.0

    def test_middle(self):
        assert position_in_range(75.0, 50.0, 100.0) == 0.5

    def test_none_returns_none(self):
        assert position_in_range(None, 50.0, 100.0) is None
        assert position_in_range(75.0, None, 100.0) is None
        assert position_in_range(75.0, 50.0, None) is None

    def test_zero_range_returns_none(self):
        assert position_in_range(50.0, 50.0, 50.0) is None
        assert position_in_range(75.0, 100.0, 50.0) is None  # high < low


class TestPositionLabel:
    def test_zones(self):
        assert "near high" in position_label(0.95)
        assert "upper half" in position_label(0.75)
        assert "mid" in position_label(0.50)
        assert "lower half" in position_label(0.15)
        assert "near low" in position_label(0.05)

    def test_none_returns_em_dash(self):
        assert position_label(None) == NA_EMDASH


class TestNarrative:
    def test_overbought_rsi(self):
        s = {"rsi_14": 75}
        assert "overbought RSI" in narrative(s)

    def test_bullish_rsi(self):
        s = {"rsi_14": 65}
        assert "bullish RSI" in narrative(s)

    def test_weak_rsi(self):
        s = {"rsi_14": 35}
        assert "weak RSI" in narrative(s)

    def test_strong_trend(self):
        s = {"adx_14": 55}
        assert "very strong trend" in narrative(s)

    def test_moderate_trend(self):
        s = {"adx_14": 35}
        assert "strong trend" in narrative(s)

    def test_weak_trend(self):
        s = {"adx_14": 15}
        assert "weak trend" in narrative(s)

    def test_volume_surge(self):
        s = {"rel_volume": 4.0}
        assert "4.0x volume surge" in narrative(s)

    def test_volume_above_avg(self):
        s = {"rel_volume": 1.8}
        assert "1.8x above avg volume" in narrative(s)

    def test_macd_bullish(self):
        s = {"macd_line": 5.0, "signal_line": 3.0}
        assert "MACD bullish" in narrative(s)

    def test_above_sma20(self):
        s = {"close": 100.0, "sma_20": 95.0}
        assert "above SMA20" in narrative(s)

    def test_all_signals_combined(self):
        # Narrative only takes the first 4 parts; SMA20 is the 5th signal
        # and gets truncated.
        s = {"rsi_14": 65, "adx_14": 35, "rel_volume": 1.6,
             "macd_line": 5.0, "signal_line": 3.0, "close": 100.0, "sma_20": 95.0}
        n = narrative(s)
        assert "bullish RSI" in n
        assert "strong trend" in n
        assert "above avg volume" in n
        assert "MACD bullish" in n
        assert "above SMA20" not in n  # truncated at 4 parts

    def test_no_signals(self):
        assert narrative({}) == "Insufficient signal"

    def test_empty_dict(self):
        assert narrative({}) == "Insufficient signal"

    def test_max_four_parts(self):
        # At most 4 parts are joined
        s = {"rsi_14": 65, "adx_14": 35, "rel_volume": 1.6,
             "macd_line": 5.0, "signal_line": 3.0, "close": 100.0, "sma_20": 95.0}
        n = narrative(s)
        # Count semicolons in the narrative (4 parts → 3 semicolons)
        assert n.count(";") <= 3
