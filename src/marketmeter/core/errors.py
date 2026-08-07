"""
core/errors — minimal exception hierarchy for the MarketMeter stack.

Only BhavcopyNotPublished is actually used (in nse.py).
"""
from __future__ import annotations


class MarketMeterError(Exception):
    """Base for every error raised by MarketMeter code."""


class BhavcopyNotPublished(MarketMeterError):
    """NSE returned 404: the file does not exist yet (or the date is a holiday)."""


__all__ = [
    "MarketMeterError",
    "BhavcopyNotPublished",
]