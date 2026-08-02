"""
cli/cmd_sync — incremental sync command.
"""
from __future__ import annotations

from marketmeter.sources.nse import sync_incremental_data
from marketmeter.reports import generate_sync_status_message
from marketmeter.core.logging import get_logger

logger = get_logger(__name__)


async def cmd_sync():
    """Run incremental sync once."""
    logger.info("Running one-time sync...")
    result = sync_incremental_data()
    msg = generate_sync_status_message(result)
    print(msg)

    # If new data, run analysis
    if result['status'] == 'completed' and result['total_records'] > 0:
        logger.info("Running analysis on new data...")
        from marketmeter.analysis import run_batch_analysis
        analysis_result = run_batch_analysis()
        print(f"Analysis: {analysis_result['message']}")


__all__ = ["cmd_sync"]