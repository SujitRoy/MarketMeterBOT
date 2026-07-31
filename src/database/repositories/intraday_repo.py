"""
Intraday Repository
Data access for intraday candles, alerts, and tracked symbols.
"""
import json
import logging
from typing import Any

from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository

logger = logging.getLogger(__name__)


class IntradayRepository(BaseRepository):
    """Repository for intraday operations."""

    def init_tables(self) -> None:
        """Create intraday tables if they don't exist."""
        from src.database.connection import get_connection
        with get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS intraday_candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    candle_ts TIMESTAMP NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    vwap REAL,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    UNIQUE(symbol, candle_ts)
                );
                CREATE INDEX IF NOT EXISTS idx_intraday_symbol_ts
                    ON intraday_candles(symbol, candle_ts);
                
                CREATE TABLE IF NOT EXISTS intraday_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    candle_ts TIMESTAMP NOT NULL,
                    price REAL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_symbol_ts
                    ON intraday_alerts(symbol, candle_ts);
                
                CREATE TABLE IF NOT EXISTS tracked_symbols (
                    symbol TEXT PRIMARY KEY,
                    added_by TEXT DEFAULT 'AUTO_REPORT',
                    added_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    active BOOLEAN DEFAULT 1
                );
            """)
        logger.info("Intraday tables initialized")

    # ── Candles ──────────────────────────────────────────────────────

    def upsert_candles(self, rows: list[dict[str, Any]]) -> int:
        """Bulk insert/update 5-minute candles."""
        if not rows:
            return 0

        tuples = [
            (r["symbol"], r["candle_ts"], r.get("open"), r.get("high"),
             r.get("low"), r.get("close"), r.get("volume"), r.get("vwap"))
            for r in rows
        ]

        with get_connection() as conn:
            before = conn.total_changes
            conn.executemany(INSERT_INTRADAY_CANDLES, tuples)
            return conn.total_changes - before

    def get_candles(
        self,
        symbol: str,
        from_ts: str | None = None,
        limit: int = 78
    ) -> list[dict[str, Any]]:
        """Get intraday candles for a symbol."""
        if from_ts:
            return self.fetch_all(GET_INTRADAY_CANDLES, (symbol, from_ts, limit))
        else:
            return self.fetch_all(GET_INTRADAY_CANDLES_RECENT, (symbol, limit))

    def prune_old_candles(self, days: int = 30) -> int:
        """Remove intraday candles older than N days."""
        cur = self.execute(PRUNE_INTRADAY_CANDLES, (f'-{days} days',))
        logger.info("Pruned %d old intraday candles", cur)
        return cur

    # ── Tracked Symbols ─────────────────────────────────────────────

    def add_tracked_symbol(self, symbol: str, added_by: str = "MANUAL") -> bool:
        """Add symbol to intraday tracking list."""
        cur = self.execute(INSERT_TRACKED_SYMBOL, (symbol, added_by))
        return cur > 0

    def get_tracked_symbols(self) -> list[dict[str, Any]]:
        """Get all active tracked symbols."""
        return self.fetch_all(GET_TRACKED_SYMBOLS)

    def remove_tracked_symbol(self, symbol: str) -> bool:
        """Soft-delete a tracked symbol."""
        cur = self.execute(REMOVE_TRACKED_SYMBOL, (symbol,))
        return cur > 0

    # ── Alerts ───────────────────────────────────────────────────────

    def log_alert(
        self,
        symbol: str,
        alert_type: str,
        candle_ts: str,
        price: float,
        details: dict[str, Any]
    ) -> int:
        """Log an intraday alert."""
        with get_connection() as conn:
            cur = conn.execute(INSERT_INTRADAY_ALERT, (symbol, alert_type, candle_ts, price, json.dumps(details)))
            return cur.lastrowid

    def get_recent_alerts(self, symbol: str | None = None, hours: int = 24) -> list[dict[str, Any]]:
        """Get recent intraday alerts."""
        if symbol:
            return self.fetch_all(GET_RECENT_ALERTS, (symbol, f'-{hours} hours'))
        else:
            return self.fetch_all(GET_RECENT_ALERTS_ALL, (f'-{hours} hours',))

    def prune_old_alerts(self, days: int = 30) -> int:
        """Remove intraday alerts older than N days."""
        cur = self.execute(PRUNE_INTRADAY_ALERTS, (f'-{days} days',))
        logger.info("Pruned %d old intraday alerts", cur)
        return cur


class IntradayReadRepository(ReadOnlyRepository):
    """Read-only repository for intraday queries."""

    def get_candles(
        self,
        symbol: str,
        from_ts: str | None = None,
        limit: int = 78
    ) -> list[dict[str, Any]]:
        """Get intraday candles for a symbol."""
        if from_ts:
            return self.fetch_all(GET_INTRADAY_CANDLES, (symbol, from_ts, limit))
        else:
            return self.fetch_all(GET_INTRADAY_CANDLES_RECENT, (symbol, limit))

    def get_tracked_symbols(self) -> list[dict[str, Any]]:
        """Get all active tracked symbols."""
        return self.fetch_all(GET_TRACKED_SYMBOLS)

    def get_recent_alerts(self, symbol: str | None = None, hours: int = 24) -> list[dict[str, Any]]:
        """Get recent intraday alerts."""
        if symbol:
            return self.fetch_all(GET_RECENT_ALERTS, (symbol, f'-{hours} hours'))
        else:
            return self.fetch_all(GET_RECENT_ALERTS_ALL, (f'-{hours} hours',))
