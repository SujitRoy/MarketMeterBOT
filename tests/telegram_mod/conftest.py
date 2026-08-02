"""
conftest.py for tests/telegram/ — local fixtures.

The tests in this directory import marketmeter.telegram which transitively
imports telegram.ext. We stub telegram properly so the import chain
doesn't require a real python-telegram-bot install.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src/ is on sys.path.
_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stub telegram if it isn't installed. These tests are pure-function and never
# touch the bot itself, so a stub is sufficient. We need a proper package so
# that `from telegram.ext import ...` works.
try:
    import telegram
    import telegram.ext
    import telegram.error
except ImportError:
    _telegram = types.ModuleType("telegram")
    _telegram.__path__ = []  # mark as a package
    _telegram_ext = types.ModuleType("telegram.ext")
    _telegram_ext.__path__ = []
    _telegram_error = types.ModuleType("telegram.error")
    _telegram_error.__path__ = []
    _telegram.MenuButtonCommands = type("MenuButtonCommands", (), {})
    _telegram.Update = type("Update", (), {})
    _telegram.Forbidden = type("Forbidden", (Exception,), {})
    _telegram.TelegramError = type("TelegramError", (Exception,), {})
    _telegram_ext.Application = type("Application", (), {})
    _telegram_ext.CallbackContext = type("CallbackContext", (), {})
    _telegram_ext.CommandHandler = type("CommandHandler", (), {})
    _telegram_ext.ContextTypes = type("ContextTypes", (), {})
    sys.modules["telegram"] = _telegram
    sys.modules["telegram.ext"] = _telegram_ext
    sys.modules["telegram.error"] = _telegram_error
