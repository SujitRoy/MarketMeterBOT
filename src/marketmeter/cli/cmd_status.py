"""
cli/cmd_status — status command.
"""
from __future__ import annotations

from marketmeter.db import get_db_stats


async def cmd_status():
    """Print database status."""
    stats = get_db_stats()
    print("=" * 50)
    print("MarketMeter Database Status")
    print("=" * 50)
    for key, value in stats.items():
        print(f"  {key}: {value}")


__all__ = ["cmd_status"]