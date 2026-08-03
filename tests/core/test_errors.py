"""
tests/core/test_errors.py — tests for marketmeter/core/errors.py.

Phase 7 §3 mandate: "typed exception tests (marketmeter.core.errors)."

The exception hierarchy is the contract between data sources and consumers.
A test here pins the inheritance chain so a caller can rely on
catching the right type.
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

from marketmeter.core.errors import (
    MarketMeterError,
    DataSourceError,
    BhavcopyNotPublished,
    BhavcopyFetchError,
    TradingViewError,
    TradingViewAuthError,
    TradingViewRateLimitError,
    AnalysisError,
    InsufficientDataError,
    ReportError,
    NoDataForDateError,
)


class TestHierarchy:
    """Every custom exception must inherit from MarketMeterError so a
    single `except MarketMeterError:` catches all in-app errors."""

    def test_all_inherit_from_marketmeter_error(self):
        all_errors = [
            DataSourceError, BhavcopyNotPublished, BhavcopyFetchError,
            TradingViewError, TradingViewAuthError, TradingViewRateLimitError,
            AnalysisError, InsufficientDataError,
            ReportError, NoDataForDateError,
        ]
        for exc in all_errors:
            assert issubclass(exc, MarketMeterError), f"{exc.__name__} does not inherit from MarketMeterError"

    def test_marketmeter_error_inherits_from_exception(self):
        assert issubclass(MarketMeterError, Exception)

    def test_data_source_inherits_from_marketmeter(self):
        assert issubclass(DataSourceError, MarketMeterError)

    def test_bhavcopy_inherits_from_data_source(self):
        assert issubclass(BhavcopyNotPublished, DataSourceError)
        assert issubclass(BhavcopyFetchError, DataSourceError)

    def test_tv_inherits_from_data_source(self):
        assert issubclass(TradingViewError, DataSourceError)
        assert issubclass(TradingViewAuthError, DataSourceError)
        assert issubclass(TradingViewRateLimitError, DataSourceError)

    def test_analysis_inherits_from_marketmeter(self):
        assert issubclass(AnalysisError, MarketMeterError)
        assert issubclass(InsufficientDataError, AnalysisError)

    def test_report_inherits_from_marketmeter(self):
        assert issubclass(ReportError, MarketMeterError)
        assert issubclass(NoDataForDateError, ReportError)


class TestExceptionBehaviour:
    def test_can_be_raised_and_caught(self):
        with pytest.raises(BhavcopyNotPublished):
            raise BhavcopyNotPublished("NSE has not published 2026-07-31 yet")

    def test_caught_by_parent(self):
        with pytest.raises(MarketMeterError):
            raise BhavcopyNotPublished("any reason")

    def test_caught_by_data_source(self):
        with pytest.raises(DataSourceError):
            raise BhavcopyNotPublished("any reason")

    def test_message_is_preserved(self):
        msg = "specific failure: 404"
        with pytest.raises(BhavcopyNotPublished, match=msg):
            raise BhavcopyNotPublished(msg)

    def test_can_carry_kwargs(self):
        with pytest.raises(BhavcopyFetchError):
            raise BhavcopyFetchError("timeout")

    def test_all_can_be_raised_without_args(self):
        for exc in [
            BhavcopyNotPublished("x"), TradingViewError("x"),
            AnalysisError("x"), ReportError("x"), MarketMeterError("x"),
        ]:
            assert isinstance(exc, Exception)
            assert str(exc) == "x"
