"""
Analysis Repository
Data access for daily technical analysis cache.
"""
import logging
from datetime import date
from typing import Any

from src.database.models import DailyAnalysis
from src.database.queries import *
from src.database.repositories.base import BaseRepository, ReadOnlyRepository

logger = logging.getLogger(__name__)


class AnalysisRepository(BaseRepository):
    """Repository for daily analysis operations."""

    def save_batch(self, analyses: list[DailyAnalysis]) -> int:
        """Bulk insert/update analysis results. Returns count of written rows."""
        if not analyses:
            return 0

        tuples = [a.to_db_tuple() for a in analyses]

        with get_connection() as conn:
            before = conn.total_changes
            conn.executemany(INSERT_ANALYSIS, tuples)
            written = conn.total_changes - before

            logger.info("Saved %d analysis rows", written)
            return written

    def get_latest_analysis(self, analysis_date: date | None = None) -> list[dict[str, Any]]:
        """Get analysis for a specific date (default: latest)."""
        if analysis_date is None:
            analysis_date = self.get_latest_analysis_date()
            if not analysis_date:
                return []

        return self.fetch_all(GET_LATEST_ANALYSIS, (analysis_date.isoformat(),))

    def get_latest_analysis_date(self) -> date | None:
        """Get the latest date that has analysis rows."""
        row = self.fetch_one(GET_LATEST_ANALYSIS_DATE)
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None

    def get_analysis_by_recommendation(self, analysis_date: date | None = None) -> dict[str, list[dict[str, Any]]]:
        """Get analysis grouped by recommendation category."""
        if analysis_date is None:
            analysis_date = self.get_latest_analysis_date()
            if not analysis_date:
                return {}

        rows = self.fetch_all(GET_ANALYSIS_BY_RECOMMENDATION, (analysis_date.isoformat(),))

        grouped = {
            "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
            "WATCH": [], "CAUTION": [], "AVOID": []
        }
        for r in rows:
            rec = r.get('recommendation', 'AVOID')
            if rec in grouped:
                grouped[rec].append(r)
        return grouped


class AnalysisReadRepository(ReadOnlyRepository):
    """Read-only repository for analysis queries."""

    def get_latest_analysis(self, analysis_date: date | None = None) -> list[dict[str, Any]]:
        """Get analysis for a specific date (default: latest)."""
        if analysis_date is None:
            analysis_date = self.get_latest_analysis_date()
            if not analysis_date:
                return []

        return self.fetch_all(GET_LATEST_ANALYSIS, (analysis_date.isoformat(),))

    def get_latest_analysis_date(self) -> date | None:
        """Get the latest date that has analysis rows."""
        row = self.fetch_one(GET_LATEST_ANALYSIS_DATE)
        if row and row['dt']:
            return date.fromisoformat(row['dt'])
        return None

    def get_analysis_by_recommendation(self, analysis_date: date | None = None) -> dict[str, list[dict[str, Any]]]:
        """Get analysis grouped by recommendation category."""
        if analysis_date is None:
            analysis_date = self.get_latest_analysis_date()
            if not analysis_date:
                return {}

        rows = self.fetch_all(GET_ANALYSIS_BY_RECOMMENDATION, (analysis_date.isoformat(),))

        grouped = {
            "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
            "WATCH": [], "CAUTION": [], "AVOID": []
        }
        for r in rows:
            rec = r.get('recommendation', 'AVOID')
            if rec in grouped:
                grouped[rec].append(r)
        return grouped
