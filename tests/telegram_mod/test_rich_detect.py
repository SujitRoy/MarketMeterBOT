"""
tests/telegram_mod/test_rich_detect.py — tests for the Rich Message detector.

`_needs_rich` decides whether a message must go through the Rich
Message path. A wrong answer here either downgrades a Rich message
(strips bold + table pipes) or upgrades a plain message (sends a tiny
markdown through a Rich endpoint and corrupts it).

These are pure-function tests. They run in microseconds.
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

from marketmeter.telegram.rich.detect import _needs_rich


class TestNeedsRich:
    """Pin what counts as Rich syntax."""

    def test_plain_text_is_not_rich(self):
        # Plain text without **, <details, or tables is NOT rich
        assert _needs_rich("Hello world") is False

    def test_bold_makes_it_rich(self):
        # **bold** is a Rich TextBold block, not legacy markdown
        assert _needs_rich("This is **important**") is True

    def test_multiple_bold_is_rich(self):
        assert _needs_rich("**a** and **b**") is True

    def test_details_makes_it_rich(self):
        # <details> is a Rich block, not supported by V1 markdown
        assert _needs_rich("<details><summary>x</summary>y</details>") is True

    def test_details_open_makes_it_rich(self):
        assert _needs_rich("<details open><summary>x</summary></details>") is True

    def test_table_makes_it_rich(self):
        # Tables render as native blocks; V1 markdown has no tables
        assert _needs_rich("| A | B |\n|--|--|\n| 1 | 2 |") is True

    def test_pipe_in_first_line_makes_it_rich(self):
        # Even a single pipe at the start of a line signals a table
        assert _needs_rich("| just a pipe") is True

    def test_pipe_in_middle_line_does_not(self):
        # A pipe in the middle of a line is not a table
        assert _needs_rich("this | that") is False

    def test_empty_string_is_not_rich(self):
        assert _needs_rich("") is False

    def test_multiline_pipe_makes_it_rich(self):
        # Even one pipe on the first line is enough
        assert _needs_rich("| table\n| more |") is True

    def test_starts_with_details_open(self):
        # Even just "<details" without the closing tag triggers rich
        assert _needs_rich("<details>") is True
