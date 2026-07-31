"""
Live Data Transformer
Transforms live TradingView data into analysis-ready format.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def transform_live_snapshot(raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Transform live TradingView snapshot to standardized format.
    
    Maps TradingView column names to our internal schema.
    """
    transformed = []

    for d in raw_data:
        transformed.append({
            "symbol": d.get("symbol"),
            "close": d.get("close"),
            "open": d.get("open"),
            "high": d.get("high"),
            "low": d.get("low"),
            "volume": d.get("volume"),
            "change": d.get("change"),
            "change_abs": d.get("change_abs"),
            "VWAP": d.get("VWAP"),
            "RSI": d.get("RSI"),
            "MACD": d.get("MACD.macd"),
            "MACD_signal": d.get("MACD.signal"),
            "EMA9": d.get("EMA9"),
            "EMA21": d.get("EMA21"),
            "EMA50": d.get("EMA50"),
            "EMA200": d.get("EMA200"),
            "SMA20": d.get("SMA20"),
            "SMA50": d.get("SMA50"),
            "SMA200": d.get("SMA200"),
            "relative_volume": d.get("relative_volume_10d_calc"),
            "market_cap": d.get("market_cap_basic"),
            "pe_ratio": d.get("price_earnings_ttm"),
            "sector": d.get("sector"),
            "industry": d.get("industry"),
            "stoch_k": d.get("Stoch.K"),
            "stoch_d": d.get("Stoch.D"),
            "ADX": d.get("ADX"),
            "ATR": d.get("ATR"),
            "BB_upper": d.get("BB.upper"),
            "BB_lower": d.get("BB.lower"),
            "BB_basis": d.get("BB.basis"),
            "high_52w": d.get("high_52w"),
            "low_52w": d.get("low_52w"),
            "all_time_high": d.get("all_time_high"),
            "all_time_low": d.get("all_time_low"),
            "gross_margin": d.get("gross_margin_ttm"),
            "net_margin": d.get("net_margin_ttm"),
            "recommendation_all": d.get("Recommend.All"),
            "recommendation_ma": d.get("Recommend.MA"),
            "recommendation_other": d.get("Recommend.Other"),
            "timestamp": d.get("timestamp"),
            "exchange": d.get("exchange"),
        })

    return transformed


def merge_historical_live(
    historical: list[dict[str, Any]],
    live: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Merge historical EOD analysis with live pre-market data.
    
    Returns list of merged dicts with gap%, RSI delta, volume ratio, etc.
    """
    live_lookup = {d["symbol"]: d for d in live}

    merged = []
    for h in historical:
        sym = h["symbol"]
        live_data = live_lookup.get(sym)

        merged_row = {
            "symbol": sym,
            # Historical (EOD)
            "hist_close": h.get("close"),
            "hist_change": h.get("change"),
            "hist_volume": h.get("volume"),
            "hist_rsi": h.get("rsi_14"),
            "hist_adx": h.get("adx_14"),
            "hist_macd": h.get("macd_line"),
            "hist_macd_sig": h.get("signal_line"),
            "hist_sma20": h.get("sma_20"),
            "hist_sma50": h.get("sma_50"),
            "hist_sma200": h.get("sma_200"),
            "hist_ema20": h.get("ema_20"),
            "hist_ema50": h.get("ema_50"),
            "hist_ema200": h.get("ema_200"),
            "hist_atr": h.get("atr_14"),
            "hist_bb_upper": h.get("bb_upper"),
            "hist_bb_lower": h.get("bb_lower"),
            "hist_rel_vol": h.get("rel_volume"),
            "hist_obv": h.get("obv_trend"),
            "hist_avg_price": h.get("avg_price"),
            "hist_score": h.get("composite_score"),
            "hist_rec": h.get("recommendation"),
            # Live (pre-market)
            "live_close": live_data.get("close") if live_data else None,
            "live_change_abs": live_data.get("change_abs") if live_data else None,
            "live_change": live_data.get("change") if live_data else None,
            "live_volume": live_data.get("volume") if live_data else None,
            "live_vwap": live_data.get("VWAP") if live_data else None,
            "live_rsi": live_data.get("RSI") if live_data else None,
            # Derived
            "gap_pct": _calculate_gap(
                live_data.get("close") if live_data else None,
                h.get("close")
            ),
            "rsi_delta": _calculate_rsi_delta(
                live_data.get("RSI") if live_data else None,
                h.get("rsi_14")
            ),
            "vol_ratio": _calculate_vol_ratio(
                live_data.get("volume") if live_data else None,
                h.get("volume")
            ),
        }
        merged.append(merged_row)

    return merged


def _calculate_gap(live_ltp: float | None, eod_close: float | None) -> float | None:
    """Calculate gap percentage: (Live - EOD) / EOD * 100."""
    if live_ltp is None or eod_close is None or eod_close == 0:
        return None
    return ((live_ltp - eod_close) / eod_close) * 100


def _calculate_rsi_delta(live_rsi: float | None, eod_rsi: float | None) -> float | None:
    """Calculate RSI delta: Live - EOD."""
    if live_rsi is None or eod_rsi is None:
        return None
    return live_rsi - eod_rsi


def _calculate_vol_ratio(live_vol: int | None, eod_vol: int | None) -> float | None:
    """Calculate volume ratio: Live / EOD."""
    if live_vol is None or eod_vol is None or eod_vol == 0:
        return None
    return live_vol / eod_vol


def filter_by_gap(
    merged: list[dict[str, Any]],
    min_gap_up: float = 0,
    max_gap_down: float = 0
) -> list[dict[str, Any]]:
    """Filter merged data by gap percentage."""
    return [
        m for m in merged
        if m.get("gap_pct") is not None and
           (m["gap_pct"] >= min_gap_up or m["gap_pct"] <= max_gap_down)
    ]


def filter_by_volume_surge(
    merged: list[dict[str, Any]],
    min_ratio: float = 2.0
) -> list[dict[str, Any]]:
    """Filter merged data by volume surge ratio."""
    return [
        m for m in merged
        if m.get("vol_ratio") is not None and m["vol_ratio"] >= min_ratio
    ]


def filter_by_rsi_shift(
    merged: list[dict[str, Any]],
    min_delta: float = 10.0
) -> list[dict[str, Any]]:
    """Filter merged data by RSI momentum shift."""
    return [
        m for m in merged
        if m.get("rsi_delta") is not None and abs(m["rsi_delta"]) >= min_delta
    ]
