import time
try:
    from mcp.client.streamable_http import streamable_http_client
except ImportError:
    from mcp.client.streamable_http import streamablehttp_client as streamable_http_client
from mcp import ClientSession
import asyncio

MCP_URL = "https://agent.bitget.com/mcp"
import json
from bitget_market import BitgetMarket
from datetime import datetime, timezone

# ==============================
# SENTIXAI CONFIG
# ==============================

SYMBOL = "TSLA"
TEST_PRICE = 350.00

STARTING_BALANCE = 10000.00
RISK_PER_TRADE = 100.00
MAX_POSITION_VALUE = 3000.00

STOP_LOSS_PERCENT = 0.03
TAKE_PROFIT_PERCENT = 0.06
MIN_CONFIDENCE = 70.0

JOURNAL_FILE = "trade_journal.json"
PORTFOLIO_FILE = "portfolio.json"


# ==============================
# UTILITIES
# ==============================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


# ==============================
# 1. MARKET DATA
# ==============================

def get_market_data(symbol):
    """
    Fetch complete U.S. equity market data directly from Bitget.

    Includes:
    - Live ticker
    - Historical OHLCV candles
    - US market session state
    - Company overview
    - Valuation indicators
    - Earnings forecast

    No API key required.
    """

    client = BitgetMarket()

    symbol = symbol.upper().replace(".US", "").replace("/", "")
    bitget_symbol = client.reality_symbol(symbol)

    # --------------------------------------------------
    # Live quote
    # --------------------------------------------------

    try:
        quote = client.quote(symbol)
    except Exception as e:
        print(f"{symbol}: Bitget quote error - {type(e).__name__}: {e}")
        return {
            "symbol": symbol,
            "bitget_symbol": bitget_symbol,
            "price": 0.0,
            "prev_close": 0.0,
            "volume": 0.0,
            "change_percent": 0.0,
            "change_24h": 0.0,
            "momentum": 0.0,
            "sentiment": 50.0,
            "trend_5d": 0.0,
            "trend_10d": 0.0,
            "trend_20d": 0.0,
            "sma_20": 0.0,
            "rsi_14": 50.0,
            "volatility_20d": 0.0,
            "price_vs_sma20": 0.0,
            "historical": [],
            "market_state": {},
            "fundamentals": {
                "company": {},
                "valuation": {},
                "earnings": {},
            },
            "source": "Bitget",
            "data_provider": "Bitget Reality US Stocks",
            "error": str(e),
        }

    price = float(quote.get("price", 0.0))
    prev_close = float(quote.get("open_24h", 0.0))
    volume = float(quote.get("volume_24h", 0.0))
    change_percent = float(quote.get("change_24h", 0.0))

    # --------------------------------------------------
    # Historical daily candles
    # --------------------------------------------------

    try:
        candle_response = client.candles(
            symbol,
            interval="1D",
            limit=100
        )
        raw_candles = candle_response.get("data", [])
    except Exception as e:
        print(
            f"{symbol}: Bitget historical data error - "
            f"{type(e).__name__}: {e}"
        )
        raw_candles = []

    candles = []

    for row in raw_candles:
        try:
            if len(row) < 5:
                continue

            candles.append({
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]) if len(row) > 5 else 0.0,
                "turnover": float(row[6]) if len(row) > 6 else 0.0,
            })
        except (TypeError, ValueError, IndexError):
            continue

    candles.sort(key=lambda x: x["timestamp"])

    closes = [x["close"] for x in candles if x["close"] > 0]

    # --------------------------------------------------
    # Momentum and historical trends
    # --------------------------------------------------

    momentum = change_percent

    def trend_return(days):
        if len(closes) <= days:
            return 0.0

        old_price = closes[-(days + 1)]
        new_price = closes[-1]

        if old_price <= 0:
            return 0.0

        return ((new_price - old_price) / old_price) * 100

    trend_5d = trend_return(5)
    trend_10d = trend_return(10)
    trend_20d = trend_return(20)

    # --------------------------------------------------
    # SMA 20
    # --------------------------------------------------

    sma_20 = 0.0

    if len(closes) >= 20:
        sma_20 = sum(closes[-20:]) / 20

    # --------------------------------------------------
    # RSI 14
    # --------------------------------------------------

    rsi_14 = 50.0

    if len(closes) >= 15:
        gains = []
        losses = []

        for i in range(len(closes) - 14, len(closes)):
            change = closes[i] - closes[i - 1]

            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))

        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14

        if avg_loss == 0:
            rsi_14 = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_14 = 100 - (100 / (1 + rs))

    # --------------------------------------------------
    # Annualized 20-day volatility
    # --------------------------------------------------

    volatility_20d = 0.0

    if len(closes) >= 21:
        returns = []

        for i in range(len(closes) - 20, len(closes)):
            previous = closes[i - 1]

            if previous > 0:
                returns.append(
                    (closes[i] - previous) / previous
                )

        if returns:
            mean_return = sum(returns) / len(returns)

            variance = sum(
                (r - mean_return) ** 2
                for r in returns
            ) / len(returns)

            volatility_20d = (
                variance ** 0.5
            ) * (252 ** 0.5) * 100

    # --------------------------------------------------
    # Price relative to SMA20
    # --------------------------------------------------

    price_vs_sma20 = 0.0

    if sma_20 > 0:
        price_vs_sma20 = (
            (price - sma_20) / sma_20
        ) * 100

    # --------------------------------------------------
    # Market session
    # --------------------------------------------------

    try:
        market_state = client.market_state()
    except Exception:
        market_state = {}

    # --------------------------------------------------
    # Bitget Reality fundamentals
    # --------------------------------------------------

    try:
        company_overview = client.company_overview(symbol)
    except Exception as e:
        print(
            f"{symbol}: Bitget company overview unavailable - "
            f"{type(e).__name__}: {e}"
        )
        company_overview = {}

    try:
        valuation = client.valuation_indicators(symbol)
    except Exception as e:
        print(
            f"{symbol}: Bitget valuation unavailable - "
            f"{type(e).__name__}: {e}"
        )
        valuation = {}

    try:
        earnings = client.earnings_forecast(symbol)
    except Exception as e:
        print(
            f"{symbol}: Bitget earnings forecast unavailable - "
            f"{type(e).__name__}: {e}"
        )
        earnings = {}

    # --------------------------------------------------
    # Complete Bitget market dataset
    # --------------------------------------------------

    return {
        "symbol": symbol,
        "bitget_symbol": bitget_symbol,

        "price": price,
        "prev_close": prev_close,
        "volume": volume,
        "change_percent": change_percent,
        "change_24h": change_percent,
        "momentum": momentum,

        # Sentiment remains neutral until a verified
        # Bitget sentiment/news source is connected.
        "sentiment": 50.0,

        "trend_5d": trend_5d,
        "trend_10d": trend_10d,
        "trend_20d": trend_20d,

        "sma_20": sma_20,
        "rsi_14": rsi_14,
        "volatility_20d": volatility_20d,
        "price_vs_sma20": price_vs_sma20,

        "historical": candles,
        "market_state": market_state,

        "fundamentals": {
            "company": company_overview,
            "valuation": valuation,
            "earnings": earnings,
        },

        "source": "Bitget",
        "data_provider": "Bitget Reality US Stocks",
    }




