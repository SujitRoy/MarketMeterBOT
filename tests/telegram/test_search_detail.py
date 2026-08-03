"""
tests/telegram/test_search_detail.py — regression guard for /search detail.

The detail formatter returns a fully joined Rich Markdown string.  A previous
refactor accidentally re-joined that string with "\\n", which iterated the
string character-by-character and produced the spaced-out garbage seen in
Telegram chat.  These tests pin the contract:

  * format_live_detail() returns a normal multi-line string.
  * send_live_stock_detail() passes that string through to _send_rich_chunks.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

from marketmeter.telegram.search.detail import (
    format_live_detail,
    send_live_stock_detail,
)


MINIMAL_LIVE_DATA = {
    "close": 100.0,
    "change_abs": 1.5,
    "change": 1.52,
    "volume": 123456,
    "high": 101.0,
    "low": 99.0,
    "open": 99.5,
    "VWAP": 100.2,
    "RSI": 55.0,
    "relative_volume_10d_calc": 1.2,
    "exchange": "NSE",
    "description": "Test Corp",
}


class TestFormatLiveDetail:
    """The formatter must return a real string, not something that needs
    another round of joining."""

    def test_returns_multiline_string(self):
        msg = format_live_detail("TEST", MINIMAL_LIVE_DATA)
        assert isinstance(msg, str)
        assert "\n" in msg
        # First line should be the symbol header, not a single character.
        first_line = msg.splitlines()[0]
        assert "TEST" in first_line

    def test_rel_vol_signal_in_one_cell(self):
        """Regression: the Rel Vol row must fit in a 2-column table."""
        msg = format_live_detail("TEST", MINIMAL_LIVE_DATA)
        for line in msg.splitlines():
            if "Rel Vol" in line:
                # Exactly two cells: "| **Rel Vol (10d)** | 1.20x · Normal |"
                assert line.count("|") == 3, f"ragged row: {line}"


class TestSendLiveStockDetail:
    """send_live_stock_detail must not double-join the formatted message."""

    def test_passes_string_not_character_list(self):
        fake_update = MagicMock()
        fake_update.message.reply_text = AsyncMock()
        fake_update.message.reply_text.return_value.delete = AsyncMock()
        fake_update.get_bot.return_value = MagicMock()
        fake_update.effective_chat.id = 12345

        async def run():
            with patch(
                "marketmeter.telegram.search.detail.fetch_live_for_symbol",
                new=AsyncMock(return_value=MINIMAL_LIVE_DATA),
            ):
                with patch(
                    "marketmeter.telegram.search.detail._send_rich_chunks",
                    new=AsyncMock(return_value=1),
                ) as mock_send:
                    await send_live_stock_detail(fake_update, "TEST")
            return mock_send

        mock_send = asyncio.run(run())
        assert mock_send.called
        _, args, kwargs = mock_send.mock_calls[0]
        bot, chat_id, sent_message = args[0], args[1], args[2]

        assert isinstance(sent_message, str)
        assert "TEST" in sent_message
        # The first line must contain the symbol header, not be one char.
        assert len(sent_message.splitlines()[0]) > 5
        # And the message must not look like "T\\nE\\nS\\nT".
        assert sent_message.count("\n") > 5
        assert "T\nE" not in sent_message
