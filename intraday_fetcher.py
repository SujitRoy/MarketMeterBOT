"""
intraday_fetcher.py — Phase 3 backward-compatibility shim.

Phase 3 of the modular refactor moved every function in this file to
src/marketmeter/sources/tradingview.py. This shim re-exports the full public
surface so existing call sites that still do `from intraday_fetcher import X`
continue to work without changes.

Phase 6 (final cleanup) removes this shim once every caller is updated to
import from marketmeter.sources.tradingview directly.

No behaviour change. This file is a pure re-export module.
"""
from __future__ import annotations

from marketmeter.sources.tradingview import (  # noqa: F401  (re-export)
    build_query,
    fetch_live_snapshot,
    aggregate_to_5min_candles,
    store_intraday_candles,
    run_intraday_ingest,
    add_symbol_to_tracking,
)

__all__ = [
    "build_query",
    "fetch_live_snapshot",
    "aggregate_to_5min_candles",
    "store_intraday_candles",
    "run_intraday_ingest",
    "add_symbol_to_tracking",
]


# Preserve the module-level entry point for `python -m` use.
if __name__ == "__main__":
    import sys
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    if len(sys.argv) > 1 and sys.argv[1] == "--add":
        sym = sys.argv[2].upper()
        add_symbol_to_tracking(sym)
        print(f"Added {sym} to tracking")
    else:
        result = run_intraday_ingest()
        print(result)