def score_fundamentals(data):
    """
    Score Bitget Reality company fundamentals.

    Returns:
        score: 0-100
        reasons: human-readable fundamental signals
    """

    fundamentals = data.get("fundamentals", {})
    company = fundamentals.get("company", {})
    valuation = fundamentals.get("valuation", {})
    earnings = fundamentals.get("earnings", {})

    score = 50.0
    reasons = []

    def number(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    pe = number(company.get("peRatio"))
    pb = number(company.get("pbRatio"))
    ev_ebitda = number(valuation.get("evEbitda"))
    eps = number(earnings.get("eps"))
    revenue = number(earnings.get("revenue"))

    # P/E valuation
    if pe is not None:
        if pe <= 20:
            score += 10
            reasons.append(f"Attractive P/E valuation ({pe:.2f})")
        elif pe <= 30:
            score += 6
            reasons.append(f"Reasonable P/E valuation ({pe:.2f})")
        elif pe <= 50:
            score += 1
            reasons.append(f"Moderate P/E valuation ({pe:.2f})")
        elif pe <= 100:
            score -= 7
            reasons.append(f"High P/E valuation ({pe:.2f})")
        else:
            score -= 15
            reasons.append(f"Very high P/E valuation ({pe:.2f})")

    # P/B valuation
    if pb is not None:
        if pb <= 5:
            score += 7
            reasons.append(f"Attractive P/B ({pb:.2f})")
        elif pb <= 10:
            score += 4
        elif pb <= 25:
            score += 0
        elif pb <= 50:
            score -= 4
            reasons.append(f"Elevated P/B ({pb:.2f})")
        else:
            score -= 7
            reasons.append(f"Very high P/B ({pb:.2f})")

    # EV / EBITDA
    if ev_ebitda is not None:
        if ev_ebitda <= 15:
            score += 7
            reasons.append(f"Attractive EV/EBITDA ({ev_ebitda:.2f})")
        elif ev_ebitda <= 25:
            score += 4
        elif ev_ebitda <= 40:
            score += 0
        elif ev_ebitda <= 80:
            score -= 4
            reasons.append(f"Elevated EV/EBITDA ({ev_ebitda:.2f})")
        else:
            score -= 7
            reasons.append(f"High EV/EBITDA ({ev_ebitda:.2f})")

    # Forecast EPS availability
    if eps is not None and eps > 0:
        score += 3
        reasons.append(f"Positive forecast EPS ({eps:.2f})")

    # Forecast revenue availability
    if revenue is not None and revenue > 0:
        score += 2
        reasons.append("Positive forward revenue estimate")

    score = max(0.0, min(100.0, score))

    return {
        "score": score,
        "reasons": reasons,
    }


def analyze_market(data):
    """
    SentixAI multi-factor AI stock analysis.

    Technical analysis provides 60% of the confidence.
    Bitget Reality fundamentals provide 40%.
    """

    price = float(data.get("price", 0.0))
    momentum = float(data.get("momentum", 0.0))
    sentiment = float(data.get("sentiment", 50.0))
    volume = float(data.get("volume", 0.0))
    trend_5d = float(data.get("trend_5d", 0.0))
    trend_10d = float(data.get("trend_10d", 0.0))
    trend_20d = float(data.get("trend_20d", 0.0))
    rsi = float(data.get("rsi_14", 50.0))
    price_vs_sma20 = float(data.get("price_vs_sma20", 0.0))
    volatility = float(data.get("volatility_20d", 0.0))

    technical_score = 50.0
    technical_reasons = []

    # Momentum
    if momentum >= 4:
        technical_score += 15
        technical_reasons.append("Strong positive momentum")
    elif momentum >= 2:
        technical_score += 10
        technical_reasons.append("Positive momentum")
    elif momentum > 0:
        technical_score += 5
        technical_reasons.append("Mild positive momentum")
    elif momentum <= -4:
        technical_score -= 15
        technical_reasons.append("Strong negative momentum")
    elif momentum <= -2:
        technical_score -= 10
        technical_reasons.append("Negative momentum")
    else:
        technical_score -= 3
        technical_reasons.append("Weak momentum")

    # Market sentiment
    if sentiment >= 70:
        technical_score += 12
        technical_reasons.append("Bullish market sentiment")
    elif sentiment >= 55:
        technical_score += 6
        technical_reasons.append("Positive market sentiment")
    elif sentiment < 30:
        technical_score -= 12
        technical_reasons.append("Bearish market sentiment")
    elif sentiment < 45:
        technical_score -= 5
        technical_reasons.append("Weak market sentiment")
    else:
        technical_reasons.append("Neutral market sentiment")

    # Volume
    if volume >= 25_000_000:
        technical_score += 8
        technical_reasons.append("Strong trading volume")
    elif volume >= 15_000_000:
        technical_score += 5
        technical_reasons.append("Healthy trading volume")
    elif volume >= 8_000_000:
        technical_score += 2
    elif volume > 0:
        technical_score -= 2
        technical_reasons.append("Weak trading volume")

    # Historical trends
    positive_trends = 0
    negative_trends = 0

    for value, threshold, label in [
        (trend_5d, 3, "5-day"),
        (trend_10d, 5, "10-day"),
        (trend_20d, 8, "20-day"),
    ]:
        if value >= threshold:
            technical_score += 4
            positive_trends += 1
        elif value <= -threshold:
            technical_score -= 4
            negative_trends += 1

    if positive_trends >= 2:
        technical_reasons.append("Positive historical trend")
    elif negative_trends >= 2:
        technical_reasons.append("Negative historical trend")
    else:
        technical_reasons.append("Mixed historical trend")

    # RSI
    if 50 <= rsi < 65:
        technical_score += 6
        technical_reasons.append("Healthy RSI momentum")
    elif 65 <= rsi < 70:
        technical_score += 3
        technical_reasons.append("Strong RSI momentum")
    elif rsi >= 70:
        technical_score -= 3
        technical_reasons.append("RSI approaching overbought territory")
    elif 35 <= rsi < 50:
        technical_score -= 2
        technical_reasons.append("Weak RSI momentum")
    elif rsi <= 35:
        technical_score += 2
        technical_reasons.append("Potential RSI recovery zone")

    # Price vs SMA20
    if price_vs_sma20 >= 5:
        technical_score += 6
        technical_reasons.append("Price strongly above 20-day SMA")
    elif price_vs_sma20 > 0:
        technical_score += 3
        technical_reasons.append("Price above 20-day SMA")
    elif price_vs_sma20 <= -5:
        technical_score -= 6
        technical_reasons.append("Price below 20-day SMA")
    else:
        technical_score -= 3

    # Volatility
    if volatility >= 60:
        technical_score -= 5
        technical_reasons.append("High price volatility")
    elif volatility >= 40:
        technical_score -= 2
        technical_reasons.append("Elevated price volatility")
    elif 0 < volatility < 20:
        technical_score += 2
        technical_reasons.append("Stable price volatility")

    # Signal confluence
    # Rewards agreement between independent indicators
    # and penalizes conflicting technical signals.

    bullish_alignment = 0
    bearish_alignment = 0

    if trend_5d > 0:
        bullish_alignment += 1
    elif trend_5d < 0:
        bearish_alignment += 1

    if trend_10d > 0:
        bullish_alignment += 1
    elif trend_10d < 0:
        bearish_alignment += 1

    if trend_20d > 0:
        bullish_alignment += 1
    elif trend_20d < 0:
        bearish_alignment += 1

    # Trend alignment
    if bullish_alignment == 3:
        technical_score += 6
        technical_reasons.append("Strong multi-period trend alignment")
    elif bullish_alignment == 2 and bearish_alignment == 0:
        technical_score += 3
        technical_reasons.append("Positive multi-period trend alignment")
    elif bearish_alignment == 3:
        technical_score -= 6
        technical_reasons.append("Strong multi-period bearish alignment")
    elif bearish_alignment == 2 and bullish_alignment == 0:
        technical_score -= 3
        technical_reasons.append("Negative multi-period trend alignment")

    # Momentum + trend confirmation
    if momentum > 0 and bullish_alignment >= 2:
        technical_score += 3
        technical_reasons.append("Momentum confirms the broader trend")
    elif momentum < 0 and bearish_alignment >= 2:
        technical_score -= 3
        technical_reasons.append("Momentum confirms the bearish trend")
    elif momentum > 0 and bearish_alignment >= 2:
        technical_score -= 2
        technical_reasons.append("Momentum conflicts with the broader trend")
    elif momentum < 0 and bullish_alignment >= 2:
        technical_score -= 2
        technical_reasons.append("Momentum conflicts with the bullish trend")

    # RSI + price structure confirmation
    if price_vs_sma20 > 0 and 45 <= rsi < 65:
        technical_score += 3
        technical_reasons.append("RSI and price structure are supportive")
    elif price_vs_sma20 < 0 and rsi < 45:
        technical_score -= 3
        technical_reasons.append("RSI and price structure are weak")

    technical_score = max(0.0, min(100.0, technical_score))

    # Fundamental score
    fundamental = score_fundamentals(data)
    fundamental_score = fundamental["score"]

    # Final confidence
    final_score = (
        technical_score * 0.60
        + fundamental_score * 0.40
    )

    # Live Bitget market adjustment.
    # This keeps confidence responsive to the current market move
    # without allowing short-term price noise to dominate the model.
    live_change = float(data.get("change_24h", 0.0) or 0.0)

    if live_change >= 5:
        live_adjustment = 4.0
    elif live_change >= 2:
        live_adjustment = 2.5
    elif live_change >= 0.5:
        live_adjustment = 1.0
    elif live_change <= -5:
        live_adjustment = -4.0
    elif live_change <= -2:
        live_adjustment = -2.5
    elif live_change <= -0.5:
        live_adjustment = -1.0
    else:
        live_adjustment = 0.0

    final_score += live_adjustment

    final_score = max(0.0, min(100.0, final_score))

    if final_score >= float(MIN_CONFIDENCE):
        decision = "BUY"
    elif final_score <= 30:
        decision = "SELL"
    else:
        decision = "HOLD"

    reasons = [
        f"Technical score: {technical_score:.1f}/100",
        f"Fundamental score: {fundamental_score:.1f}/100",
    ]

    reasons.extend(technical_reasons)
    reasons.extend(fundamental["reasons"])

    return {
        "symbol": data.get("symbol", "UNKNOWN"),
        "price": price,
        "decision": decision,
        "confidence": round(final_score, 2),
        "technical_score": round(technical_score, 2),
        "fundamental_score": round(fundamental_score, 2),
        "reasons": reasons,
    }



def generate_ai_thesis(data, analysis, ranking=None):
    """
    Generate a human-readable AI investment thesis
    from Bitget market data and SentixAI analysis.
    """

    symbol = data.get("symbol", "UNKNOWN")
    price = float(data.get("price", 0.0))
    decision = analysis.get("decision", "HOLD")
    confidence = float(analysis.get("confidence", 0.0))
    technical = float(analysis.get("technical_score", 0.0))
    fundamental = float(analysis.get("fundamental_score", 0.0))

    fundamentals = data.get("fundamentals", {})
    company = fundamentals.get("company", {})
    valuation = fundamentals.get("valuation", {})
    earnings = fundamentals.get("earnings", {})

    name = company.get("name", symbol)

    def number(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    pe = number(company.get("peRatio"))
    pb = number(company.get("pbRatio"))
    eps = number(earnings.get("eps"))
    revenue = number(earnings.get("revenue"))
    rsi = number(data.get("rsi_14"))
    sma20 = number(data.get("sma_20"))
    change = number(data.get("change_percent"))
    momentum = number(data.get("momentum"))
    trend_5d = number(data.get("trend_5d"))
    trend_10d = number(data.get("trend_10d"))
    trend_20d = number(data.get("trend_20d"))
    price_vs_sma20 = number(data.get("price_vs_sma20"))

    thesis = []

    # Signal strength and confidence gap
    buy_threshold = float(MIN_CONFIDENCE)
    confidence_gap = max(0.0, buy_threshold - confidence)

    if confidence >= 80:
        signal_strength = "Very Strong"
    elif confidence >= 70:
        signal_strength = "Strong"
    elif confidence >= 60:
        signal_strength = "Moderate"
    elif confidence >= 45:
        signal_strength = "Weak"
    else:
        signal_strength = "Very Weak"

    # Overall assessment
    if decision == "BUY":
        thesis.append(
            f"{name} currently qualifies as a BUY candidate with "
            f"{confidence:.1f}% confidence."
        )
    elif decision == "SELL":
        thesis.append(
            f"{name} currently shows a SELL setup with "
            f"{confidence:.1f}% confidence."
        )
    else:
        thesis.append(
            f"{name} currently remains a HOLD because its "
            f"{confidence:.1f}% confidence is below the "
            f"{float(MIN_CONFIDENCE):.1f}% BUY threshold."
        )

    # Technical case
    technical_points = []

    if technical >= 70:
        technical_points.append("strong technical structure")
    elif technical >= 60:
        technical_points.append("positive technical structure")
    elif technical >= 50:
        technical_points.append("mixed-to-positive technical structure")
    else:
        technical_points.append("weak technical structure")

    if rsi is not None:
        if 50 <= rsi < 65:
            technical_points.append(f"healthy RSI at {rsi:.1f}")
        elif 65 <= rsi < 70:
            technical_points.append(f"strong RSI at {rsi:.1f}")
        elif rsi >= 70:
            technical_points.append(f"overbought RSI risk at {rsi:.1f}")
        elif rsi < 40:
            technical_points.append(f"weak RSI at {rsi:.1f}")

    if sma20 and price:
        if price > sma20:
            technical_points.append("price is above the 20-day SMA")
        else:
            technical_points.append("price is below the 20-day SMA")

    thesis.append(
        "Technical case: " + ", ".join(technical_points) + "."
    )

    # Trend confirmation
    trend_points = []

    if momentum is not None:
        trend_points.append(f"24H momentum at {momentum:+.2f}%")

    trend_values = [
        value for value in (trend_5d, trend_10d, trend_20d)
        if value is not None
    ]

    if trend_values:
        bullish_trends = sum(1 for value in trend_values if value > 0)
        bearish_trends = sum(1 for value in trend_values if value < 0)

        trend_labels = [
            ("5D", trend_5d),
            ("10D", trend_10d),
            ("20D", trend_20d),
        ]

        trend_points.extend(
            f"{label} {value:+.2f}%"
            for label, value in trend_labels
            if value is not None
        )

        if bullish_trends == len(trend_values):
            trend_points.append("all tracked trends are bullish")
        elif bearish_trends == len(trend_values):
            trend_points.append("all tracked trends are bearish")
        elif bullish_trends > bearish_trends:
            trend_points.append("trend structure leans bullish")
        elif bearish_trends > bullish_trends:
            trend_points.append("trend structure leans bearish")
        else:
            trend_points.append("multi-period trends are mixed")

    if price_vs_sma20 is not None:
        trend_points.append(
            f"price is {price_vs_sma20:+.2f}% vs the 20-day SMA"
        )

    if trend_points:
        thesis.append(
            "Trend confirmation: " + ", ".join(trend_points) + "."
        )

    # Fundamental case
    fundamental_points = []

    if fundamental >= 70:
        fundamental_points.append("strong fundamental profile")
    elif fundamental >= 60:
        fundamental_points.append("healthy fundamental profile")
    elif fundamental >= 50:
        fundamental_points.append("mixed fundamental profile")
    else:
        fundamental_points.append("weak fundamental profile")

    if pe is not None:
        if pe <= 20:
            fundamental_points.append(f"P/E of {pe:.2f} is relatively attractive")
        elif pe <= 40:
            fundamental_points.append(f"P/E of {pe:.2f} is moderate")
        else:
            fundamental_points.append(f"P/E of {pe:.2f} is elevated")

    if pb is not None:
        if pb <= 5:
            fundamental_points.append(f"P/B of {pb:.2f} is attractive")
        elif pb > 25:
            fundamental_points.append(f"P/B of {pb:.2f} is elevated")

    if eps is not None and eps > 0:
        fundamental_points.append(f"positive forecast EPS of {eps:.2f}")

    if revenue is not None and revenue > 0:
        fundamental_points.append("positive forward revenue estimate")

    thesis.append(
        "Fundamental case: " + ", ".join(fundamental_points) + "."
    )

    # Risks
    risks = []

    if rsi is not None and rsi >= 65:
        risks.append("momentum may be getting stretched")

    if pe is not None and pe > 50:
        risks.append("high earnings multiple")

    if pb is not None and pb > 25:
        risks.append("elevated price-to-book valuation")

    if technical < 60:
        risks.append("technical score is below the bullish zone")

    if fundamental < 50:
        risks.append("fundamental score is weak")

    if change is not None and abs(change) > 5:
        risks.append("large short-term price movement")

    if not risks:
        risks.append("no major valuation or technical warning detected")

    thesis.append("Key risks: " + "; ".join(risks) + ".")

    # Ranking context
    if ranking:
        rank = next(
            (
                i + 1
                for i, item in enumerate(ranking)
                if item.get("symbol") == symbol
            ),
            None,
        )

        if rank is not None:
            thesis.append(
                f"Ranking context: {symbol} is currently "
                f"#{rank} in the Bitget stock opportunity scan."
            )

    # Confidence intelligence
    if decision == "BUY":
        thesis.append(
            f"Signal strength: {signal_strength}. "
            f"Confidence is {confidence:.1f}%, above the {buy_threshold:.1f}% BUY threshold."
        )
    elif decision == "SELL":
        thesis.append(
            f"Signal strength: {signal_strength}. "
            f"Confidence is {confidence:.1f}% with a bearish decision."
        )
    else:
        thesis.append(
            f"Signal strength: {signal_strength}. "
            f"Confidence gap to BUY: {confidence_gap:.1f} points."
        )

    # Final action
    if decision == "BUY":
        action = (
            "AI ACTION: BUY candidate. Risk engine must approve "
            "the position before execution."
        )
    elif decision == "SELL":
        action = (
            "AI ACTION: SELL signal. Further risk validation "
            "is required before execution."
        )
    else:
        action = (
            f"AI ACTION: HOLD. Wait for stronger confirmation "
            f"before considering a BUY above {float(MIN_CONFIDENCE):.0f}% confidence."
        )

    return {
        "symbol": symbol,
        "decision": decision,
        "confidence": round(confidence, 2),
        "buy_threshold": round(buy_threshold, 2),
        "confidence_gap": round(confidence_gap, 2),
        "signal_strength": signal_strength,
        "thesis": thesis,
        "risks": risks,
        "action": action,
    }


def scan_stock_universe(symbols=None):
    """
    Scan the SentixAI U.S. stock universe using
    live Bitget market data.

    Stocks are analyzed concurrently so the dashboard
    does not wait for each Bitget request sequentially.
    """

    from concurrent.futures import ThreadPoolExecutor, as_completed

    if symbols is None:
        symbols = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN"]

    def analyze_symbol(symbol):
        try:
            market_data = get_market_data(symbol)
            analysis = analyze_market(market_data)

            confidence = float(analysis.get("confidence", 0.0))
            technical = float(analysis.get("technical_score", 0.0))
            fundamental = float(analysis.get("fundamental_score", 0.0))

            technical_quality = technical - 50.0
            fundamental_quality = fundamental - 50.0

            opportunity_score = (
                confidence
                + (technical_quality * 0.10)
                + (fundamental_quality * 0.10)
            )

            opportunity_score = max(
                0.0,
                min(100.0, opportunity_score)
            )

            return {
                "symbol": symbol,
                "price": analysis["price"],
                "decision": analysis["decision"],
                "confidence": confidence,
                "technical_score": technical,
                "fundamental_score": fundamental,
                "opportunity_score": round(opportunity_score, 2),
                "reasons": analysis["reasons"],
            }

        except Exception as e:
            print(
                f"{symbol}: scanner error - "
                f"{type(e).__name__}: {e}"
            )
            return None

    results = []

    max_workers = min(len(symbols), 2)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(analyze_symbol, symbol): symbol
            for symbol in symbols
        }

        for future in as_completed(futures):
            result = future.result()

            if result is not None:
                results.append(result)

    results.sort(
        key=lambda x: x["opportunity_score"],
        reverse=True
    )

    for rank, result in enumerate(results, start=1):
        result["rank"] = rank

    return results

def display_opportunity_ranking(results):
    """
    Display the strongest SentixAI opportunities.
    """

    print("\n" + "=" * 72)
    print("SENTIXAI — OPPORTUNITY RANKING")
    print("=" * 72)

    for rank, item in enumerate(results, start=1):
        print(
            f"{rank}. "
            f"{item['symbol']:5} | "
            f"${item['price']:>8.2f} | "
            f"{item['decision']:<4} | "
            f"{item['confidence']:>5.1f}%"
        )

    print("-" * 72)

    if results:
        best = results[0]

        print(
            f"TOP CANDIDATE: {best['symbol']} "
            f"({best['confidence']:.1f}%)"
        )

        if best["decision"] == "BUY":
            print("ACTION: BUY candidate meets confidence threshold.")
        else:
            gap = max(0.0, MIN_CONFIDENCE - best["confidence"])

            print(
                "ACTION: NO BUY — strongest candidate "
                "does not meet confidence threshold."
            )
            print(
                f"CONFIDENCE GAP: {gap:.1f} percentage points "
                f"below BUY threshold ({MIN_CONFIDENCE:.1f}%)."
            )

        print("\nTop candidate signals:")

        for reason in best["reasons"]:
            print(f" • {reason}")

    print("=" * 72)

def run_pipeline(symbol='TSLA'):
    print("\n" + "=" * 72)
    print("SENTIXAI AUTONOMOUS US STOCK PIPELINE")
    print("=" * 72)

    print("\n[1] BITGET MARKET SCAN")
    print("Scanning: TSLA, NVDA, AAPL, MSFT, AMZN")

    results = scan_stock_universe()

    if not results:
        print("ERROR: No market data returned from Bitget.")
        return

    display_opportunity_ranking(results)

    best = results[0]
    selected_symbol = best["symbol"]

    print("\n[2] SELECTED CANDIDATE")
    print(f"Symbol     : {selected_symbol}")
    print(f"Price      : ${best['price']:.2f}")
    print(f"Decision   : {best['decision']}")
    print(f"Confidence : {best['confidence']:.2f}%")
    print(f"Technical  : {best.get('technical_score', 0):.2f}/100")
    print(f"Fundamental: {best.get('fundamental_score', 0):.2f}/100")

    data = get_market_data(selected_symbol)

    print("\n[3] BITGET MARKET DATA")
    print(f"Symbol     : {data.get('symbol', selected_symbol)}")
    print(f"Bitget     : {data.get('bitget_symbol', 'N/A')}")
    print(f"Price      : ${data.get('price', 0):.2f}")
    print(f"Source     : {data.get('source', 'UNKNOWN')}")

    analysis = analyze_market(data)

    print("\n[4] AI DECISION")
    print(f"Decision   : {analysis['decision']}")
    print(f"Confidence : {analysis['confidence']:.2f}%")
    print(f"Technical  : {analysis.get('technical_score', 0):.2f}/100")
    print(f"Fundamental: {analysis.get('fundamental_score', 0):.2f}/100")

    thesis = generate_ai_thesis(
        data,
        analysis,
        ranking=results
    )

    print("\n[5] AI INVESTMENT THESIS")
    for line in thesis["thesis"]:
        print(f"• {line}")

    print(f"\n{thesis['action']}")

    display_ai_analyst_report(
        data,
        analysis,
        ranking=results
    )

    risk = risk_check(data, analysis)

    print("\n[6] RISK ENGINE")
    print(
        f"Open Positions : "
        f"{risk.get('open_positions', 0)}/{risk.get('max_positions', 5)}"
    )
    print(f"Exposure       : ${risk.get('current_exposure', 0):,.2f}")
    print(f"Exposure %     : {risk.get('exposure_percent', 0):.2f}%")
    print(f"Max Exposure   : ${risk.get('max_exposure', 0):,.2f}")
    print(f"Remaining      : ${risk.get('remaining_exposure', 0):,.2f}")
    print(f"Available Cash : ${risk.get('available_capital', 0):,.2f}")

    if risk["approved"]:
        print("Status         : APPROVED")
        print(f"Position       : ${risk['position_value']:,.2f}")
        print(f"Quantity       : {risk['quantity']:.6f}")
        print(f"Stop Loss      : ${risk['stop_loss']:.2f}")
        print(f"Take Profit    : ${risk['take_profit']:.2f}")
        print(f"Risk Amount    : ${risk['risk_amount']:.2f}")
    else:
        print("Status         : NOT APPROVED")
        print(
            f"Reason         : "
            f"{risk.get('reason', 'Risk check failed')}"
        )

    print("\n[7] PORTFOLIO")
    display_portfolio()

    print("\n" + "=" * 72)
    print("SENTIXAI PIPELINE COMPLETE")
    print("=" * 72)

def risk_check(data, analysis):
    """
    SentixAI portfolio-aware risk engine.
    Uses portfolio capital and the current AI decision.
    """

    portfolio = load_portfolio()

    starting_balance = float(
        portfolio.get("starting_balance", 10000.0)
    )
    realized_pnl = float(
        portfolio.get("realized_pnl", 0.0)
    )
    current_balance = float(
        portfolio.get(
            "current_balance",
            starting_balance + realized_pnl
        )
    )

    max_position = 3000.0
    max_portfolio_exposure = current_balance * 0.60
    max_positions = 5
    max_risk_per_trade = 100.0

    current_exposure = 0.0
    open_positions = 0

    exposure_percent = (
        current_exposure / current_balance * 100
        if current_balance > 0 else 0.0
    )

    remaining_exposure = max(
        0.0,
        max_portfolio_exposure - current_exposure
    )

    available_capital = max(
        0.0,
        current_balance - current_exposure
    )

    price = float(data.get("price", 0.0))
    decision = analysis.get("decision", "HOLD")
    confidence = float(
        analysis.get("confidence", 0.0)
    )

    base = {
        "approved": False,
        "open_positions": open_positions,
        "max_positions": max_positions,
        "current_exposure": current_exposure,
        "exposure_percent": exposure_percent,
        "max_exposure": max_portfolio_exposure,
        "remaining_exposure": remaining_exposure,
        "available_capital": available_capital,
    }

    if decision != "BUY":
        base["reason"] = "No BUY signal"
        return base

    if confidence < MIN_CONFIDENCE:
        base["reason"] = (
            f"Confidence {confidence:.2f}% is below "
            f"BUY threshold {MIN_CONFIDENCE:.2f}%"
        )
        return base

    if price <= 0:
        base["reason"] = "Invalid market price"
        return base

    if open_positions >= max_positions:
        base["reason"] = "Maximum open positions reached"
        return base

    if remaining_exposure <= 0:
        base["reason"] = "Maximum portfolio exposure reached"
        return base

    stop_loss = price * 0.97
    take_profit = price * 1.06

    risk_per_share = price - stop_loss

    if risk_per_share <= 0:
        base["reason"] = "Invalid stop-loss calculation"
        return base

    risk_based_position = (
        max_risk_per_trade / 0.03
    )

    position_value = min(
        max_position,
        remaining_exposure,
        available_capital,
        risk_based_position
    )

    if position_value <= 0:
        base["reason"] = "No capital available"
        return base

    quantity = position_value / price
    risk_amount = risk_per_share * quantity

    if risk_amount > max_risk_per_trade + 0.01:
        base["reason"] = (
            f"Calculated risk ${risk_amount:.2f} "
            f"exceeds ${max_risk_per_trade:.2f} limit"
        )
        return base

    base.update({
        "approved": True,
        "position_value": position_value,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_amount": risk_amount,
        "reason": "Risk checks passed",
    })

    return base


def load_portfolio():
    """Load SentixAI portfolio state from portfolio.json."""
    import json
    import os

    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "portfolio.json"
    )

    default = {
        "starting_balance": 10000.0,
        "realized_pnl": 0.0,
        "current_balance": 10000.0,
        "wins": 0,
        "losses": 0,
        "total_trades": 0,
    }

    try:
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump(default, f, indent=4)
            return default

        with open(path, "r") as f:
            data = json.load(f)

        for key, value in default.items():
            data.setdefault(key, value)

        return data

    except Exception:
        return default


