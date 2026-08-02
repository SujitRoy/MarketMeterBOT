"""
tests/core/test_config.py — tests for marketmeter/core/config.py.

These tests verify that config.py correctly:
  * Requires MARKETMETER_BOT_TOKEN and MARKETMETER_OWNER_CHAT_ID env vars.
  * Returns correct types (int, str, float, Path).
  * Provides the right DB_PATH relative to the project root.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Ensure env vars exist before any import of config.py.
os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

import pytest

from marketmeter import core
from marketmeter.core import config


class TestConfigLoads:
    """The config module must load cleanly when env vars are present."""

    def test_bot_token_loaded(self):
        assert config.BOT_TOKEN == "test-token"

    def test_owner_chat_id_loaded_as_int(self):
        assert isinstance(config.OWNER_CHAT_ID, int)
        assert config.OWNER_CHAT_ID == 999999

    def test_db_path_is_path(self):
        assert isinstance(config.DB_PATH, Path)

    def test_data_dir_is_path(self):
        assert isinstance(config.DATA_DIR, Path)

    def test_log_dir_is_path(self):
        assert isinstance(config.LOG_DIR, Path)


class TestConfigDefaults:
    """Constants that have no env var must have correct types."""

    def test_timezone_is_ist(self):
        assert config.TIMEZONE == "Asia/Kolkata"

    def test_min_price_is_float(self):
        assert isinstance(config.MIN_PRICE, float)
        assert config.MIN_PRICE == 20.0

    def test_min_volume_is_int(self):
        assert isinstance(config.MIN_VOLUME, int)
        assert config.MIN_VOLUME == 10_000

    def test_api_base_url_is_string(self):
        assert isinstance(config.TELEGRAM_API_BASE_URL, str)

    def test_token_max_chars_is_int(self):
        assert isinstance(config.RICH_MESSAGE_MAX_CHARS, int)
        assert config.RICH_MESSAGE_MAX_CHARS == 32_768
