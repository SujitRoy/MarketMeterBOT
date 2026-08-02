"""
reports/reference — /indicators, /welcome, /help message bodies.

Phase 4 split: these three large message bodies moved here because they are
reference text rather than data-driven reports. They don't depend on db or
analysis; they're pure constants with light templating.
"""
from __future__ import annotations


# Pull BOT_DISPLAY_NAME only when callers actually need it; the reference
# messages here are pure strings and never interpolate it. Re-export keeps
# the shim working.
__all__ = [
    "generate_indicators_message",
    "generate_welcome_message",
    "generate_help_message",
]


def generate_indicators_message() -> str:
    """Indicator glossary for /indicators, in Rich Markdown.

    Sized to stay inside the Rich Message limits: each <details> block is its own
    unit so _split_rich_markdown can break between blocks without ever cutting
    one open. Blank line after every </summary> so the server parses the body.
    """
    return """📊 **Technical Indicators — Full Forms & Meanings**

Every indicator below feeds the composite score that ranks stocks in /report.

---

**📋 Quick Reference**

| Code | Full Form | Simple Meaning |
|:-----|:----------|:---------------|
| RSI | Relative Strength Index | How fast is it moving? |
| ADX | Average Directional Index | How strong is the move? |
| RelVol | Relative Volume | Are people interested today? |
| OBV | On-Balance Volume | Is money flowing in or out? |
| BB | Bollinger Bands | Is it high or low vs recent prices? |
| MACD | Moving Average Convergence Divergence | Is momentum building or fading? |
| LTP | Last Traded Price | Closing price for the day |
| AvgPrice | Average Price | Day's average traded price |

---

<details><summary>**1️⃣ RSI — Relative Strength Index**</summary>

• **Measures:** speed and magnitude of price changes
• **Range:** 0 to 100
• **> 70** = Overbought (may fall)
• **< 30** = Oversold (may rise)
• **Best for:** spotting potential reversals

**In this bot:** RSI 60-75 scores highest (+3). Above 75 scores +2, since
overbought names can keep running but carry more risk.

</details>

<details><summary>**2️⃣ ADX — Average Directional Index**</summary>

• **Measures:** strength of a trend, not its direction
• **Range:** 0 to 100
• **> 25** = strong trend | **> 50** = very strong | **< 20** = no trend
• **Best for:** confirming a trend is worth following

⚠️ ADX tells you if a trend is STRONG, not whether it is UP or DOWN.

**In this bot:** ADX > 50 scores +3, > 30 scores +2, > 20 scores +1.

</details>

<details><summary>**3️⃣ RelVol — Relative Volume**</summary>

• **Measures:** today's volume against its own 20-day average
• **Formula:** today's volume ÷ average volume (last 20 days)
• **> 1.5x** = above-average interest | **> 2x** = strong | **> 3x** = exceptional
• **Best for:** confirming a price move has real backing

**In this bot:** > 3x scores +3, > 2x scores +2, > 1.5x scores +1.

</details>

<details><summary>**4️⃣ OBV — On-Balance Volume**</summary>

• **Measures:** cumulative buying vs selling pressure
• **Formula:** add volume on up days, subtract on down days
• **↑ Surging / Rising** = buying pressure | **↓ Falling** = selling pressure
• **Divergence** (price up, OBV down) is a warning sign
• **Best for:** checking a trend has volume support

**In this bot:** the 20-day OBV change is compared to daily volume; a rising
OBV scores +1.

</details>

<details><summary>**5️⃣ BB — Bollinger Bands**</summary>

• **Measures:** volatility and where price sits in its recent range
• **Upper** = SMA20 + (2 × StdDev) | **Middle** = SMA20 | **Lower** = SMA20 − (2 × StdDev)
• **Near Upper** = stretched high | **Near Lower** = stretched low
• **Squeeze** (narrow bands) often precedes a large move
• **Best for:** identifying price extremes

**In this bot:** shown as position (Near Upper / Mid-Upper / Mid-Lower / Near Lower).

</details>

<details><summary>**6️⃣ MACD — Moving Average Convergence Divergence**</summary>

• **Measures:** momentum and trend direction
• **MACD Line** = EMA12 − EMA26 | **Signal** = EMA9 of MACD | **Histogram** = MACD − Signal
• **Bullish** = MACD above Signal | **Bearish** = MACD below Signal
• **Best for:** catching trend and momentum changes

**In this bot:** MACD above Signal scores +2. Note a stock can read Bullish
while both lines are still negative — that is momentum improving from a low base.

</details>

<details><summary>**🧮 How the Composite Score Works**</summary>

Each stock earns points, then the total maps to a recommendation.

| Factor | Points |
|:-------|:-------|
| RSI 60-75 | +3 |
| RSI > 75 | +2 |
| RSI > 50 | +1 |
| ADX > 50 | +3 |
| ADX > 30 | +2 |
| ADX > 20 | +1 |
| RelVol > 3x | +3 |
| RelVol > 2x | +2 |
| RelVol > 1.5x | +1 |
| MACD bullish | +2 |
| Above SMA20 | +2 |
| Above SMA50 | +2 |
| Above SMA100 | +1 |
| Price > 5% over SMA20 | +1 |
| OBV rising | +1 |

Higher totals map to STRONG BUY / BUY, mid to ACCUMULATE / WATCH, low to
CAUTION / AVOID. RSI and ADX also gate the final label, so a high score with
extreme RSI can still be downgraded.

</details>

<details><summary>**🎯 Reading Signals Together**</summary>

No single indicator is sufficient; agreement across them is what matters.

| Scenario | What to look for |
|:---------|:-----------------|
| Strong setup | RSI 60-75 + ADX > 25 + RelVol > 1.5x + OBV rising + MACD bullish |
| Warning | RSI > 80 + ADX < 20 + RelVol < 0.8x + OBV falling |
| Trend confirmed | ADX > 30 + MACD bullish + OBV rising |
| Breakout check | RelVol > 2x + RSI > 60 + ADX > 25 + price near BB upper |

</details>

---

📊 All indicators are computed on **full price history** from 2022-01-03, so
the 200-period values are exact rather than approximated.

⚠️ _Not financial advice. Indicators describe past price action and never
guarantee future moves._"""


