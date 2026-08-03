"""
cli/cmd_analyze — analysis command.
"""
from __future__ import annotations

from marketmeter.analysis import run_batch_analysis


async def cmd_analyze():
    """Run analysis only."""
    result = run_batch_analysis()
    print(result['message'])


__all__ = ["cmd_analyze"]