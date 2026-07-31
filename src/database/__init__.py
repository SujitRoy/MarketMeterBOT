"""
Database Package
Centralized database access layer with repositories.
"""
from src.database.connection import (
    get_connection,
    get_readonly_connection,
    init_database,
    vacuum_database,
    check_database_health,
)

from src.database.models import (
    BhavCopyRow,
    DailyAnalysis,
    SyncLogEntry,
    Subscriber,
    IntradayCandle,
    IntradayAlert,
    TrackedSymbol,
    ReportCacheEntry,
    DBStats,
)

from src.database.repositories import (
    BhavCopyRepository,
    BhavCopyReadRepository,
    AnalysisRepository,
    AnalysisReadRepository,
    SyncRepository,
    SyncReadRepository,
    SubscriberRepository,
    SubscriberReadRepository,
    ReportCacheRepository,
    ReportCacheReadRepository,
    IntradayRepository,
    IntradayReadRepository,
    StatsRepository,
)

# Re-export queries for direct access if needed
from src.database import queries

__all__ = [
    # Connection
    "get_connection",
    "get_readonly_connection",
    "init_database",
    "vacuum_database",
    "check_database_health",
    
    # Models
    "BhavCopyRow",
    "DailyAnalysis",
    "SyncLogEntry",
    "Subscriber",
    "IntradayCandle",
    "IntradayAlert",
    "TrackedSymbol",
    "ReportCacheEntry",
    "DBStats",
    
    # Repositories
    "BhavCopyRepository",
    "BhavCopyReadRepository",
    "AnalysisRepository",
    "AnalysisReadRepository",
    "SyncRepository",
    "SyncReadRepository",
    "SubscriberRepository",
    "SubscriberReadRepository",
    "ReportCacheRepository",
    "ReportCacheReadRepository",
    "IntradayRepository",
    "IntradayReadRepository",
    "StatsRepository",
    
    # Queries
    "queries",
]