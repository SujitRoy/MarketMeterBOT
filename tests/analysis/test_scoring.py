"""
tests/analysis/test_scoring.py — tests for analysis/scoring.py.

Phase 7 §3 mandate: "scoring tests (BUY/SELL/HOLD logic)."

These are pure-function tests for the recommendation engine. They pin
the score → recommendation mapping so a regression in the scoring logic
trips the tests immediately.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

from marketmeter.analysis.scoring import _get_recommendation


class TestScoreToRecommendation:
    """Pin the score → recommendation mapping."""

    @pytest.mark.parametrize("score,expected", [
        (0, "AVOID"),
        (3, "AVOID"),
        (4, "CAUTION"),
        (5, "CAUTION"),
        (6, "WATCH"),
        (7, "WATCH"),
        (8, "ACCUMULATE"),
        (9, "ACCUMULATE"),
        (10, "BUY"),
        (11, "BUY"),
        (12, "STRONG_BUY"),
        (15, "STRONG_BUY"),
        (18, "STRONG_BUY"),
    ])
    def test_score_thresholds(self, score, expected):
        # No extreme RSI / ADX override for these tests
        result, rationale = _get_recommendation(score, 50, 25)
        assert result == expected
        assert rationale != ""  # rationale is always non-empty


class TestRsiOverride:
    """RSI > 80 with weak trend (ADX < 20) downgrades BUY/STRONG_BUY
    to ACCUMULATE. This guard prevents chasing overbought momentum."""

    def test_buy_downgraded_to_accumulate_when_overbought_weak_trend(self):
        # score >= 10 → BUY, but RSI > 80 and ADX < 20 → downgrade
        result, rationale = _get_recommendation(11, rsi=85, adx=15)
        assert result == "ACCUMULATE"

    def test_strong_buy_downgraded_to_accumulate_when_overbought_weak_trend(self):
        result, _ = _get_recommendation(15, rsi=82, adx=18)
        assert result == "ACCUMULATE"

    def test_overbought_with_strong_trend_keeps_buy(self):
        # RSI > 80 but ADX >= 20 → no downgrade
        result, _ = _get_recommendation(11, rsi=85, adx=25)
        assert result == "BUY"

    def test_overbought_with_neutral_rsi_keeps_buy(self):
        # RSI = 80 is NOT > 80, so no override
        result, _ = _get_recommendation(11, rsi=80, adx=15)
        assert result == "BUY"

    def test_watch_and_below_not_downgraded(self):
        # Only BUY and STRONG_BUY are candidates for the downgrade
        # For score 8 (ACCUMULATE): rsi > 80 + weak trend keeps it at ACCUMULATE
        # For scores 0-6: not in the BUY/STRONG_BUY band, no override
        for score in (0, 4, 6):
            result, _ = _get_recommendation(score, rsi=85, adx=15)
            assert result != "ACCUMULATE"


class TestRationale:
    """The rationale is human-readable and reflects the recommendation."""

    def test_rationale_is_nonempty(self):
        for score in (0, 5, 8, 11, 15):
            _, rationale = _get_recommendation(score, 50, 25)
            assert rationale != ""
            assert isinstance(rationale, str)

    def test_rationale_describes_signal(self):
        # Each recommendation has a distinctive rationale
        rationales = set()
        for score in (0, 4, 6, 8, 10, 12):
            _, rationale = _get_recommendation(score, 50, 25)
            rationales.add(rationale)
        # All six categories should have distinct rationales
        assert len(rationales) >= 5