def display_portfolio():
    """Display current SentixAI portfolio statistics."""
    portfolio = load_portfolio()

    starting = float(
        portfolio.get("starting_balance", 10000.0)
    )
    realized = float(
        portfolio.get("realized_pnl", 0.0)
    )
    current = float(
        portfolio.get("current_balance", starting + realized)
    )

    wins = int(portfolio.get("wins", 0))
    losses = int(portfolio.get("losses", 0))
    total = int(
        portfolio.get("total_trades", wins + losses)
    )

    win_rate = (
        wins / total * 100
        if total > 0 else 0.0
    )

    print(f"Starting Balance : ${starting:,.2f}")
    print(f"Realized PnL    : ${realized:,.2f}")
    print(f"Current Balance : ${current:,.2f}")
    print(f"Wins            : {wins}")
    print(f"Losses          : {losses}")
    print(f"Total Trades    : {total}")
    print(f"Win Rate        : {win_rate:.2f}%")


def display_ai_analyst_report(data, analysis, ranking=None):
    """Display a clean, judge-friendly SentixAI analyst report."""

    symbol = analysis.get("symbol", data.get("symbol", "UNKNOWN"))
    price = float(analysis.get("price", data.get("price", 0.0)))
    decision = analysis.get("decision", "HOLD")
    confidence = float(analysis.get("confidence", 0.0))
    technical = float(analysis.get("technical_score", 0.0))
    fundamental = float(analysis.get("fundamental_score", 0.0))

    print("\n" + "=" * 72)
    print("SENTIXAI AI ANALYST")
    print("=" * 72)

    print(f"{symbol}")
    print(f"${price:.2f}")
    print()
    print(f"SIGNAL        {decision}")
    print(f"CONFIDENCE    {confidence:.1f}%")
    print(f"TECHNICAL     {technical:.1f}/100")
    print(f"FUNDAMENTAL   {fundamental:.1f}/100")

    print("\nWHY?")

    reasons = analysis.get("reasons", [])

    positive_keywords = (
        "positive",
        "reasonable",
        "attractive",
        "healthy",
        "stable",
        "above",
        "moderate",
        "strong",
    )

    risk_keywords = (
        "weak",
        "mixed",
        "high",
        "elevated",
        "volatile",
        "negative",
        "below",
    )

    shown_positive = 0
    shown_risk = 0

    for reason in reasons:
        text = str(reason)

        if shown_positive < 4 and any(
            word in text.lower()
            for word in positive_keywords
        ):
            print(f"✓ {text}")
            shown_positive += 1

    print("\nRISKS")

    for reason in reasons:
        text = str(reason)

        if shown_risk < 4 and any(
            word in text.lower()
            for word in risk_keywords
        ):
            print(f"⚠ {text}")
            shown_risk += 1

    if shown_positive == 0:
        print("✓ No major positive signal identified.")

    if shown_risk == 0:
        print("⚠ No major risk signal identified.")

    print("\nBUY TRIGGER")
    print(
        f"Confidence ≥ {MIN_CONFIDENCE:.1f}%"
    )

    if ranking:
        position = next(
            (
                i
                for i, item in enumerate(ranking, start=1)
                if item.get("symbol") == symbol
            ),
            None,
        )

        if position is not None:
            print(
                f"\nRANK\n"
                f"#{position} / {len(ranking)} "
                f"Bitget US stocks"
            )

    print("─" * 72)
    print(
        f"DATA: {data.get('data_provider', 'Bitget Reality US Stocks')}"
    )
    print("=" * 72)



