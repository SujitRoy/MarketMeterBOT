"""
tests/telegram/test_search_keyboards.py — tests for telegram/search/keyboards.py.

Phase 7 §3 mandate: "search-keyboard tests (pure, no network)."

The keyboard builders are pure functions — they take search results and
return an InlineKeyboardMarkup. These tests pin the keyboard layout so
a refactor that changes button labels or layout trips them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Avoid requiring telegram as a real dep for pure tests
import types
try:
    import telegram
except ImportError:
    _telegram = types.ModuleType("telegram")
    _telegram.InlineKeyboardButton = type("InlineKeyboardButton", (), {})
    _telegram.InlineKeyboardMarkup = type("InlineKeyboardMarkup", (), {})
    sys.modules["telegram"] = _telegram

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import pytest

from marketmeter.telegram.search.keyboards import (
    build_search_keyboard,
    _build_candidate_keyboard,
    _chart_keyboard,
)


class TestBuildSearchKeyboard:
    """The search results keyboard shows matches as inline buttons."""

    def test_empty_matches_returns_empty_markup(self):
        kb = build_search_keyboard([], query="foo")
        # Even with no matches, the Cancel button is present
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_match_button_includes_symbol(self):
        matches = [("RELIANCE", 95), ("TCS", 80)]
        kb = build_search_keyboard(matches, query="foo")
        # The keyboard should include the symbol names
        button_data = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("RELIANCE" in text for text in button_data)
        assert any("TCS" in text for text in button_data)

    def test_match_button_has_correct_callback(self):
        matches = [("RELIANCE", 95)]
        kb = build_search_keyboard(matches, query="foo")
        # callback_data should encode the symbol
        for row in kb.inline_keyboard:
            for btn in row:
                if "RELIANCE" in btn.text:
                    assert "RELIANCE" in btn.callback_data
                    assert btn.callback_data.startswith("search_select|")

    def test_cancel_button_present(self):
        matches = [("RELIANCE", 95)]
        kb = build_search_keyboard(matches, query="foo")
        button_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert any("cancel" in data for data in button_data)

    def test_each_match_gets_a_button(self):
        matches = [("A", 50), ("B", 50), ("C", 50), ("D", 50), ("E", 50)]
        kb = build_search_keyboard(matches, query="")
        # Each symbol should get a button (plus Cancel)
        symbol_buttons = 0
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data.startswith("search_select|"):
                    symbol_buttons += 1
        assert symbol_buttons == 5


class TestBuildCandidateKeyboard:
    """The candidate picker shows TV search results as buttons."""

    def test_candidates_get_buttons(self):
        candidates = ["RELIANCE", "TCS", "INFY"]
        names = {"RELIANCE": "Reliance Industries", "TCS": "Tata Consultancy"}
        kb = _build_candidate_keyboard(candidates, names)
        button_data = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("RELIANCE" in text for text in button_data)
        assert any("TCS" in text for text in button_data)
        assert any("INFY" in text for text in button_data)

    def test_includes_company_name_in_label(self):
        candidates = ["RELIANCE"]
        names = {"RELIANCE": "Reliance Industries"}
        kb = _build_candidate_keyboard(candidates, names)
        button_data = [btn.text for row in kb.inline_keyboard for btn in row]
        # Label should include the company name
        assert any("Reliance Industries" in text for text in button_data)

    def test_without_name_just_symbol(self):
        candidates = ["RELIANCE"]
        names = {}  # No name mapping
        kb = _build_candidate_keyboard(candidates, names)
        # Label should still include the symbol
        button_data = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("RELIANCE" in text for text in button_data)

    def test_callback_data_uses_symbol(self):
        candidates = ["RELIANCE"]
        names = {"RELIANCE": "Reliance Industries"}
        kb = _build_candidate_keyboard(candidates, names)
        for row in kb.inline_keyboard:
            for btn in row:
                if "RELIANCE" in btn.text:
                    assert "RELIANCE" in btn.callback_data

    def test_includes_cancel_button(self):
        candidates = ["RELIANCE"]
        names = {"RELIANCE": "Reliance"}
        kb = _build_candidate_keyboard(candidates, names)
        button_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "search_cancel" in button_data


class TestChartKeyboard:
    """The chart keyboard opens a TradingView chart and offers refresh."""

    def test_has_open_chart_button(self):
        kb = _chart_keyboard("RELIANCE")
        for row in kb.inline_keyboard:
            for btn in row:
                if "Chart" in btn.text or "chart" in btn.text.lower():
                    assert btn.url is not None
                    return
        assert False, "Expected an 'Open Chart' button"

    def test_has_refresh_button(self):
        kb = _chart_keyboard("RELIANCE")
        for row in kb.inline_keyboard:
            for btn in row:
                if "Refresh" in btn.text or "refresh" in btn.text.lower():
                    assert "RELIANCE" in btn.callback_data
                    return
        assert False, "Expected a 'Refresh' button"

    def test_chart_url_uses_nse_symbol(self):
        kb = _chart_keyboard("RELIANCE")
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.url is not None and "tradingview" in btn.url:
                    assert "NSE-RELIANCE" in btn.url
                    return
        assert False, "Expected a TradingView URL with NSE symbol"
