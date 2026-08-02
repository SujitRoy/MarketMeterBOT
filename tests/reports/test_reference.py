"""
tests/reports/test_reference.py — tests for reports/reference.py.

The reference module hosts three static Rich-Markdown messages:
  * generate_welcome_message
  * generate_help_message
  * generate_indicators_message

These are pure-string functions — no DB, no network — so they're the
easiest tests to run. They pin the messages so layout changes trip them.
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

from marketmeter.reports.reference import (
    generate_welcome_message,
    generate_help_message,
    generate_indicators_message,
)


class TestWelcomeMessage:
    def test_includes_user_name(self):
        msg = generate_welcome_message("Alice")
        assert "Alice" in msg

    def test_uses_default_name_when_none(self):
        msg = generate_welcome_message()
        assert "there" in msg or "Hello" in msg

    def test_contains_marketmeter_branding(self):
        assert "MarketMeter" in generate_welcome_message("Bob")

    def test_lists_commands(self):
        msg = generate_welcome_message("Carol")
        # All the primary commands should be mentioned
        for cmd in ("/start", "/report", "/status", "/help",
                    "/search", "/indicators", "/subscribe", "/unsubscribe"):
            assert cmd in msg, f"welcome message missing {cmd}"


class TestHelpMessage:
    def test_is_static_rich_markdown(self):
        msg = generate_help_message()
        # Should be a non-empty string
        assert isinstance(msg, str)
        assert len(msg) > 100

    def test_contains_marketmeter_branding(self):
        assert "MarketMeter" in generate_help_message()

    def test_lists_all_commands(self):
        msg = generate_help_message()
        for cmd in ("/start", "/report", "/status", "/help",
                    "/search", "/indicators", "/subscribe", "/unsubscribe"):
            assert cmd in msg, f"help message missing {cmd}"


class TestIndicatorsMessage:
    def test_explains_each_indicator(self):
        msg = generate_indicators_message()
        # Each indicator should be in the glossary
        for ind in ("RSI", "ADX", "RelVol", "OBV", "BB", "MACD", "LTP", "AvgPrice"):
            assert ind in msg, f"indicators message missing {ind}"

    def test_contains_glossary_section(self):
        msg = generate_indicators_message()
        # A "composite score" or similar explanation should be present
        assert "composite" in msg.lower() or "score" in msg.lower()

    def test_is_rich_markdown(self):
        msg = generate_indicators_message()
        # Must contain **bold** markers
        assert "**" in msg
        # Must contain a <details> block (Rich syntax)
        assert "<details" in msg