def generate_welcome_message(first_name: str = "there") -> str:
    """Welcome message for new users. QuicklixBot-style Rich Markdown."""
    return f"""👋 **Hello {first_name}!**

**Welcome to MarketMeter** — your daily NSE stock analysis assistant.

---

**📊 What this bot does:**
📥 Downloads daily BhavCopy data from NSE
📊 Runs technical analysis on all 3,000+ stocks
📈 Sends morning reports with BUY/WATCH/AVOID signals

---

**🎯 Your Daily Edge**

| Feature | Status |
|:--------|:------:|
| **EOD Data** | ✅ 6:30 PM IST |
| **Live Prices** | ✅ 9:00 AM IST |
| **Full History** | ✅ 2022-01-03 → latest trading day |
| **Indicators** | ✅ 15+ technicals |
| **Coverage** | ✅ 3,000+ NSE stocks |

---

**⚡ Quick Commands**

| Command | Description |
|:--------|:------------|
| `/start` | This welcome message |
| `/subscribe` | Get daily morning reports |
| `/unsubscribe` | Stop receiving reports |
| `/report` | Get today's analysis on demand |
| `/status` | Check sync & database status |
| `/indicators` | RSI, ADX, MACD, SMA/EMA explained |
| `/search <symbol|name>` | Live price + full details |
| `/help` | Show detailed help |

---

**🔍 How it works**

```
1️⃣ EOD Sync (6:30 PM) → Download BhavCopy → Store in SQLite
2️⃣ Analysis → RSI, ADX, MACD, EMA/SMA, Volume, OBV
3️⃣ Score → Composite 0-18 → STRONG BUY → AVOID
4️⃣ Report (8:30 AM) → Top 25 + Full scan table
5️⃣ Pre-market (9:00 AM) → Live prices for tracked symbols
```

---

**📈 Report Categories**

<details open><summary>**📊 Signal Legend**</summary>

| Emoji | Signal | Score | Action |
|:-----:|:-------|:-----:|:-------|
| 🟢 | **STRONG BUY** | 12-18 | High conviction entry |
| 🟢 | **BUY** | 10-11 | Strong momentum |
| 🟡 | **ACCUMULATE** | 8-9 | Add on dips |
| 🔵 | **WATCH** | 6-7 | Monitor for setup |
| 🟠 | **CAUTION** | <6 | Overbought/weak |
| 🔴 | **AVOID** | <6 | Poor setup |

</details>

---

**🔔 Pre-Market Live Prices**
• **9:00 AM IST** — Live quotes for tracked symbols
• **/search RELIANCE** — Instant live quote + 15 indicators

---

**💡 Pro Tips**
<details><summary>**📖 Learn More**</summary>

• `/indicators` — Full glossary & scoring rules
• `/search <name>` — Fuzzy search (e.g. `/search airtel` → BHARTIARTL)
• `/status` — Database health, sync history, subscriber count

</details>

---

⚠️ _Not financial advice. All analysis based on technical indicators only._"""


def generate_help_message() -> str:
    """Help message with all commands. Rich Markdown."""
    return """🆘 **MarketMeter Help**

**Commands**

| Command | Description |
|:--------|:------------|
| /start | Welcome message |
| /subscribe | Subscribe to daily reports |
| /unsubscribe | Unsubscribe from reports |
| /report | Get latest analysis report |
| /status | Database & sync status |
| /indicators | Indicator meanings & scoring |
| /search <symbol|name> | Live price & full details |
| /help | This message |

**How it works**

1️⃣ Bot downloads BhavCopy data daily at 6:30 PM IST
2️⃣ Technical analysis runs on all stocks
3️⃣ Morning report sent at 8:30 AM IST with:

<details open><summary>**📊 Report Categories**</summary>

| Emoji | Category |
|:-----:|:---------|
| 🟢 | STRONG BUY / BUY |
| 🟡 | ACCUMULATE |
| 🔵 | WATCH |
| 🟠 | CAUTION |
| 🔴 | AVOID |

</details>

**Pre-market live prices**

• 9:00 AM — Live prices for tracked symbols
• `/search RELIANCE` — instant live quote + indicators

**Scoring factors**

| Factor | Description |
|:-------|:------------|
| RSI | Relative Strength Index |
| ADX | Trend Strength |
| MACD | Momentum |
| SMA/EMA 20/50/100/200 | Moving Averages |
| Relative Volume | Volume vs average |
| OBV | On-Balance Volume |

<details><summary>**ℹ️ Full Indicator Guide**</summary>

Use `/indicators` for detailed explanations of each indicator, scoring rules, and how to read signals together.

</details>

---
⚠️ _Not financial advice. DYOR._"""


__all__ = [
    "generate_indicators_message",
    "generate_welcome_message",
    "generate_help_message",
]