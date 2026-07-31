"""
Technical analysis engine for NSE stocks.
Calculates indicators, scores stocks, and generates recommendations.
"""
import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    MIN_PRICE, MIN_VOLUME, MIN_DATA_POINTS, ANALYSIS_BATCH_SIZE,
)
from database import (
    get_all_symbols, get_stock_history, save_daily_analysis,
    get_latest_trade_date,
)

logger = logging.getLogger(__name__)


# ── Technical Indicators ────────────────────────────────────────────

def calc_sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window).mean()


def calc_ema(series: pd.Series, window: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=window, adjust=False).mean()


def calc_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram."""
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()


def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=window).mean()

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm_s = pd.Series(plus_dm, index=high.index).rolling(window=window).mean()
    minus_dm_s = pd.Series(minus_dm, index=high.index).rolling(window=window).mean()

    plus_di = 100 * (plus_dm_s / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm_s / atr.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(window=window).mean()


def calc_bollinger_bands(series: pd.Series, window: int = 20, num_std: int = 2):
    """Bollinger Bands: upper, middle, lower."""
    sma = calc_sma(series, window)
    std = series.rolling(window=window).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, sma, lower


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume).cumsum()
    return obv


# ── Single Stock Analysis ───────────────────────────────────────────

def analyze_stock(df: pd.DataFrame, symbol: str) -> Optional[dict]:
    """
    Full technical analysis for a single stock.
    Returns dict with all indicators and signals, or None if insufficient data.
    """
    if len(df) < MIN_DATA_POINTS:
        return None

    df = df.sort_values('trade_date').reset_index(drop=True)

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    current_price = close.iloc[-1]
    current_volume = int(volume.iloc[-1])

    # Basic filters
    if current_price < MIN_PRICE:
        return None
    if current_volume < MIN_VOLUME:
        return None

    # ── Calculate all indicators ──
    sma_20 = calc_sma(close, 20).iloc[-1]
    sma_50 = calc_sma(close, 50).iloc[-1]
    sma_100 = calc_sma(close, 100).iloc[-1] if len(close) >= 100 else np.nan
    sma_200 = calc_sma(close, 200).iloc[-1] if len(close) >= 200 else np.nan

    ema_20 = calc_ema(close, 20).iloc[-1]
    ema_50 = calc_ema(close, 50).iloc[-1]
    # EMA is recursive with no fixed lookback, so it is only reported once the
    # series is at least as long as the span. Below that the value is dominated
    # by its seed rather than by price action, and the report shows "-".
    ema_100 = calc_ema(close, 100).iloc[-1] if len(close) >= 100 else np.nan
    ema_200 = calc_ema(close, 200).iloc[-1] if len(close) >= 200 else np.nan

    rsi = calc_rsi(close, 14).iloc[-1]

    macd_line, signal_line, histogram = calc_macd(close)
    macd_latest = macd_line.iloc[-1]
    signal_latest = signal_line.iloc[-1]
    hist_latest = histogram.iloc[-1]

    atr = calc_atr(high, low, close, 14).iloc[-1]
    adx = calc_adx(high, low, close, 14).iloc[-1]

    bb_upper, _, bb_lower = calc_bollinger_bands(close, 20, 2)
    bb_upper_latest = bb_upper.iloc[-1]
    bb_lower_latest = bb_lower.iloc[-1]

    obv_series = calc_obv(close, volume)
    obv_latest = obv_series.iloc[-1]
    obv_20_ago = obv_series.iloc[-20] if len(obv_series) >= 20 else obv_series.iloc[0]
    obv_trend = obv_latest - obv_20_ago if not pd.isna(obv_20_ago) else 0

    # Relative Volume (20-day average)
    rel_volume = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else np.nan

    # Full-day average traded price. Prefer NSE's own AVG_PRICE column when the
    # row was synced with it; fall back to turnover/volume for older rows that
    # predate the column. Either way this is a full-day average, NOT an intraday
    # VWAP -- BhavCopy is one row per symbol per day.
    avg_price = np.nan
    if 'avg_price' in df.columns:
        nse_avg = df['avg_price'].iloc[-1]
        if nse_avg is not None and not pd.isna(nse_avg) and float(nse_avg) > 0:
            avg_price = float(nse_avg)
    if pd.isna(avg_price) and 'value_lakh' in df.columns:
        turnover = df['value_lakh'].iloc[-1]
        if turnover is not None and not pd.isna(turnover) and current_volume > 0:
            avg_price = (float(turnover) * 100_000.0) / current_volume

    # Price vs SMA percentages
    price_vs_sma20 = (current_price / sma_20 - 1) * 100 if not pd.isna(sma_20) else np.nan
    price_vs_sma50 = (current_price / sma_50 - 1) * 100 if not pd.isna(sma_50) else np.nan

    # Boolean signals
    above_sma20 = bool(current_price > sma_20) if not pd.isna(sma_20) else False
    above_sma50 = bool(current_price > sma_50) if not pd.isna(sma_50) else False
    above_sma100 = bool(current_price > sma_100) if not pd.isna(sma_100) else False
    macd_bullish = bool(macd_latest > signal_latest)
    macd_hist_positive = bool(hist_latest > 0)

    # ── Composite Score ──
    score = 0

    # RSI sweet spot (60-75)
    if not pd.isna(rsi):
        if 60 <= rsi <= 75:
            score += 3
        elif rsi > 75:
            score += 2
        elif rsi > 50:
            score += 1

    # ADX trend strength
    if not pd.isna(adx):
        if adx > 50:
            score += 3
        elif adx > 30:
            score += 2
        elif adx > 20:
            score += 1

    # Relative Volume
    if not pd.isna(rel_volume):
        if rel_volume > 3:
            score += 3
        elif rel_volume > 2:
            score += 2
        elif rel_volume > 1.5:
            score += 1

    # MACD
    if macd_bullish:
        score += 2

    # Above SMAs
    if above_sma20:
        score += 2
    if above_sma50:
        score += 2
    if above_sma100:
        score += 1

    # Price momentum vs SMA20
    if not pd.isna(price_vs_sma20) and price_vs_sma20 > 5:
        score += 1

    # OBV trend
    if obv_trend > 0:
        score += 1

    # ── Recommendation ──
    recommendation, reason = _get_recommendation(score, rsi, adx)

    # ── Trend Strength Label ──
    if not pd.isna(adx):
        if adx > 50:
            trend_strength = 'Very Strong'
        elif adx > 30:
            trend_strength = 'Strong'
        elif adx > 20:
            trend_strength = 'Moderate'
        else:
            trend_strength = 'Weak'
    else:
        trend_strength = 'N/A'

    # ── Momentum Label ──
    if not pd.isna(rsi):
        if rsi > 70:
            momentum = 'Overbought'
        elif rsi > 60:
            momentum = 'Bullish'
        elif rsi > 40:
            momentum = 'Neutral'
        elif rsi > 30:
            momentum = 'Bearish'
        else:
            momentum = 'Oversold'
    else:
        momentum = 'N/A'

    return {
        'symbol': symbol,
        'analysis_date': df['trade_date'].iloc[-1],
        'close': round(current_price, 2),
        'volume': current_volume,
        'rsi_14': round(rsi, 2) if not pd.isna(rsi) else None,
        'adx_14': round(adx, 2) if not pd.isna(adx) else None,
        'macd_line': round(macd_latest, 4) if not pd.isna(macd_latest) else None,
        'signal_line': round(signal_latest, 4) if not pd.isna(signal_latest) else None,
        'macd_hist': round(hist_latest, 4) if not pd.isna(hist_latest) else None,
        'sma_20': round(sma_20, 2) if not pd.isna(sma_20) else None,
        'sma_50': round(sma_50, 2) if not pd.isna(sma_50) else None,
        'sma_100': round(sma_100, 2) if not pd.isna(sma_100) else None,
        'sma_200': round(sma_200, 2) if not pd.isna(sma_200) else None,
        'ema_20': round(ema_20, 2) if not pd.isna(ema_20) else None,
        'ema_50': round(ema_50, 2) if not pd.isna(ema_50) else None,
        'ema_100': round(ema_100, 2) if not pd.isna(ema_100) else None,
        'ema_200': round(ema_200, 2) if not pd.isna(ema_200) else None,
        'atr_14': round(atr, 2) if not pd.isna(atr) else None,
        'bb_upper': round(bb_upper_latest, 2) if not pd.isna(bb_upper_latest) else None,
        'bb_lower': round(bb_lower_latest, 2) if not pd.isna(bb_lower_latest) else None,
        'rel_volume': round(rel_volume, 2) if not pd.isna(rel_volume) else None,
        'obv_trend': round(obv_trend, 2),
        'avg_price': round(avg_price, 2) if not pd.isna(avg_price) else None,
        'composite_score': score,
        'recommendation': recommendation,
        # Extra metadata (not stored in DB, used for reports)
        '_trend_strength': trend_strength,
        '_momentum': momentum,
        '_reason': reason,
        '_above_sma20': above_sma20,
        '_above_sma50': above_sma50,
        '_macd_bullish': macd_bullish,
        '_price_vs_sma20': round(price_vs_sma20, 2) if not pd.isna(price_vs_sma20) else None,
    }


def _get_recommendation(score: int, rsi: float, adx: float) -> tuple[str, str]:
    """Generate recommendation based on composite score and indicators."""
    rsi_val = rsi if not pd.isna(rsi) else 50
    adx_val = adx if not pd.isna(adx) else 20

    if score >= 12 and rsi_val < 70 and adx_val > 30:
        return "STRONG_BUY", "Excellent technical setup with strong trend"
    elif score >= 10 and rsi_val < 75 and adx_val > 25:
        return "BUY", "Strong technical signals, good momentum"
    elif score >= 8 and rsi_val < 80:
        return "ACCUMULATE", "Positive momentum, accumulate on dips"
    elif score >= 6:
        return "WATCH", "Monitor for confirmation before entry"
    elif rsi_val > 80 and score < 8:
        return "CAUTION", "Overbought with weak underlying trend"
    else:
        return "AVOID", "Weak technicals, better opportunities elsewhere"


# ── Batch Analysis ──────────────────────────────────────────────────

def run_batch_analysis(analysis_date: Optional[date] = None) -> dict:
    """
    Run technical analysis on all stocks with sufficient history.
    Caches results in daily_analysis table.
    Processes in small batches to limit memory usage.
    Returns summary dict.
    """
    if analysis_date is None:
        # analyze_stock labels each row with df['trade_date'].iloc[-1], i.e. the
        # latest *trade* date, not the wall clock. date.today() reported zeros
        # for every category because the sync runs at 18:30 and the newest
        # trade date is the previous session.
        analysis_date = get_latest_trade_date() or date.today()

    symbols = get_all_symbols(min_records=MIN_DATA_POINTS)
    total = len(symbols)
    logger.info("Starting batch analysis for %d symbols...", total)

    all_results = []
    analyzed = 0
    skipped = 0
    saved = 0

    for i, symbol in enumerate(symbols, 1):
        if i % ANALYSIS_BATCH_SIZE == 0:
            logger.info("Analysis progress: %d/%d symbols (%d analyzed, %d skipped)",
                        i, total, analyzed, skipped)

        history = get_stock_history(symbol, min_days=MIN_DATA_POINTS)
        if not history:
            skipped += 1
            continue

        df = pd.DataFrame(history)
        result = analyze_stock(df, symbol)

        if result:
            all_results.append(result)
            analyzed += 1
        else:
            skipped += 1

        # Save in batches to limit memory
        if len(all_results) >= ANALYSIS_BATCH_SIZE:
            # Accumulate: reassigning here discarded every earlier batch's
            # count, so the figure sent to the owner was only the last batch.
            saved += save_daily_analysis(all_results)
            logger.info("Saved batch to DB (%d rows written so far)", saved)
            all_results.clear()

    # Save remaining
    if all_results:
        saved += save_daily_analysis(all_results)
        logger.info("Saved final batch of analysis results to DB")

    # Count by recommendation - we need to query DB since we cleared memory
    from database import get_analysis_by_recommendation
    grouped = get_analysis_by_recommendation(analysis_date)
    rec_counts = {k: len(v) for k, v in grouped.items()}

    summary = {
        'status': 'completed',
        'analysis_date': analysis_date.isoformat(),
        'total_symbols': total,
        'analyzed': analyzed,
        'skipped': skipped,
        'saved': saved,
        'recommendation_counts': rec_counts,
        'message': (
            f"Analysis complete: {analyzed} stocks analyzed, {skipped} skipped. "
            f"BUY: {rec_counts.get('STRONG_BUY', 0) + rec_counts.get('BUY', 0)}, "
            f"ACCUMULATE: {rec_counts.get('ACCUMULATE', 0)}, "
            f"WATCH: {rec_counts.get('WATCH', 0)}, "
            f"CAUTION/AVOID: {rec_counts.get('CAUTION', 0) + rec_counts.get('AVOID', 0)}"
        ),
    }

    logger.info(summary['message'])

    # Warm the report cache while the data is fresh, so the 08:00 broadcast and
    # every on-demand /report become pure cache reads instead of a ~1.1s render.
    # Local import: report_generator imports this module.
    try:
        from report_generator import warm_report_cache
        if warm_report_cache(analysis_date):
            logger.info("Report cache warmed for %s", analysis_date)
    except Exception as e:
        # A cold cache only costs latency, so never fail the analysis run.
        logger.warning("Could not warm report cache: %s", e)

    return summary


def get_market_outlook(analysis_date: Optional[date] = None) -> dict:
    """
    Generate a market-level outlook from the analysis cache.

    Takes the resolved analysis_date so it reads the same day as the report
    body. Previously it defaulted to the latest row independently, which could
    disagree with the grouped data it was rendered beside.
    """
    from database import get_latest_analysis

    results = get_latest_analysis(analysis_date)
    if not results:
        return {
            'outlook': 'N/A',
            'bullish_pct': 0,
            'bearish_pct': 0,
            'avg_rsi': None,
            'avg_adx': None,
            'total_stocks': 0,
        }

    df = pd.DataFrame(results)
    total = len(df)

    bullish = len(df[df['recommendation'].isin(['STRONG_BUY', 'BUY', 'ACCUMULATE'])])
    bearish = len(df[df['recommendation'].isin(['CAUTION', 'AVOID'])])

    bullish_pct = round(bullish / total * 100, 1) if total > 0 else 0
    bearish_pct = round(bearish / total * 100, 1) if total > 0 else 0

    avg_rsi = round(df['rsi_14'].mean(), 1) if 'rsi_14' in df.columns else None
    avg_adx = round(df['adx_14'].mean(), 1) if 'adx_14' in df.columns else None

    if bullish_pct > 60:
        outlook = 'Bullish 📈'
    elif bullish_pct > 40:
        outlook = 'Neutral ↔️'
    elif bearish_pct > 50:
        outlook = 'Bearish 📉'
    else:
        outlook = 'Mixed 🔀'

    return {
        'outlook': outlook,
        'bullish_pct': bullish_pct,
        'bearish_pct': bearish_pct,
        'neutral_pct': round(100 - bullish_pct - bearish_pct, 1),
        'avg_rsi': avg_rsi,
        'avg_adx': avg_adx,
        'total_stocks': total,
    }


def get_analysis_aggregate(analysis_date: Optional[date] = None) -> tuple[dict, dict]:
    """
    Single-pass: read the analysis rows ONCE and return (grouped, outlook).

    The report previously fetched the same rows twice — once grouped by
    recommendation, once for the market outlook. Here we read them once and
    derive both shapes in memory. Outlook values are computed to be identical
    to get_market_outlook() so the render is byte-for-byte unchanged.
    """
    from database import get_latest_analysis

    results = get_latest_analysis(analysis_date)

    grouped: dict[str, list[dict]] = {
        "STRONG_BUY": [], "BUY": [], "ACCUMULATE": [],
        "WATCH": [], "CAUTION": [], "AVOID": []
    }
    for r in results:
        rec = r.get('recommendation', 'AVOID')
        if rec in grouped:
            grouped[rec].append(r)

    if not results:
        outlook = {
            'outlook': 'N/A', 'bullish_pct': 0, 'bearish_pct': 0,
            'avg_rsi': None, 'avg_adx': None, 'total_stocks': 0,
        }
        return grouped, outlook

    total = len(results)
    bullish = sum(len(grouped[k]) for k in ('STRONG_BUY', 'BUY', 'ACCUMULATE'))
    bearish = sum(len(grouped[k]) for k in ('CAUTION', 'AVOID'))
    bullish_pct = round(bullish / total * 100, 1) if total > 0 else 0
    bearish_pct = round(bearish / total * 100, 1) if total > 0 else 0

    # Mirror get_market_outlook: mean over the (non-null) rsi_14 / adx_14 values.
    rsi_vals = [r['rsi_14'] for r in results if r.get('rsi_14') is not None]
    adx_vals = [r['adx_14'] for r in results if r.get('adx_14') is not None]
    avg_rsi = round(sum(rsi_vals) / len(rsi_vals), 1) if rsi_vals else None
    avg_adx = round(sum(adx_vals) / len(adx_vals), 1) if adx_vals else None

    if bullish_pct > 60:
        outlook_lbl = 'Bullish 📈'
    elif bullish_pct > 40:
        outlook_lbl = 'Neutral ↔️'
    elif bearish_pct > 50:
        outlook_lbl = 'Bearish 📉'
    else:
        outlook_lbl = 'Mixed 🔀'

    outlook = {
        'outlook': outlook_lbl,
        'bullish_pct': bullish_pct,
        'bearish_pct': bearish_pct,
        'neutral_pct': round(100 - bullish_pct - bearish_pct, 1),
        'avg_rsi': avg_rsi,
        'avg_adx': avg_adx,
        'total_stocks': total,
    }
    return grouped, outlook