def run_opportunity_monitor(interval_seconds=60):
    """
    SentixAI autonomous Bitget opportunity monitor.

    Continuously scans Bitget US Reality stocks and watches
    for candidates that reach the AI BUY threshold.
    """

    import time

    symbols = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN"]
    previous_decisions = {}

    print("\n" + "=" * 72)
    print("SENTIXAI OPPORTUNITY MONITOR")
    print("=" * 72)
    print("Data source : Bitget Reality US Stocks")
    print(f"Universe    : {', '.join(symbols)}")
    print(f"BUY trigger : {MIN_CONFIDENCE:.1f}%")
    print(f"Scan cycle  : {interval_seconds} seconds")
    print("Press Ctrl+C to stop.")
    print("=" * 72)

    while True:
        try:
            timestamp = time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            print("\n" + "=" * 72)
            print(f"SENTIXAI SCAN — {timestamp}")
            print("=" * 72)

            results = scan_stock_universe(symbols)

            if not results:
                print("STATUS: NO VALID BITGET MARKET DATA")
                print(
                    f"Retrying in {interval_seconds} seconds..."
                )
                time.sleep(interval_seconds)
                continue

            print(
                f"\n{'SYMBOL':<8}"
                f"{'PRICE':>12}"
                f"{'SIGNAL':>10}"
                f"{'CONF.':>10}"
            )
            print("-" * 72)

            for item in results:
                print(
                    f"{item['symbol']:<8}"
                    f"${item['price']:>10.2f}"
                    f"{item['decision']:>10}"
                    f"{item['confidence']:>9.1f}%"
                )

            best = results[0]

            print("\n" + "-" * 72)
            print(
                f"TOP CANDIDATE : {best['symbol']}"
            )
            print(
                f"CONFIDENCE    : {best['confidence']:.1f}%"
            )
            print(
                f"TECHNICAL     : "
                f"{best.get('technical_score', 0):.1f}/100"
            )
            print(
                f"FUNDAMENTAL   : "
                f"{best.get('fundamental_score', 0):.1f}/100"
            )

            gap = max(
                0.0,
                MIN_CONFIDENCE - best["confidence"]
            )

            if best["decision"] == "BUY":
                print("\n🚨 SENTIXAI BUY SIGNAL")
                print(
                    f"{best['symbol']} has crossed "
                    f"the {MIN_CONFIDENCE:.1f}% threshold."
                )

                data = get_market_data(best["symbol"])
                analysis = analyze_market(data)

                risk = risk_check(data, analysis)

                if risk["approved"]:
                    print("\nRISK CHECK: APPROVED")
                    print(
                        f"Entry       : "
                        f"${data['price']:.2f}"
                    )
                    print(
                        f"Position    : "
                        f"${risk['position_value']:.2f}"
                    )
                    print(
                        f"Quantity    : "
                        f"{risk['quantity']:.6f}"
                    )
                    print(
                        f"Stop Loss   : "
                        f"${risk['stop_loss']:.2f}"
                    )
                    print(
                        f"Take Profit : "
                        f"${risk['take_profit']:.2f}"
                    )
                    print(
                        f"Risk        : "
                        f"${risk['risk_amount']:.2f}"
                    )
                else:
                    print("\nRISK CHECK: NOT APPROVED")
                    print(
                        f"Reason      : "
                        f"{risk.get('reason', 'Unknown')}"
                    )

            else:
                print("\nSTATUS: WAITING")
                print(
                    f"{best['symbol']} needs "
                    f"+{gap:.1f}% confidence "
                    f"to reach BUY."
                )

            # Detect signal transitions.
            for item in results:
                symbol = item["symbol"]
                current = item["decision"]
                previous = previous_decisions.get(symbol)

                if previous is not None and current != previous:
                    print(
                        f"\nSIGNAL CHANGE: "
                        f"{symbol} {previous} → {current}"
                    )

                previous_decisions[symbol] = current

            print(
                f"\nNEXT SCAN IN {interval_seconds} SECONDS"
            )

            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\n")
            print("=" * 72)
            print("SENTIXAI OPPORTUNITY MONITOR STOPPED")
            print("=" * 72)
            break

        except Exception as e:
            print(
                f"\nMONITOR ERROR: "
                f"{type(e).__name__}: {e}"
            )
            print(
                f"Retrying in {interval_seconds} seconds..."
            )
            time.sleep(interval_seconds)


