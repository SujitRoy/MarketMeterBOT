"""
analysis/scoring — composite score + recommendation mapping.

Phase 4 split: the recommendation logic from /analyzer.py:_get_recommendation
lives here. Pure function: takes a score + RSI + ADX and returns
(recommendation_label, narrative_suffix).

The composite score is computed in analyze_stock (analysis/analyzer.py);
this module only owns the score -> label mapping.
"""
from __future__ import annotations

from typing import Tuple


def _get_recommendation(score: int, rsi: float, adx: float) -> Tuple[str, str]:
    """
    Map composite score to one of STRONG_BUY / BUY / ACCUMULATE / WATCH / CAUTION / AVOID.

    Second return value is a short rationale string used by the morning
    report's category tally.

    The exact thresholds come from /analyzer.py:_get_recommendation (Phase 4
    moved it here verbatim). RSI and ADX additionally gate the final label so
    a high score with extreme RSI can still be downgraded.
    """
    if score >= 12:
        rec = "STRONG_BUY"
    elif score >= 10:
        rec = "BUY"
    elif score >= 8:
        rec = "ACCUMULATE"
    elif score >= 6:
        rec = "WATCH"
    elif score >= 4:
        rec = "CAUTION"
    else:
        rec = "AVOID"

    # Optional: down-grade if RSI is extreme and trend is weak
    if rsi is not None and adx is not None:
        if rsi > 80 and adx < 20 and rec in ("STRONG_BUY", "BUY"):
            rec = "ACCUMULATE"

    rationale = {
        "STRONG_BUY": "high composite signal",
        "BUY":        "strong momentum",
        "ACCUMULATE": "add on dips",
        "WATCH":      "monitor for setup",
        "CAUTION":    "overbought/weak",
        "AVOID":      "poor setup",
    }.get(rec, "")

    return rec, rationale


# Back-compat alias: old call sites used _get_recommendation (underscore).
_get_recommendation = _get_recommendation


__all__ = ["_get_recommendation"]
