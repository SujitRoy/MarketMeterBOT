"""
db/intraday_repo — CRUD for the three intraday tables.

Phase 2 moves (verbatim from /database.py):
- upsert_intraday_candles
- get_intraday_candles
- add_tracked_symbol
- get_tracked_symbols
- remove_tracked_symbol
- log_intraday_alert
- get_recent_alerts
- prune_old_intraday

All SQL is byte-identical to the original.

Note: the `init_intraday_tables` function lives in db/schema.py because the
intraday schema is part of the schema bootstrap. This repo owns runtime CRUD
on those tables; schema.py owns their creation.
"""
from __future__ import annotations

import json
from typing import Optional

from marketmeter.core.logging import get_logger
from marketmeter.db.connection import get_connection

logger = get_logger(__name__)


def upsert_intraday_candles(rows: list[dict]) -> int:
    """Bulk insert/update 5-minute candles."""
    if not rows:
        return 0

    with get_connection() as conn:
        before = conn.total_changes
        conn.executemany("""
            INSERT OR REPLACE INTO intraday_candles
                (symbol, candle_ts, open, high, low, close, volume, vwap)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (r["symbol"], r["candle_ts"], r.get("open"), r.get("high"),
             r.get("low"), r.get("close"), r.get("volume"), r.get("vwap"))
            for r in rows
        ])
        return conn.total_changes - before


def get_intraday_candles(symbol: str, from_ts: Optional[str] = None, limit: int = 78) -> list[dict]:
    """
    Get intraday candles for a symbol.
    Default limit 78 = 6.5 hours * 12 (5-min buckets) = full trading day.
    """
    with get_connection() as conn:
        if from_ts:
            rows = conn.execute("""
                SELECT * FROM intraday_candles
                WHERE symbol = ? AND candle_ts >= ?
                ORDER BY candle_ts ASC
                LIMIT ?
            """, (symbol, from_ts, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM intraday_candles
                WHERE symbol = ?
                ORDER BY candle_ts DESC
                LIMIT ?
            """, (symbol, limit)).fetchall()
        return [dict(r) for r in rows]


def add_tracked_symbol(symbol: str, added_by: str = "MANUAL") -> bool:
    """Add symbol to intraday tracking list."""
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT OR REPLACE INTO tracked_symbols (symbol, added_by, active)
            VALUES (?, ?, 1)
        """, (symbol, added_by))
        return cur.rowcount > 0


def get_tracked_symbols() -> list[dict]:
    """Get all active tracked symbols."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT symbol, added_by, added_at FROM tracked_symbols
            WHERE active = 1
            ORDER BY added_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def remove_tracked_symbol(symbol: str) -> bool:
    """Soft-delete a tracked symbol."""
    with get_connection() as conn:
        cur = conn.execute("""
            UPDATE tracked_symbols SET active = 0 WHERE symbol = ?
        """, (symbol,))
        return cur.rowcount > 0


def log_intraday_alert(symbol: str, alert_type: str, candle_ts: str,
                        price: float, details: dict) -> int:
    """Log an intraday alert."""
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO intraday_alerts (symbol, alert_type, candle_ts, price, details)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, alert_type, candle_ts, price, json.dumps(details)))
        return cur.lastrowid


def get_recent_alerts(symbol: Optional[str] = None, hours: int = 24) -> list[dict]:
    """Get recent intraday alerts."""
    with get_connection() as conn:
        if symbol:
            rows = conn.execute("""
                SELECT * FROM intraday_alerts
                WHERE symbol = ? AND candle_ts >= datetime('now', ?)
                ORDER BY candle_ts DESC
            """, (symbol, f'-{hours} hours')).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM intraday_alerts
                WHERE candle_ts >= datetime('now', ?)
                ORDER BY candle_ts DESC
                LIMIT 100
            """, (f'-{hours} hours',)).fetchall()
        return [dict(r) for r in rows]


def prune_old_intraday(days: int = 30) -> None:
    """Remove intraday data older than N days."""
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM intraday_candles
            WHERE candle_ts < datetime('now', ?)
        """, (f'-{days} days',))
        conn.execute("""
            DELETE FROM intraday_alerts
            WHERE created_at < datetime('now', ?)
        """, (f'-{days} days',))
    logger.info("Pruned intraday data older than %d days", days)


__all__ = [
    "upsert_intraday_candles",
    "get_intraday_candles",
    "add_tracked_symbol",
    "get_tracked_symbols",
    "remove_tracked_symbol",
    "log_intraday_alert",
    "get_recent_alerts",
    "prune_old_intraday",
]