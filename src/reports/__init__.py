"""
Reports Package
All report types for MarketMeter.
"""
from src.reports.backtest import BacktestReport
from src.reports.base import (
    BaseReport,
    CompositeReport,
    ReportContext,
    ReportResult,
    TemplateReport,
)
from src.reports.custom import CustomReport
from src.reports.morning import MorningReport, generate_morning_report
from src.reports.premarket import (
    CombinedPreMarketReport,
    OpenCrossCheckReport,
    send_combined_premarket_report,
    send_open_crosscheck_report,
)
from src.reports.registry import register_report, registry
from src.reports.scanner import ScannerReport
from src.reports.sector import SectorReport
from src.reports.technical import TechnicalReport

__all__ = [
    # Base
    "BaseReport",
    "ReportContext",
    "ReportResult",
    "TemplateReport",
    "CompositeReport",

    # Registry
    "registry",
    "register_report",

    # Morning
    "MorningReport",
    "generate_morning_report",

    # Pre-market
    "OpenCrossCheckReport",
    "CombinedPreMarketReport",
    "send_open_crosscheck_report",
    "send_combined_premarket_report",

    # Other reports
    "TechnicalReport",
    "SectorReport",
    "ScannerReport",
    "BacktestReport",
    "CustomReport",
]
