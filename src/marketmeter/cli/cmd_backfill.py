"""
cli/cmd_backfill — historical backfill command.
"""
from __future__ import annotations

from marketmeter.sources.nse import backfill_historical_data
from marketmeter.core.logging import get_logger

logger = get_logger(__name__)


async def cmd_backfill():
    """Run full historical backfill."""
    logger.info("Starting full historical backfill...")
    print("This will download data from 2021-04-01 to today.")
    print("Estimated time: 20-30 minutes for ~1100 trading days.")
    response = input("Continue? (y/n): ").strip().lower()

    if response != 'y':
        print("Aborted.")
        return

    result = backfill_historical_data()
    print(f"\nBackfill complete: {result['message']}")

    # Run analysis after backfill
    logger.info("Running initial analysis...")
    from marketmeter.analysis import run_batch_analysis
    analysis_result = run_batch_analysis()
    print(f"Analysis: {analysis_result['message']}")


__all__ = ["cmd_backfill"]