def run_signal_intelligence(interval_seconds=60):
    """
    SentixAI Signal Intelligence Monitor.

    Tracks changes between Bitget scans instead of repeatedly
    displaying identical information.
    """

    import time

    symbols = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN"]
    previous = {}

    print("\n" + "=" * 72)
    print("SENTIXAI SIGNAL INTELLIGENCE")
    print("=" * 72)
    print("Data source : Bitget Reality US Stocks")
    print(f"Universe    : {', '.join(symbols)}")
    print(f"BUY trigger : {MIN_CONFIDENCE:.1f}%")
    print(f"Scan cycle  : {interval_seconds} seconds")
    print("Press Ctrl+C to stop.")
    print("=" * 72)

    while True:
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            results = scan_stock_universe(symbols)

            if not results:
                print("\nNO VALID BITGET DATA")
                print(f"Retrying in {interval_seconds} seconds...")
                time.sleep(interval_seconds)
                continue

            print("\n" + "=" * 72)
            print(f"SENTIXAI INTELLIGENCE — {timestamp}")
            print("=" * 72)

            print(
                f"\n{'SYMBOL':<8}"
                f"{'PRICE':>12}"
                f"{'SIGNAL':>10}"
                f"{'CONF.':>10}"
                f"{'CHANGE':>10}"
            )
            print("-" * 72)

            for item in results:
                symbol = item["symbol"]
                confidence = float(item["confidence"])
                old = previous.get(symbol)

                if old is None:
                    change_text = "NEW"
                else:
                    change = confidence - old["confidence"]

                    if change > 0.05:
                        change_text = f"▲ +{change:.1f}"
                    elif change < -0.05:
                        change_text = f"▼ {change:.1f}"
                    else:
                        change_text = "— 0.0"

                print(
                    f"{symbol:<8}"
                    f"${item['price']:>10.2f}"
                    f"{item['decision']:>10}"
                    f"{confidence:>9.1f}%"
                    f"{change_text:>10}"
                )

            best = results[0]
            best_symbol = best["symbol"]
            best_confidence = float(best["confidence"])

            print("\n" + "-" * 72)
            print("MARKET UPDATE")

            changes_found = False

            for item in results:
                symbol = item["symbol"]
                confidence = float(item["confidence"])
                old = previous.get(symbol)

                if old is None:
                    print(
                        f"• {symbol} entered the intelligence monitor."
                    )
                    changes_found = True
                    continue

                change = confidence - old["confidence"]

                if change >= 0.5:
                    print(
                        f"✓ {symbol} confidence improving "
                        f"+{change:.1f}%"
                    )
                    changes_found = True

                elif change <= -0.5:
                    print(
                        f"⚠ {symbol} confidence weakening "
                        f"{change:.1f}%"
                    )
                    changes_found = True

                if (
                    old["decision"] != "BUY"
                    and item["decision"] == "BUY"
                ):
                    print(
                        f"\n🚨 NEW BUY SIGNAL: {symbol}"
                    )
                    print(
                        f"Confidence: {confidence:.1f}%"
                    )
                    print(
                        f"Previous: {old['confidence']:.1f}%"
                    )
                    print(
                        f"Change: +"
                        f"{confidence - old['confidence']:.1f}%"
                    )

                    data = get_market_data(symbol)
                    analysis = analyze_market(data)
                    risk = risk_check(data, analysis)

                    if risk["approved"]:
                        print("Risk: APPROVED")
                        print(
                            f"Entry       : "
                            f"${data['price']:.2f}"
                        )
                        print(
                            f"Stop Loss   : "
                            f"${risk['stop_loss']:.2f}"
                        )
                        print(
                            f"Take Profit : "
                            f"${risk['take_profit']:.2f}"
                        )
                        print(
                            f"Position    : "
                            f"${risk['position_value']:.2f}"
                        )
                    else:
                        print("Risk: NOT APPROVED")
                        print(
                            f"Reason: "
                            f"{risk.get('reason', 'Unknown')}"
                        )

                    changes_found = True

            if not changes_found:
                print(
                    "• No material confidence changes."
                )

            gap = max(
                0.0,
                MIN_CONFIDENCE - best_confidence
            )

            print("\n" + "-" * 72)
            print("TOP OPPORTUNITY")
            print(
                f"Symbol       : {best_symbol}"
            )
            print(
                f"Confidence   : {best_confidence:.1f}%"
            )
            print(
                f"Technical    : "
                f"{best.get('technical_score', 0):.1f}/100"
            )
            print(
                f"Fundamental  : "
                f"{best.get('fundamental_score', 0):.1f}/100"
            )

            if best["decision"] == "BUY":
                print("\n🚨 STATUS: BUY ZONE")
            else:
                print("\nSTATUS: WATCH")

                if gap > 0:
                    print(
                        f"{best_symbol} needs "
                        f"+{gap:.1f}% confidence "
                        f"to reach BUY."
                    )

            previous = {
                item["symbol"]: {
                    "confidence": float(item["confidence"]),
                    "decision": item["decision"],
                    "price": float(item["price"]),
                }
                for item in results
            }

            print(
                f"\nNEXT INTELLIGENCE SCAN "
                f"IN {interval_seconds} SECONDS"
            )

            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\n")
            print("=" * 72)
            print("SENTIXAI SIGNAL INTELLIGENCE STOPPED")
            print("=" * 72)
            break

        except Exception as e:
            print(
                f"\nINTELLIGENCE ERROR: "
                f"{type(e).__name__}: {e}"
            )
            print(
                f"Retrying in {interval_seconds} seconds..."
            )
            time.sleep(interval_seconds)

