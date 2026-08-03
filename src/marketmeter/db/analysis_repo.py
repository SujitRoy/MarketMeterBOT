"""
db/analysis_repo — CRUD for the `daily_analysis` table.

Phase 2 moves (verbatim from /database.py):
- save_daily_analysis
- get_latest_analysis
- get_resolved_analysis_date
- get_analysis_by_recommendation

All SQL is byte-identical to the original.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from marketmeter.db.connection import get_connection


def save_daily_analysis(rows: list[dict]) -> int:
    """Bulk insert/update analysis results using executemany. Returns count."""
    if not rows:
        return 0

    with get_connection() as conn:
        columns = [
            'symbol', 'analysis_date', 'close', 'volume',
            'rsi_14', 'adx_14', 'macd_line', 'signal_line', 'macd_hist',
            'sma_20', 'sma_50', 'sma_100', 'sma_200',
            'ema_20', 'ema_50', 'ema_100', 'ema_200',
            'atr_14', 'bb_upper', 'bb_lower',
            'rel_volume', 'obv_trend', 'avg_price',
            'composite_score', 'recommendation'
        ]
        tuples = [tuple(r.get(c) for c in columns) for r in rows]

        # O(1) counter instead of a COUNT(*) pair. Note INSERT OR REPLACE
        # counts both the delete and the insert of a replaced row, so this is
        # "rows written", which is what the caller reports.
        before = conn.total_changes

        conn.executemany("""
            INSERT OR REPLACE INTO daily_analysis
                (symbol, analysis_date, close, volume,
                 rsi_14, adx_14, macd_line, signal_line, macd_hist,
                 sma_20, sma_50, sma_100, sma_200,
                 ema_20, ema_50, ema_100, ema_200,
                 atr_14, bb_upper, bb_lower,
                 rel_volume, obv_trend, avg_price,
                 composite_score, recommendation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?)
        """, tuples)

        return conn.total_changes - before


def get_latest_analysis(analysis_date: Optional[date] = None) -> list[dict]:
    """Get analysis for a specific date (default: latest)."""
    with get_connection() as conn:
        if analysis_date is None:
            # Get latest analysis date
            row = conn.execute(
                "SELECT MAX(analysis_date) as dt FROM daily_analysis"
            ).fetchone()
            if not row or not row['dt']:
                return []
            analysis_date = row['dt']

        rows = conn.execute("""
            SELECT * FROM daily_analysis
            WHERE analysis_date = ?
            ORDER BY composite_score DESC
        """, (analysis_date.isoformat() if isinstance(analysis_date, date) else analysis_date,)).fetchall()
        return [dict(r) for r in rows]


def get_resolved_analysis_date() -> Optional[date]:
    """
    The latest date that actually has analysis rows.

    Callers must resolve through this rather than assuming date.today():
    analysis runs after the 6:30 PM sync, so between midnight and the next
    run date.today() has zero rows. Keying a cache on today() would store the
    empty "no data" report and serve it all day.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(analysis_date) as dt FROM daily_analysis"
        ).fetchone()
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None


def get_analysis_by_recommendation(analysis_date: Optional[date] = None) -> dict[str, list[dict]]:
    """Get analysis grouped by recommendation category."""
    results = get_latest_analysis(analysis_date)
    grouped: dict[str, list[dict]] = {
        "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
        "WATCH": [], "CAUTION": [], "AVOID": []
    }
    for r in results:
        rec = r.get('recommendation', 'AVOID')
        if rec in grouped:
            grouped[rec].append(r)
    return grouped


def analysis_date_exists(target_date: date) -> bool:
    """Check if analysis data exists for a specific date."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM daily_analysis WHERE analysis_date = ? LIMIT 1",
            (target_date.isoformat(),),
        ).fetchone()
        return row is not None


def get_analysis_date_range() -> tuple[Optional[date], Optional[date]]:
    """Get the earliest and latest analysis_date in daily_analysis."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MIN(analysis_date) as mn, MAX(analysis_date) as mx FROM daily_analysis"
        ).fetchone()
        mn = date.fromisoformat(row['mn']) if row['mn'] else None
        mx = date.fromisoformat(row['mx']) if row['mx'] else None
        return mn, mx


__all__ = [
    "save_daily_analysis",
    "get_latest_analysis",
    "get_resolved_analysis_date",
    "get_analysis_by_recommendation",
    "analysis_date_exists",
    "get_analysis_date_range",
]