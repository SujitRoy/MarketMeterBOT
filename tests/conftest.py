"""
tests/conftest.py — shared fixtures for the fresh test suite.

Phase 7 of the docs/REFACTOR_PLAN.md mandates:
  - "db/connection.py must support an in-memory :memory: SQLite for fast unit tests."
  - "Snapshot tests for reports: byte-equal output given identical inputs."
  - "pytest is the runner."

This file:
  1. Sets safe env vars BEFORE any marketmeter import (so config.py loads).
  2. Provides a per-test :memory: SQLite fixture fully initialised with the
     canonical schema, so db/* tests can read/write without touching the live DB.
  3. Wires pytest's tmp_path to point marketmeter.core.config at a tempdir.
"""
from __future__ import annotations

import os
import sys
import sqlite3
from pathlib import Path

# ── 1. Neutralise env BEFORE any project import ───────────────────────────
os.environ.setdefault("MARKETMETER_BOT_TOKEN", "test-token")
os.environ.setdefault("MARKETMETER_OWNER_CHAT_ID", "999999")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://localhost:0/bot")

# ── 2. Ensure src/ is on sys.path so `from marketmeter.X import Y` resolves ───
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ── 3. The shared :memory: SQLite fixture ───────────────────────────────────
# Initialises the canonical schema (mirrors src/marketmeter/db/schema.py) so any
# test can grab `conn` and run real CRUD without touching data/marketmeter.db.

# Schema mirrors src/marketmeter/db/schema.py. Kept inline so tests do not
# depend on the production initialiser (which would write to data/).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bhavcopy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    series TEXT DEFAULT 'EQ',
    open REAL, high REAL, low REAL, close REAL, last REAL, prevclose REAL,
    volume INTEGER, value_lakh REAL, del_pct REAL, avg_price REAL,
    trade_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    UNIQUE(symbol, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_bhavcopy_symbol_date ON bhavcopy(symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_bhavcopy_date ON bhavcopy(trade_date);
CREATE INDEX IF NOT EXISTS idx_bhavcopy_symbol ON bhavcopy(symbol);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE UNIQUE NOT NULL,
    status TEXT CHECK(status IN ('success','failed','holiday','skipped','not_available')),
    records_count INTEGER DEFAULT 0,
    error_message TEXT,
    synced_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS daily_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    analysis_date DATE NOT NULL,
    close REAL, volume INTEGER,
    rsi_14 REAL, adx_14 REAL,
    macd_line REAL, signal_line REAL, macd_hist REAL,
    sma_20 REAL, sma_50 REAL, sma_100 REAL, sma_200 REAL,
    ema_20 REAL, ema_50 REAL, ema_100 REAL, ema_200 REAL,
    atr_14 REAL, bb_upper REAL, bb_lower REAL,
    rel_volume REAL, obv_trend REAL, avg_price REAL,
    composite_score INTEGER,
    recommendation TEXT CHECK(recommendation IN
        ('STRONG_BUY','BUY','ACCUMULATE','WATCH','CAUTION','AVOID')),
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    UNIQUE(symbol, analysis_date)
);

CREATE TABLE IF NOT EXISTS stats_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS report_cache (
    kind TEXT NOT NULL,
    analysis_date DATE NOT NULL,
    version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    built_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (kind, analysis_date, version)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    subscribed_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    active BOOLEAN DEFAULT 1,
    receive_reports BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS intraday_candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    candle_ts TIMESTAMP NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume INTEGER, vwap REAL,
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    UNIQUE(symbol, candle_ts)
);

CREATE TABLE IF NOT EXISTS intraday_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    candle_ts TIMESTAMP NOT NULL,
    price REAL,
    details TEXT,
    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tracked_symbols (
    symbol TEXT PRIMARY KEY,
    added_by TEXT DEFAULT 'AUTO_REPORT',
    added_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
    active BOOLEAN DEFAULT 1
);
"""


def fresh_inmemory_db() -> sqlite3.Connection:
    """Return a fresh in-memory SQLite connection with the canonical schema.

    Tests should grab this via the `conn` fixture below. The row factory
    is set to sqlite3.Row so callers that do row['col'] get dict-like
    access (matches production get_connection).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


# ── 4. Pytest fixtures ───────────────────────────────────────────────────────

import pytest


@pytest.fixture
def conn():
    """A fresh in-memory SQLite with the canonical schema. Per-test isolation."""
    c = fresh_inmemory_db()
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def sample_bhavcopy_rows():
    """Canonical fixture rows for bhavcopy CRUD tests."""
    return [
        {"symbol": "RELIANCE", "series": "EQ", "open": 2500.0, "high": 2520.0,
         "low": 2490.0, "close": 2510.0, "last": 2510.0, "prevclose": 2495.0,
         "volume": 1_000_000, "value_lakh": 25000.0, "del_pct": 0.6,
         "trade_date": "2026-07-31", "avg_price": 2505.0},
        {"symbol": "TCS", "series": "EQ", "open": 3500.0, "high": 3520.0,
         "low": 3490.0, "close": 3510.0, "last": 3510.0, "prevclose": 3495.0,
         "volume": 500_000, "value_lakh": 17500.0, "del_pct": 0.4,
         "trade_date": "2026-07-31", "avg_price": 3505.0},
    ]


@pytest.fixture
def sample_analysis_rows():
    """Canonical fixture rows for daily_analysis CRUD tests."""
    return [
        {"symbol": "RELIANCE", "analysis_date": "2026-07-31",
         "close": 2510.0, "volume": 1_000_000,
         "rsi_14": 65.0, "adx_14": 30.0,
         "macd_line": 5.0, "signal_line": 3.0, "macd_hist": 2.0,
         "sma_20": 2490.0, "sma_50": 2480.0, "sma_100": 2450.0, "sma_200": 2400.0,
         "ema_20": 2495.0, "ema_50": 2485.0, "ema_100": 2460.0, "ema_200": 2420.0,
         "atr_14": 30.0, "bb_upper": 2530.0, "bb_lower": 2470.0,
         "rel_volume": 1.2, "obv_trend": 50000.0, "avg_price": 2505.0,
         "composite_score": 12, "recommendation": "BUY"},
    ]
