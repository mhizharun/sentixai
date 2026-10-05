import os
import json
import time
import threading
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from sentixai import (
    scan_stock_universe,
    get_market_data,
    analyze_market,
    generate_ai_thesis,
)

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))

SYMBOLS = ["AMZN", "NVDA", "MSFT", "AAPL", "TSLA"]

_STOCK_UNIVERSE = []
_STOCK_UNIVERSE_TIME = 0
_STOCK_UNIVERSE_LOCK = threading.Lock()
_STOCK_UNIVERSE_CACHE_SECONDS = 600


def get_stock_universe():
    global _STOCK_UNIVERSE, _STOCK_UNIVERSE_TIME

    now = time.time()

    with _STOCK_UNIVERSE_LOCK:
        if (
            _STOCK_UNIVERSE
            and now - _STOCK_UNIVERSE_TIME < _STOCK_UNIVERSE_CACHE_SECONDS
        ):
            return _STOCK_UNIVERSE

        import urllib.request

        url = "https://api.bitget.com/api/v3/reality/market/stock-info"

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SentixAI/1.0",
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode())

        rows = payload.get("data", [])
        universe = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            symbol = str(row.get("code", "") or "").upper().strip()
            bitget_symbol = str(row.get("symbol", "") or "").strip()

            if not symbol or not bitget_symbol:
                continue

            universe.append({
                "symbol": symbol,
                "name": row.get("name") or symbol,
                "bitget_symbol": bitget_symbol,
                "trading_period": row.get("tradingPeriod", []),
                "weekend_tradable": row.get("weekendTradable"),
            })

        universe.sort(key=lambda item: item["symbol"])

        _STOCK_UNIVERSE = universe
        _STOCK_UNIVERSE_TIME = now

        return _STOCK_UNIVERSE


def search_stock_universe(query="", limit=12):
    query = str(query or "").strip().upper()
    universe = get_stock_universe()

    if not query:
        return universe[:limit]

    exact = []
    starts = []
    contains = []

    for item in universe:
        symbol = item["symbol"]
        name = str(item.get("name", "") or "").upper()

        if symbol == query:
            exact.append(item)
        elif symbol.startswith(query):
            starts.append(item)
        elif query in symbol or query in name:
            contains.append(item)

    return (exact + starts + contains)[:limit]


def is_known_stock(symbol):
    symbol = str(symbol or "").upper().strip()

    if not symbol:
        return False

    return any(
        item["symbol"] == symbol
        for item in get_stock_universe()
    )



def normalize_history(rows):
    result = []

    for row in rows or []:
        try:
            # Bitget candle format:
            # [timestamp, open, high, low, close, ...]
            if isinstance(row, (list, tuple)) and len(row) >= 5:
                result.append({
                    "time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                })

            elif isinstance(row, dict):
                result.append({
                    "time": int(row.get("timestamp", row.get("time", 0))),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", row.get("price", 0))),
                })
        except Exception:
            continue

    result.sort(key=lambda x: x["time"])
    return result


def get_stock(symbol):
    data = get_market_data(symbol)
    analysis = analyze_market(data)
    thesis = generate_ai_thesis(data, analysis)

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

    buy_threshold = (
        float(MIN_CONFIDENCE)
        if "MIN_CONFIDENCE" in globals()
        else 70.0
    )

    return {
        "symbol": symbol,
        "price": data.get("price", 0),
        "change_24h": data.get(
            "change_24h",
            data.get("change_percent", 0)
        ),
        "decision": analysis.get("decision", "HOLD"),
        "confidence": confidence,
        "opportunity_score": round(opportunity_score, 2),
        "buy_threshold": buy_threshold,
        "confidence_gap": max(
            0.0,
            buy_threshold - confidence
        ),
        "signal_strength": thesis.get(
            "signal_strength",
            ""
        ),
        "technical": technical,
        "fundamental": fundamental,
        "rsi": data.get("rsi_14", 0),
        "sma20": data.get("sma_20", 0),
        "momentum": data.get("momentum", 0),
        "trend_5d": data.get("trend_5d", 0),
        "trend_10d": data.get("trend_10d", 0),
        "trend_20d": data.get("trend_20d", 0),
        "volatility": data.get("volatility_20d", 0),
        "price_vs_sma20": data.get("price_vs_sma20", 0),
        "bitget_symbol": data.get("bitget_symbol", ""),
        "market_state": data.get("market_state", {}),
        "historical": normalize_history(
            data.get("historical", [])
        ),
        "thesis": thesis,
        "source": "Bitget Reality US Stocks",
    }


_DASHBOARD_CACHE = {}
_DASHBOARD_CACHE_TIME = {}
_DASHBOARD_CACHE_LOCK = threading.Lock()
_DASHBOARD_CACHE_SECONDS = 20


def get_dashboard_data(symbol="AMZN"):
    symbol = symbol.upper()

    if not is_known_stock(symbol):
        symbol = "AMZN"

    with _DASHBOARD_CACHE_LOCK:
        cached = _DASHBOARD_CACHE.get(symbol)
        cached_at = _DASHBOARD_CACHE_TIME.get(symbol, 0)

        if cached and (time.time() - cached_at) < _DASHBOARD_CACHE_SECONDS:
            return cached

        ranking = scan_stock_universe(SYMBOLS)

        stocks = []
        for item in ranking:
            stocks.append({
                "symbol": item["symbol"],
                "price": item["price"],
                "change_24h": item.get("change_24h", item.get("change_percent", 0)),
                "decision": item["decision"],
                "confidence": item["confidence"],
                "technical": item.get("technical_score", 0),
                "fundamental": item.get("fundamental_score", 0),
                "opportunity": item.get("opportunity_score", 0),
                "rank": item.get("rank", 0),
            })

        selected = get_stock(symbol)

        result = {
            "status": "ok",
            "source": "Bitget Reality US Stocks",
            "selected": selected,
            "best": {
                "symbol": ranking[0]["symbol"],
                "price": ranking[0]["price"],
                "decision": ranking[0]["decision"],
                "confidence": ranking[0]["confidence"],
                "technical": ranking[0].get("technical_score", 0),
                "fundamental": ranking[0].get("fundamental_score", 0),
                "opportunity": ranking[0].get("opportunity_score", 0),
                "rank": ranking[0].get("rank", 1),
            },
            "stocks": stocks,
        }

        _DASHBOARD_CACHE[symbol] = result
        _DASHBOARD_CACHE_TIME[symbol] = time.time()

        return result


HTML = r'''
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>SentixAI — Bitget US Stock Intelligence</title>

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #070a0f;
    color: #eef2f7;
    font-family: Arial, Helvetica, sans-serif;
}

.header {
    border-bottom: 1px solid #202733;
    background: #0a0e15;
    padding: 18px 24px;
    position: sticky;
    top: 0;
    z-index: 10;
}

.header-inner {
    max-width: 1400px;
    margin: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logo {
    font-size: 25px;
    font-weight: 900;
}

.logo span {
    color: #00d4aa;
}

.tag {
    color: #8993a4;
    font-size: 12px;
    margin-top: 4px;
}

.live {
    color: #00d4aa;
    font-size: 12px;
    font-weight: 800;
}

.container {
    max-width: 1400px;
    margin: auto;
    padding: 22px;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
}

.market-status {
    font-size: 16px;
    font-weight: 800;
}

.closed {
    color: #8993a4;
}

.open {
    color: #00d4aa;
}

.refresh {
    background: #111722;
    color: white;
    border: 1px solid #293342;
    border-radius: 7px;
    padding: 9px 14px;
    cursor: pointer;
}

.refresh:hover {
    border-color: #00d4aa;
}

.tabs {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    margin-bottom: 18px;
}

.tab {
    background: #10151e;
    color: #9ba5b5;
    border: 1px solid #232c39;
    padding: 10px 18px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 800;
}

.tab.active {
    background: rgba(0,212,170,.12);
    border-color: #00d4aa;
    color: #00d4aa;
}

.layout {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 18px;
}

.card {
    background: #0d121a;
    border: 1px solid #202733;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 18px;
}

.card-title {
    color: #8993a4;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: .7px;
    margin-bottom: 15px;
}

.quote {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}

.symbol {
    font-size: 30px;
    font-weight: 900;
}

.price {
    font-size: 30px;
    font-weight: 800;
    margin-top: 4px;
}

.change {
    margin-top: 5px;
    font-weight: 800;
}

.positive {
    color: #00d4aa;
}

.negative {
    color: #ff6478;
}

.signal {
    padding: 9px 14px;
    border-radius: 8px;
    font-weight: 900;
    display: inline-block;
}

.signal.BUY {
    color: #00d4aa;
    background: rgba(0,212,170,.12);
}

.signal.HOLD {
    color: #f4c95d;
    background: rgba(244,201,93,.10);
}

.signal.SELL {
    color: #ff6478;
    background: rgba(255,100,120,.10);
}

.chart-wrap {
    height: 310px;
    position: relative;
}

canvas {
    width: 100%;
    height: 100%;
}

.metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
}

.metric {
    background: #121822;
    border-radius: 9px;
    padding: 13px;
}

.label {
    color: #7e899a;
    font-size: 11px;
}

.value {
    font-size: 18px;
    font-weight: 800;
    margin-top: 5px;
}

.confidence {
    font-size: 42px;
    font-weight: 900;
}

.bar {
    height: 8px;
    background: #202733;
    border-radius: 20px;
    overflow: hidden;
    margin-top: 10px;
}

.bar div {
    height: 100%;
    background: #00d4aa;
}

.grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
}

.stock-row {
    display: grid;
    grid-template-columns: 55px 1fr 90px 80px 65px 100px;
    gap: 8px;
    padding: 12px 5px;
    border-bottom: 1px solid #202733;
    align-items: center;
    cursor: pointer;
}

.stock-row:hover {
    background: #111722;
}

.stock-head {
    color: #6f7b8d;
    font-size: 10px;
    font-weight: 800;
}

.ai {
    color: #c1c9d5;
    line-height: 1.65;
    font-size: 14px;
}

.source {
    color: #687487;
    font-size: 11px;
    margin-top: 15px;
}

@media(max-width: 900px) {
    .layout {
        grid-template-columns: 1fr;
    }

    .metrics {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media(max-width: 550px) {
    .container {
        padding: 12px;
    }

    .metrics {
        grid-template-columns: 1fr 1fr;
    }

    .stock-row {
        grid-template-columns: 45px 1fr 65px 62px 48px 75px;
        gap: 5px;
        font-size: 11px;
    }
}

/* SENTIXAI WELCOME PAGE */
#welcome {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background:
        radial-gradient(circle at 50% 40%, rgba(38, 255, 145, 0.10), transparent 32%),
        radial-gradient(circle at 20% 80%, rgba(0, 150, 255, 0.08), transparent 28%),
        #070a0f;
}

.welcome-grid {
    position: absolute;
    inset: 0;
    opacity: .18;
    background-image:
        linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px);
    background-size: 55px 55px;
    mask-image: radial-gradient(circle at center, black, transparent 75%);
}

.welcome-content {
    position: relative;
    z-index: 2;
    width: min(900px, 92%);
    text-align: center;
}

.welcome-badge {
    display: inline-block;
    padding: 8px 15px;
    border: 1px solid rgba(38,255,145,.25);
    border-radius: 999px;
    color: #26ff91;
    background: rgba(38,255,145,.06);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.5px;
    margin-bottom: 25px;
}

.welcome-logo {
    font-size: clamp(70px, 13vw, 150px);
    line-height: .9;
    font-weight: 1000;
    letter-spacing: -7px;
    color: #f4f7fb;
    text-shadow: 0 0 45px rgba(38,255,145,.10);
}

.welcome-logo span {
    color: #26ff91;
}

.welcome-subtitle {
    margin-top: 24px;
    font-size: clamp(15px, 2vw, 21px);
    font-weight: 800;
    letter-spacing: 5px;
    color: #d8dee8;
}

.welcome-description {
    max-width: 650px;
    margin: 22px auto 0;
    color: #8993a3;
    font-size: 15px;
    line-height: 1.7;
}

.enter-btn {
    margin-top: 34px;
    padding: 15px 28px;
    border: 0;
    border-radius: 10px;
    background: #26ff91;
    color: #06100a;
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 1.2px;
    cursor: pointer;
    box-shadow: 0 0 35px rgba(38,255,145,.20);
    transition: transform .2s, box-shadow .2s;
}

.enter-btn span {
    margin-left: 12px;
    font-size: 18px;
}

.enter-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 0 45px rgba(38,255,145,.35);
}

.welcome-features {
    display: flex;
    justify-content: center;
    gap: 45px;
    margin-top: 55px;
}

.welcome-features div {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.welcome-features strong {
    font-size: 10px;
    letter-spacing: 1px;
    color: #dce3ec;
}

.welcome-features span {
    font-size: 11px;
    color: #687384;
}

#app {
    min-height: 100vh;
}

@media(max-width: 600px) {
    .welcome-logo {
        letter-spacing: -4px;
    }

    .welcome-subtitle {
        letter-spacing: 2px;
    }

    .welcome-features {
        gap: 18px;
        margin-top: 40px;
    }

    .welcome-features strong {
        font-size: 9px;
    }

    .welcome-features span {
        font-size: 9px;
    }
}


/* SIGNAL BREAKDOWN */
.signal-breakdown {
    margin-top: 16px;
    padding-top: 14px;
    border-top: 1px solid #202733;
}

.breakdown-title {
    margin-bottom: 10px;
    color: #8e99aa;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1.2px;
}

.breakdown-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
}

.breakdown-item {
    padding: 10px;
    border: 1px solid #202733;
    border-radius: 8px;
    background: #0b0f15;
}

.breakdown-item span {
    display: block;
    color: #707b8d;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: .8px;
}

.breakdown-item strong {
    display: block;
    margin-top: 5px;
    font-size: 14px;
}

@media(max-width:550px) {
    .breakdown-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}


/* SENTIXAI CHAT */
.chat-card {
    margin-top: 16px;
}

.chat-subtitle {
    color: #707b8d;
    font-size: 11px;
    margin-top: -6px;
    margin-bottom: 14px;
}

.chat-window {
    height: 300px;
    overflow-y: auto;
    padding: 12px;
    border: 1px solid #202733;
    border-radius: 10px;
    background: #080c12;
}

.chat-message {
    display: flex;
    margin-bottom: 10px;
}

.chat-message.user {
    justify-content: flex-end;
}

.chat-bubble {
    max-width: 82%;
    padding: 10px 12px;
    border-radius: 10px;
    font-size: 12px;
    line-height: 1.55;
}

.chat-message.ai .chat-bubble {
    background: #101722;
    border: 1px solid #202733;
    color: #c7ced9;
}

.chat-message.user .chat-bubble {
    background: #26ff91;
    color: #06100a;
    font-weight: 700;
}

.chat-quick {
    display: flex;
    gap: 7px;
    flex-wrap: wrap;
    margin-top: 10px;
}

.chat-quick button {
    border: 1px solid #26303d;
    background: #0b0f15;
    color: #aeb8c7;
    border-radius: 7px;
    padding: 7px 9px;
    font-size: 10px;
    cursor: pointer;
}

.chat-quick button:hover {
    border-color: #26ff91;
    color: #26ff91;
}

.chat-input-row {
    display: flex;
    gap: 8px;
    margin-top: 10px;
}

.chat-input {
    flex: 1;
    min-width: 0;
    border: 1px solid #202733;
    background: #0b0f15;
    color: #e8edf4;
    border-radius: 8px;
    padding: 11px;
    outline: none;
    font-size: 12px;
}

.chat-input:focus {
    border-color: #26ff91;
}

.chat-send {
    border: 0;
    border-radius: 8px;
    padding: 0 16px;
    background: #26ff91;
    color: #06100a;
    font-weight: 900;
    cursor: pointer;
}

.chat-send:hover {
    filter: brightness(1.08);
}

@media(max-width:550px) {
    .chat-window {
        height: 260px;
    }

    .chat-bubble {
        max-width: 90%;
    }
}

/* AI ANALYST */
.analyst-signal {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
    padding: 16px;
    margin-bottom: 14px;
    border: 1px solid #202733;
    border-radius: 10px;
    background: #0b0f15;
}

.analyst-decision {
    margin-top: 5px;
    font-size: 28px;
    font-weight: 1000;
}

.analyst-confidence {
    text-align: right;
}

.analyst-confidence strong {
    display: block;
    margin-top: 5px;
    font-size: 22px;
}

.analyst-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 16px;
}

.analyst-box {
    padding: 11px;
    border: 1px solid #202733;
    border-radius: 8px;
    background: #0b0f15;
}

.analyst-box strong {
    display: block;
    margin-top: 5px;
    font-size: 16px;
}

.analyst-section {
    border-top: 1px solid #202733;
    padding-top: 14px;
    margin-top: 14px;
}

.analyst-section-title {
    margin-bottom: 9px;
    color: #8e99aa;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1.2px;
}

.analyst-driver {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 7px 0;
    color: #b8c0cc;
    font-size: 12px;
    line-height: 1.5;
}

.analyst-driver .dot {
    width: 6px;
    height: 6px;
    margin-top: 6px;
    flex: 0 0 6px;
    border-radius: 50%;
    background: #26ff91;
}

.analyst-driver.risk .dot {
    background: #f4c95d;
}

@media(max-width: 550px) {
    .analyst-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}


/* SENTIXAI LARGE STOCK SEARCH */
.stock-search-wrap {
    width: 100%;
    margin-bottom: 18px;
}
.stock-search {
    width: 100% !important;
    min-height: 72px !important;
    box-sizing: border-box !important;
    padding: 20px 24px !important;
    font-size: 19px !important;
    border-radius: 14px !important;
    border-width: 2px !important;
}
.stock-search::placeholder {
    font-size: 17px;
}

</style>
</head>

<body>

<div id="welcome" style="display:none;">
    <div class="welcome-grid"></div>

    <div class="welcome-content">
        <div class="welcome-badge">● LIVE U.S. STOCK INTELLIGENCE</div>

        <div class="welcome-logo">
            SENTIX<span>AI</span>
        </div>

        <div class="welcome-subtitle">
            AI-POWERED STOCK MARKET ANALYSIS
        </div>

        <div class="welcome-description">
            Analyze U.S. stocks using live Bitget Reality market data,
            technical indicators, fundamentals, sentiment and AI-driven signals.
        </div>

        <button class="enter-btn" onclick="enterSentix()">
            ENTER SENTIXAI
            <span>→</span>
        </button>

        <div class="welcome-features">
            <div>
                <strong>LIVE DATA</strong>
                <span>Bitget Reality</span>
            </div>
            <div>
                <strong>AI ANALYSIS</strong>
                <span>Explainable signals</span>
            </div>
            <div>
                <strong>MARKET SIGNALS</strong>
                <span>BUY · HOLD · SELL</span>
            </div>
        </div>
    </div>
</div>

<div id="app">

<div class="header">
    <div class="header-inner">
        <div>
            <div class="logo">SENTIX<span>AI</span></div>
            <div class="tag">AI U.S. Stock Intelligence · Bitget Reality</div>
        </div>

        <div class="live">● BITGET DATA</div>
    </div>
</div>

<div class="container">

    <div class="topbar">
        <div>
            <div class="market-status" id="marketStatus">
                ● CHECKING MARKET
            </div>
            <div class="tag" id="updated">Waiting for data...</div>
        </div>

        <button class="refresh" onclick="loadData()">
            Refresh
        </button>
    </div>

    
<div class="stock-search-wrap">
    <input
        id="stockSearch"
        class="stock-search"
        type="text"
        placeholder="Search 2,800+ Bitget Reality stocks..."
        autocomplete="off"
    >
    <div id="stockSearchResults" class="stock-search-results"></div>
</div>

<div class="tabs">
        <button class="tab active" data-symbol="AMZN">AMZN</button>
        <button class="tab" data-symbol="NVDA">NVDA</button>
        <button class="tab" data-symbol="MSFT">MSFT</button>
        <button class="tab" data-symbol="AAPL">AAPL</button>
        <button class="tab" data-symbol="TSLA">TSLA</button>
    </div>

    <div class="layout">

        <main>

            <div class="card">

                <div class="card-title">BITGET REALITY · LIVE MARKET</div>

                <div class="quote">
                    <div>
                        <div class="symbol" id="symbol">--</div>
                        <div class="price" id="price">$--</div>
                        <div class="change" id="change">--</div>
                    </div>

                    <div id="decision" class="signal HOLD">
                        --
                    </div>
                </div>

                <div class="chart-wrap">
                    <canvas id="chart"></canvas>
                </div>

                <div class="source" id="bitgetSymbol">
                    Bitget symbol: --
                </div>

            </div>

            <div class="card">

                <div class="card-title">
                    SENTIXAI SIGNAL ENGINE
                </div>

                <div class="metrics">

                    <div class="metric">
                        <div class="label">CONFIDENCE</div>
                        <div class="value" id="confidence">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">TECHNICAL</div>
                        <div class="value" id="technical">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">FUNDAMENTAL</div>
                        <div class="value" id="fundamental">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">RSI-14</div>
                        <div class="value" id="rsi">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">SIGNAL STRENGTH</div>
                        <div class="value" id="signalStrength">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">BUY GAP</div>
                        <div class="value" id="confidenceGap">--</div>
                    </div>

                </div>

                <div class="bar">
                    <div id="confidenceBar" style="width:0%"></div>
                </div>

                <div class="signal-breakdown">

                    <div class="breakdown-title">
                        SIGNAL BREAKDOWN
                    </div>

                    <div class="breakdown-grid">

                        <div class="breakdown-item">
                            <span>24H MOVE</span>
                            <strong id="break24h">--</strong>
                        </div>

                        <div class="breakdown-item">
                            <span>MOMENTUM</span>
                            <strong id="breakMomentum">--</strong>
                        </div>

                        <div class="breakdown-item">
                            <span>5D TREND</span>
                            <strong id="breakTrend5">--</strong>
                        </div>

                        <div class="breakdown-item">
                            <span>10D TREND</span>
                            <strong id="breakTrend10">--</strong>
                        </div>

                        <div class="breakdown-item">
                            <span>20D TREND</span>
                            <strong id="breakTrend20">--</strong>
                        </div>

                        <div class="breakdown-item">
                            <span>PRICE / SMA20</span>
                            <strong id="breakSma">--</strong>
                        </div>

                    </div>

                </div>

            </div>

            <div class="card">

                <div class="card-title">
                    BITGET STOCK OPPORTUNITY SCAN
                </div>

                <div class="stock-row stock-head">
                    <div>RANK</div>
                    <div>STOCK</div>
                    <div>PRICE</div>
                    <div>SIGNAL</div>
                    <div>CONF.</div>
                    <div>OPPORTUNITY</div>
                </div>

                <div id="stocks"></div>

            </div>

        </main>

        <aside>

            <div class="card">

                <div class="card-title">
                    SENTIXAI · AI ANALYST
                </div>

                <div class="analyst-signal">
                    <div>
                        <div class="label">AI SIGNAL</div>
                        <div class="analyst-decision" id="analystDecision">
                            --
                        </div>
                    </div>

                    <div class="analyst-confidence">
                        <div class="label">CONFIDENCE</div>
                        <strong id="analystConfidence">--</strong>
                    </div>
                </div>

                <div class="analyst-grid">

                    <div class="analyst-box">
                        <div class="label">TECHNICAL</div>
                        <strong id="analystTechnical">--</strong>
                    </div>

                    <div class="analyst-box">
                        <div class="label">FUNDAMENTAL</div>
                        <strong id="analystFundamental">--</strong>
                    </div>

                    <div class="analyst-box">
                        <div class="label">RSI 14</div>
                        <strong id="analystRsi">--</strong>
                    </div>

                    <div class="analyst-box">
                        <div class="label">BUY GAP</div>
                        <strong id="analystGap">--</strong>
                    </div>

                </div>

                <div class="analyst-section">
                    <div class="analyst-section-title">WHY THIS SIGNAL?</div>
                    <div id="analystDrivers">
                        Loading analysis...
                    </div>
                </div>

                <div class="analyst-section">
                    <div class="analyst-section-title">AI INVESTMENT THESIS</div>
                    <div class="ai" id="thesis">
                        Loading...
                    </div>
                </div>

            </div>

            <div class="card chat-card">

                <div class="card-title">
                    ASK SENTIXAI
                </div>

                <div class="chat-subtitle">
                    Ask about the selected stock using live Bitget Reality market data.
                </div>

                <div class="chat-window" id="chatWindow">

                    <div class="chat-message ai">
                        <div class="chat-bubble">
                            Hello. I'm SentixAI. Ask me about the selected stock,
                            its signal, RSI, trends, fundamentals or current price.
                        </div>
                    </div>

                </div>

                <div class="chat-quick">

                    <button onclick="askQuick('Why is this stock HOLD?')">
                        Why HOLD?
                    </button>

                    <button onclick="askQuick('What is driving the signal?')">
                        Signal drivers
                    </button>

                    <button onclick="askQuick('Is this stock overbought?')">
                        RSI check
                    </button>

                    <button onclick="askQuick('What are the current trends?')">
                        Trends
                    </button>

                </div>

                <div class="chat-input-row">

                    <input
                        id="chatInput"
                        class="chat-input"
                        type="text"
                        placeholder="Ask SentixAI..."
                        onkeydown="if(event.key==='Enter') sendChat()"
                    >

                    <button
                        class="chat-send"
                        onclick="sendChat()"
                    >
                        ASK
                    </button>

                </div>

            </div>

            <div class="card">

                <div class="card-title">
                    TECHNICAL SNAPSHOT
                </div>

                <div class="grid2">

                    <div class="metric">
                        <div class="label">SMA 20</div>
                        <div class="value" id="sma">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">MOMENTUM</div>
                        <div class="value" id="momentum">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">5D TREND</div>
                        <div class="value" id="trend5">--</div>
                    </div>

                    <div class="metric">
                        <div class="label">20D TREND</div>
                        <div class="value" id="trend20">--</div>
                    </div>

                </div>

            </div>

            <div class="card">

                <div class="card-title">
                    DATA SOURCE
                </div>

                <div class="ai">
                    Bitget Reality US Stocks
                    <br><br>
                    Public market data · Quotes · Historical candles ·
                    Fundamentals · Market state
                </div>

            </div>

        </aside>

    </div>

</div>

<script>

let currentSymbol = "AMZN";
let currentHistory = [];

function money(value) {
    return "$" + Number(value || 0).toFixed(2);
}

function pct(value) {
    const n = Number(value || 0);
    return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

function setMarketStatus() {

    const now = new Date();
    const day = now.getDay();

    let text = "● MARKET CLOSED";
    let cls = "closed";

    if (day !== 0 && day !== 6) {

        const est = new Date(
            now.toLocaleString(
                "en-US",
                {timeZone: "America/New_York"}
            )
        );

        const minutes =
            est.getHours() * 60 +
            est.getMinutes();

        if (minutes >= 240 && minutes < 570) {
            text = "● PRE-MARKET";
            cls = "open";
        } else if (minutes >= 570 && minutes < 960) {
            text = "● MARKET OPEN";
            cls = "open";
        } else if (minutes >= 960 && minutes < 1200) {
            text = "● AFTER-HOURS";
            cls = "open";
        } else if (minutes >= 1200 || minutes < 240) {
            text = "● OVERNIGHT";
            cls = "open";
        }
    }

    const el = document.getElementById("marketStatus");

    el.textContent = text;
    el.className = "market-status " + cls;
}


function drawChart(history) {

    const canvas = document.getElementById("chart");
    const rect = canvas.getBoundingClientRect();

    const dpr = window.devicePixelRatio || 1;

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;

    const ctx = canvas.getContext("2d");

    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;

    ctx.clearRect(0, 0, width, height);

    if (!history || history.length < 2) {
        ctx.fillStyle = "#697586";
        ctx.font = "13px Arial";
        ctx.fillText(
            "Historical Bitget candles unavailable",
            20,
            height / 2
        );
        return;
    }

    const candles = history.map(x => ({
        time: Number(x.time),
        open: Number(x.open),
        high: Number(x.high),
        low: Number(x.low),
        close: Number(x.close)
    }));

    const min = Math.min(...candles.map(x => x.low));
    const max = Math.max(...candles.map(x => x.high));
    const range = max - min || 1;

    const left = 58;
    const right = width - 12;
    const top = 24;
    const bottom = height - 38;

    function priceY(price) {
        return bottom -
            ((price - min) / range) *
            (bottom - top);
    }

    // Grid and price scale
    ctx.strokeStyle = "#1b2330";
    ctx.lineWidth = 1;

    for (let i = 0; i < 5; i++) {

        const y =
            top +
            ((bottom - top) / 4) * i;

        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();

        const labelValue =
            max - (range * i / 4);

        ctx.fillStyle = "#8993a4";
        ctx.font = "10px Arial";
        ctx.textAlign = "right";

        ctx.fillText(
            money(labelValue),
            left - 7,
            y + 3
        );
    }

    // Date labels
    ctx.textAlign = "center";
    ctx.fillStyle = "#8993a4";
    ctx.font = "10px Arial";

    [0, Math.floor((candles.length - 1) / 2), candles.length - 1]
        .forEach(index => {

            const item = candles[index];

            const x =
                left +
                (index / (candles.length - 1)) *
                (right - left);

            const date = new Date(item.time);

            const label =
                date.toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric"
                });

            ctx.fillText(
                label,
                x,
                height - 10
            );
        });

    // Candlesticks
    const chartWidth = right - left;
    const candleSpace = chartWidth / candles.length;
    const bodyWidth = Math.max(
        5,
        Math.min(14, candleSpace * 0.58)
    );

    candles.forEach((candle, i) => {

        const x =
            left +
            (i + 0.5) * candleSpace;

        const openY = priceY(candle.open);
        const closeY = priceY(candle.close);
        const highY = priceY(candle.high);
        const lowY = priceY(candle.low);

        const bullish = candle.close >= candle.open;

        // Wick
        ctx.strokeStyle =
            bullish ? "#00d4aa" : "#ff6478";

        ctx.lineWidth = 1;

        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        // Body
        const bodyTop = Math.min(openY, closeY);
        const bodyHeight =
            Math.max(1, Math.abs(closeY - openY));

        ctx.fillStyle =
            bullish ? "#00d4aa" : "#ff6478";

        ctx.fillRect(
            x - bodyWidth / 2,
            bodyTop,
            bodyWidth,
            bodyHeight
        );
    });

    // Current price line
    const last = candles[candles.length - 1];
    const currentY = priceY(last.close);

    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "#8993a4";
    ctx.lineWidth = 1;

    ctx.beginPath();
    ctx.moveTo(left, currentY);
    ctx.lineTo(right, currentY);
    ctx.stroke();

    ctx.setLineDash([]);

    // Current price label
    ctx.fillStyle = "#eef2f7";
    ctx.font = "12px Arial";
    ctx.textAlign = "left";

    ctx.fillText(
        money(last.close),
        10,
        14
    );
}


function render(data) {

    const s = data.selected;

    document.getElementById("symbol").textContent =
        s.symbol;

    document.getElementById("price").textContent =
        money(s.price);

    const change = document.getElementById("change");

    change.textContent =
        pct(s.change_24h);

    change.className =
        "change " +
        (Number(s.change_24h) >= 0
            ? "positive"
            : "negative");

    const decision =
        document.getElementById("decision");

    decision.textContent =
        s.decision;

    decision.className =
        "signal " + s.decision;

    document.getElementById("confidence").textContent =
        Number(s.confidence).toFixed(1) + "%";

    document.getElementById("signalStrength").textContent =
        s.thesis?.signal_strength || "--";

    const buyGap = Number(
        s.thesis?.confidence_gap ?? s.confidence_gap ?? 0
    );

    document.getElementById("confidenceGap").textContent =
        s.decision === "BUY"
            ? "0.0 pts"
            : buyGap.toFixed(1) + " pts";

    document.getElementById("technical").textContent =
        Number(s.technical).toFixed(1) + "/100";

    document.getElementById("fundamental").textContent =
        Number(s.fundamental).toFixed(1) + "/100";

    document.getElementById("rsi").textContent =
        Number(s.rsi).toFixed(2);

    document.getElementById("sma").textContent =
        money(s.sma20);

    document.getElementById("momentum").textContent =
        Number(s.momentum).toFixed(2);

    document.getElementById("trend5").textContent =
        pct(s.trend_5d);

    document.getElementById("trend20").textContent =
        pct(s.trend_20d);

    const confidenceBar = document.getElementById("confidenceBar");
    confidenceBar.style.width =
        Math.max(0, Math.min(100, Number(s.confidence))) + "%";
    confidenceBar.style.background =
        Number(s.confidence) >= 70 ? "#00d4aa" :
        Number(s.confidence) <= 30 ? "#ff6478" : "#f4c95d";

    // Signal Breakdown
    const live24h = Number(
        s.change_24h !== undefined ? s.change_24h : s.change_percent
    );

    const breakdownMomentum = Number(s.momentum || 0);
    const breakdownTrend5 = Number(s.trend_5d || 0);
    const breakdownTrend10 = Number(s.trend_10d || 0);
    const breakdownTrend20 = Number(s.trend_20d || 0);
    const breakdownPriceVsSma = Number(s.price_vs_sma20 || 0);

    const formatSignal = (value, suffix = "%") => {
        if (!Number.isFinite(value)) return "--";
        return (value >= 0 ? "+" : "") + value.toFixed(2) + suffix;
    };

    document.getElementById("break24h").textContent =
        formatSignal(live24h);

    document.getElementById("breakMomentum").textContent =
        formatSignal(breakdownMomentum);

    document.getElementById("breakTrend5").textContent =
        formatSignal(breakdownTrend5);

    document.getElementById("breakTrend10").textContent =
        formatSignal(breakdownTrend10);

    document.getElementById("breakTrend20").textContent =
        formatSignal(breakdownTrend20);

    document.getElementById("breakSma").textContent =
        formatSignal(breakdownPriceVsSma);

    // Color positive / negative signals
    [
        ["break24h", live24h],
        ["breakMomentum", breakdownMomentum],
        ["breakTrend5", breakdownTrend5],
        ["breakTrend10", breakdownTrend10],
        ["breakTrend20", breakdownTrend20],
        ["breakSma", breakdownPriceVsSma]
    ].forEach(([id, value]) => {
        const el = document.getElementById(id);
        el.style.color =
            value > 0 ? "#26ff91" :
            value < 0 ? "#ff6478" :
            "#8e99aa";
    });

    const displayBitgetSymbol =
        s.bitget_symbol
            ? s.bitget_symbol.replace(/^R/, "r")
            : "--";

    document.getElementById("bitgetSymbol").textContent =
        "Bitget Reality symbol: " + displayBitgetSymbol;

    const thesis =
        s.thesis && s.thesis.thesis
            ? s.thesis.thesis
            : [];

    document.getElementById("thesis").innerHTML =
        thesis.map(x => "<p>• " + x + "</p>").join("");

    // AI Analyst: explain why SentixAI reached this signal
    const confidence = Number(s.confidence || 0);
    const technical = Number(s.technical || 0);
    const fundamental = Number(s.fundamental || 0);
    const rsi = Number(s.rsi || 0);
    const gap = Number(s.confidence_gap || 0);

    const analystDecision = document.getElementById("analystDecision");

    analystDecision.textContent = s.decision || "--";

    analystDecision.style.color =
        s.decision === "BUY" ? "#26ff91" :
        s.decision === "SELL" ? "#ff6478" :
        "#f4c95d";

    document.getElementById("analystConfidence").textContent =
        confidence.toFixed(1) + "%";

    document.getElementById("analystTechnical").textContent =
        technical.toFixed(0) + "/100";

    document.getElementById("analystFundamental").textContent =
        fundamental.toFixed(0) + "/100";

    document.getElementById("analystRsi").textContent =
        rsi ? rsi.toFixed(1) : "--";

    document.getElementById("analystGap").textContent =
        gap > 0 ? gap.toFixed(1) + " pts" : "READY";

    const drivers = [];

    if (technical >= 65) {
        drivers.push(["positive", "Technical structure is supporting the signal with a strong technical score."]);
    } else if (technical < 40) {
        drivers.push(["risk", "Technical structure is weak and is limiting the signal."]);
    } else {
        drivers.push(["risk", "Technical conditions are mixed, keeping the signal from becoming stronger."]);
    }

    if (fundamental >= 65) {
        drivers.push(["positive", "Fundamentals are strong and provide additional support."]);
    } else if (fundamental < 40) {
        drivers.push(["risk", "Fundamental valuation or forecast factors are weighing on the signal."]);
    } else {
        drivers.push(["risk", "Fundamentals are mixed and do not provide a strong confirmation."]);
    }

    if (rsi >= 70) {
        drivers.push(["risk", "RSI is elevated, indicating potentially overbought conditions."]);
    } else if (rsi >= 50 && rsi < 70) {
        drivers.push(["positive", "RSI remains in a constructive range without extreme overbought conditions."]);
    } else if (rsi > 0 && rsi < 35) {
        drivers.push(["positive", "RSI is low, which may indicate an oversold condition."]);
    } else if (rsi > 0) {
        drivers.push(["risk", "RSI is below the stronger bullish range."]);
    }

    const trend5 = Number(s.trend_5d || 0);
    const trend20 = Number(s.trend_20d || 0);

    if (trend5 > 0 && trend20 > 0) {
        drivers.push(["positive", "5D and 20D trends are aligned positively."]);
    } else if (trend5 < 0 && trend20 < 0) {
        drivers.push(["risk", "5D and 20D trends are both negative."]);
    } else {
        drivers.push(["risk", "Short-term and broader trend signals are not fully aligned."]);
    }

    document.getElementById("analystDrivers").innerHTML =
        drivers.map(item =>
            '<div class="analyst-driver ' +
            (item[0] === "risk" ? "risk" : "") +
            '"><span class="dot"></span><span>' +
            item[1] +
            '</span></div>'
        ).join("");

    const container =
        document.getElementById("stocks");

    container.innerHTML = "";

    data.stocks.forEach(stock => {

        const row =
            document.createElement("div");

        row.className = "stock-row";
        row.style.cursor = "pointer";
        row.title = "Analyze " + stock.symbol;
        row.onclick = () => selectSymbol(stock.symbol);

        row.innerHTML = `
            <div>
                <strong>#${stock.rank}</strong>
            </div>

            <div>
                <strong>${stock.symbol}</strong>
            </div>

            <div>
                ${money(stock.price)}
            </div>

            <div>
                <span class="signal ${stock.decision}">
                    ${stock.decision}
                </span>
            </div>

            <div>
                ${Number(stock.confidence).toFixed(1)}%
            </div>

            <div>
                <strong>${Number(stock.opportunity || 0).toFixed(1)}</strong>
            </div>
        `;

        row.onclick = () => {
            selectSymbol(stock.symbol);
        };

        container.appendChild(row);
    });

    currentHistory = s.historical || [];

    drawChart(currentHistory);

    document.getElementById("updated").textContent =
        "Updated " +
        new Date().toLocaleTimeString();
}


function enterSentix() {
    const welcome = document.getElementById("welcome");

    welcome.style.transition = "opacity .45s ease, transform .45s ease";
    welcome.style.opacity = "0";
    welcome.style.transform = "scale(1.02)";

    setTimeout(() => {
        welcome.style.display = "none";
        window.scrollTo(0, 0);

        requestAnimationFrame(() => {
            drawChart(currentHistory);
        });
    }, 450);
}

async function loadData() {

    setMarketStatus();

    try {

        const response =
            await fetch(
                "/api/data?symbol=" +
                encodeURIComponent(currentSymbol)
            );

        const data =
            await response.json();

        if (data.status !== "ok") {
            throw new Error(
                data.message || "API error"
            );
        }

        render(data);

    } catch (error) {

        console.error(error);

        document.getElementById("updated").textContent =
            "Data error: " + error.message;
    }
}



async function askQuick(question) {

    document.getElementById("chatInput").value = question;

    await sendChat();
}

function addChatMessage(type, text) {

    const windowEl = document.getElementById("chatWindow");

    const message = document.createElement("div");
    message.className = "chat-message " + type;

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = text;

    message.appendChild(bubble);
    windowEl.appendChild(message);

    windowEl.scrollTop = windowEl.scrollHeight;
}

async function sendChat() {

    const input = document.getElementById("chatInput");
    const question = input.value.trim();

    if (!question) return;

    addChatMessage("user", question);

    input.value = "";

    addChatMessage("ai", "Analyzing live market data...");

    const loadingBubble =
        document.querySelector(
            "#chatWindow .chat-message.ai:last-child .chat-bubble"
        );

    try {

        const url =
            "/api/chat?symbol=" +
            encodeURIComponent(currentSymbol) +
            "&question=" +
            encodeURIComponent(question);

        const response = await fetch(url);
        const data = await response.json();

        if (data.status !== "ok") {
            throw new Error(
                data.message || "Chat request failed"
            );
        }

        loadingBubble.textContent = data.answer;

    } catch (error) {

        loadingBubble.textContent =
            "I couldn't analyze that request right now. Please try again.";

        console.error(
            "SentixAI chat error:",
            error
        );
    }

    document.getElementById("chatWindow").scrollTop =
        document.getElementById("chatWindow").scrollHeight;
}

function selectSymbol(symbol) {

    currentSymbol = symbol;

    const searchInput = document.getElementById("stockSearch");
    if (searchInput) {
        searchInput.value = symbol;
    }

    clearStockSearch();

    // Force the searched stock chart to resize before rendering.
    requestAnimationFrame(() => {
        drawChart(currentHistory);
    });

    document.querySelectorAll(".tab")
        .forEach(tab => {

            tab.classList.toggle(
                "active",
                tab.dataset.symbol === symbol
            );
        });

    loadData();
}


document.querySelectorAll(".tab")
    .forEach(tab => {

        tab.addEventListener(
            "click",
            () => selectSymbol(tab.dataset.symbol)
        );
    });


window.addEventListener(
    "resize",
    () => drawChart(currentHistory)
);

// Refresh Bitget market data every 30 seconds.
setInterval(() => {
    loadData();
}, 30000);


setMarketStatus();
loadData();

setInterval(
    () => {
        setMarketStatus();
        loadData();
    },
    60000
);


let stockSearchTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("stockSearch");

    if (!input) {
        console.error("SentixAI: stockSearch input not found");
        return;
    }

    input.addEventListener("input", () => {
        searchStocks(input.value);
    });

    input.addEventListener("focus", () => {
        if (input.value.trim()) {
            searchStocks(input.value);
        }
    });
});

function clearStockSearch() {
    const results = document.getElementById("stockSearchResults");

    if (results) {
        results.innerHTML = "";
        results.style.display = "none";
    }
}

function chooseSearchedStock(symbol) {
    const input = document.getElementById("stockSearch");

    if (input) {
        input.value = symbol;
    }

    clearStockSearch();

    currentSymbol = String(symbol).toUpperCase();

    document.querySelectorAll(".tab").forEach(tab => {
        tab.classList.toggle(
            "active",
            tab.dataset.symbol === currentSymbol
        );
    });

    loadData();
}


async function searchStocks(query) {
    const results = document.getElementById("stockSearchResults");

    if (!results) return;

    query = query.trim();

    if (!query) {
        clearStockSearch();
        return;
    }

    clearTimeout(stockSearchTimer);

    stockSearchTimer = setTimeout(async () => {
        try {
            const response = await fetch(
                "/api/stocks?q=" + encodeURIComponent(query)
            );

            const data = await response.json();

            if (data.status !== "ok") {
                throw new Error(data.message || "Search failed");
            }

            if (!data.stocks || !data.stocks.length) {
                results.innerHTML =
                    '<div class="stock-search-empty">' +
                    'No Bitget Reality stock found.' +
                    '</div>';

                results.style.display = "block";
                return;
            }

            results.innerHTML = "";

            data.stocks.forEach(stock => {
                const symbol = String(stock.symbol || "");
                const name = String(
                    stock.name || symbol
                )
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;");

                const bitget = String(
                    stock.bitget_symbol || ""
                )
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;");

                const button = document.createElement("button");

                button.type = "button";
                button.className = "stock-search-result";

                const symbolEl = document.createElement("span");
                symbolEl.className = "stock-search-symbol";
                symbolEl.textContent = symbol;

                const nameEl = document.createElement("span");
                nameEl.className = "stock-search-name";
                nameEl.textContent = name;

                const bitgetEl = document.createElement("span");
                bitgetEl.className = "stock-search-bitget";
                bitgetEl.textContent = bitget;

                button.appendChild(symbolEl);
                button.appendChild(nameEl);
                button.appendChild(bitgetEl);

                button.addEventListener("click", (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    chooseSearchedStock(symbol);
                });

                results.appendChild(button);

                return;
            });

            results.style.display = "block";

        } catch (error) {
            results.innerHTML =
                '<div class="stock-search-empty">' +
                'Search unavailable right now.' +
                '</div>';

            results.style.display = "block";

            console.error(
                "SentixAI stock search error:",
                error
            );
        }
    }, 180);
}

document.addEventListener("click", (event) => {
    const wrap = document.querySelector(
        ".stock-search-wrap"
    );

    if (wrap && !wrap.contains(event.target)) {
        clearStockSearch();
    }
});

</script>

</body>
</html>
'''



def sentix_chat_answer(symbol, question, market):
    """
    SentixAI conversational analyst.

    Uses the same live Bitget Reality analysis powering
    the dashboard. Supports signal explanations,
    buy/hold questions, technical/fundamental questions,
    and live stock comparisons.
    """

    q = question.lower().strip()

    price = float(market.get("price", 0) or 0)
    change = float(market.get("change_24h", 0) or 0)
    confidence = float(market.get("confidence", 0) or 0)
    buy_threshold = float(market.get("buy_threshold", 70) or 70)
    confidence_gap = float(
        market.get("confidence_gap", buy_threshold - confidence)
        or 0
    )
    technical = float(market.get("technical", 0) or 0)
    fundamental = float(market.get("fundamental", 0) or 0)
    rsi = float(market.get("rsi", 0) or 0)
    momentum = float(market.get("momentum", 0) or 0)
    trend5 = float(market.get("trend_5d", 0) or 0)
    trend10 = float(market.get("trend_10d", 0) or 0)
    trend20 = float(market.get("trend_20d", 0) or 0)
    price_vs_sma = float(market.get("price_vs_sma20", 0) or 0)
    opportunity = float(
        market.get("opportunity_score", confidence)
        or confidence
    )
    decision = str(market.get("decision", "HOLD"))

    def stock_summary(stock_symbol, data):
        return {
            "symbol": stock_symbol,
            "price": float(data.get("price", 0) or 0),
            "change": float(data.get("change_24h", 0) or 0),
            "confidence": float(data.get("confidence", 0) or 0),
            "technical": float(data.get("technical", 0) or 0),
            "fundamental": float(data.get("fundamental", 0) or 0),
            "rsi": float(data.get("rsi", 0) or 0),
            "trend5": float(data.get("trend_5d", 0) or 0),
            "trend10": float(data.get("trend_10d", 0) or 0),
            "trend20": float(data.get("trend_20d", 0) or 0),
            "momentum": float(data.get("momentum", 0) or 0),
            "price_vs_sma": float(data.get("price_vs_sma20", 0) or 0),
            "opportunity": float(
                data.get("opportunity_score", data.get("confidence", 0))
                or 0
            ),
            "decision": str(data.get("decision", "HOLD")),
        }

    # ---------------------------------------------------------
    # LIVE STOCK COMPARISON
    # ---------------------------------------------------------

    comparison_symbols = []

    import re

    question_symbols = set(
        re.findall(r"\b[A-Z]{1,6}\b", question.upper())
    )

    universe_symbols = {
        str(item.get("symbol", "")).upper().strip()
        for item in get_stock_universe()
    }

    for candidate_symbol in question_symbols:
        if (
            candidate_symbol
            and candidate_symbol != symbol
            and candidate_symbol in universe_symbols
        ):
            comparison_symbols.append(candidate_symbol)

    if (
        any(word in q for word in [
            "compare",
            "versus",
            " vs ",
            "better than",
            "better"
        ])
        and comparison_symbols
    ):
        other_symbol = comparison_symbols[0]

        try:
            other_response = get_dashboard_data(other_symbol)
            other_market = other_response.get(
                "selected",
                other_response
            )

            a = stock_summary(symbol, market)
            b = stock_summary(other_symbol, other_market)

            winner = a if a["opportunity"] >= b["opportunity"] else b
            loser = b if winner is a else a
            gap = abs(a["opportunity"] - b["opportunity"])

            reasons = []

            if winner["technical"] > loser["technical"]:
                reasons.append(
                    f"stronger technical score ({winner['technical']:.0f}/100 vs {loser['technical']:.0f}/100)"
                )

            if winner["fundamental"] > loser["fundamental"]:
                reasons.append(
                    f"stronger fundamentals ({winner['fundamental']:.0f}/100 vs {loser['fundamental']:.0f}/100)"
                )

            if winner["trend5"] > loser["trend5"]:
                reasons.append(
                    f"better 5D trend ({winner['trend5']:+.1f}% vs {loser['trend5']:+.1f}%)"
                )

            if winner["trend10"] > loser["trend10"]:
                reasons.append(
                    f"better 10D trend ({winner['trend10']:+.1f}% vs {loser['trend10']:+.1f}%)"
                )

            if winner["trend20"] > loser["trend20"]:
                reasons.append(
                    f"better 20D trend ({winner['trend20']:+.1f}% vs {loser['trend20']:+.1f}%)"
                )

            if winner["momentum"] > loser["momentum"]:
                reasons.append(
                    f"stronger momentum ({winner['momentum']:+.1f}% vs {loser['momentum']:+.1f}%)"
                )

            if winner["rsi"] < 70 <= loser["rsi"]:
                reasons.append(
                    f"healthier RSI ({winner['rsi']:.1f} vs {loser['rsi']:.1f})"
                )
            elif winner["rsi"] < loser["rsi"] and winner["rsi"] >= 30:
                reasons.append(
                    f"more balanced RSI ({winner['rsi']:.1f} vs {loser['rsi']:.1f})"
                )

            if winner["price_vs_sma"] > loser["price_vs_sma"]:
                reasons.append(
                    f"stronger SMA20 structure ({winner['price_vs_sma']:+.1f}% vs {loser['price_vs_sma']:+.1f}%)"
                )

            explanation = (
                "; ".join(reasons[:4])
                if reasons
                else "the overall signals are very close"
            )

            return (
                f"SentixAI live comparison: {a['symbol']} vs "
                f"{b['symbol']}.\n\n"
                f"{a['symbol']}: {a['decision']} | "
                f"Confidence {a['confidence']:.1f}% | "
                f"Technical {a['technical']:.0f}/100 | "
                f"Fundamental {a['fundamental']:.0f}/100 | "
                f"RSI {a['rsi']:.1f} | "
                f"Opportunity {a['opportunity']:.1f}/100.\n\n"
                f"{b['symbol']}: {b['decision']} | "
                f"Confidence {b['confidence']:.1f}% | "
                f"Technical {b['technical']:.0f}/100 | "
                f"Fundamental {b['fundamental']:.0f}/100 | "
                f"RSI {b['rsi']:.1f} | "
                f"Opportunity {b['opportunity']:.1f}/100.\n\n"
                f"SentixAI currently ranks {winner['symbol']} higher "
                f"by {gap:.1f} opportunity points.\n\n"
                f"Why: {winner['symbol']} has {explanation}. "
                f"Momentum: {a['symbol']} {a['momentum']:+.1f}% vs "
                f"{b['symbol']} {b['momentum']:+.1f}%. "
                f"SMA20: {a['symbol']} {a['price_vs_sma']:+.1f}% vs "
                f"{b['symbol']} {b['price_vs_sma']:+.1f}%. "
                f"Both stocks currently carry a {a['decision']} / {b['decision']} signal, "
                f"so the comparison identifies the stronger setup rather than "
                f"generating a new recommendation."
            )

        except Exception as e:
            return (
                f"I can compare {symbol} with {other_symbol}, "
                f"but the second live market dataset could not be "
                f"loaded right now: {type(e).__name__}."
            )

    # ---------------------------------------------------------
    # BUY / SELL / SHOULD I BUY QUESTIONS
    # ---------------------------------------------------------

    buy_question = any(word in q for word in [
        "should i buy",
        "buy this",
        "buy now",
        "good buy",
        "worth buying",
        "enter",
        "entry",
    ])

    sell_question = any(word in q for word in [
        "should i sell",
        "sell this",
        "sell now",
    ])

    if buy_question or sell_question:

        if decision == "BUY":
            stance = (
                f"SentixAI currently has a BUY signal for {symbol} "
                f"with {confidence:.1f}% confidence."
            )
        elif decision == "SELL":
            stance = (
                f"SentixAI currently has a SELL signal for {symbol} "
                f"with {confidence:.1f}% confidence."
            )
        else:
            stance = (
                f"SentixAI currently recommends HOLD for {symbol}. "
                f"Confidence is {confidence:.1f}%, below the "
                f"{buy_threshold:.1f}% BUY threshold."
            )

        reasons = []

        if technical >= 65:
            reasons.append(
                f"technical structure is strong at {technical:.0f}/100"
            )
        elif technical < 40:
            reasons.append(
                f"technical structure is weak at {technical:.0f}/100"
            )
        else:
            reasons.append(
                f"technical conditions are mixed at {technical:.0f}/100"
            )

        if fundamental >= 65:
            reasons.append(
                f"fundamentals are supportive at {fundamental:.0f}/100"
            )
        elif fundamental < 40:
            reasons.append(
                f"fundamentals are weak at {fundamental:.0f}/100"
            )
        else:
            reasons.append(
                f"fundamentals are mixed at {fundamental:.0f}/100"
            )

        if rsi >= 70:
            reasons.append(
                f"RSI is elevated at {rsi:.1f}"
            )
        elif rsi <= 35:
            reasons.append(
                f"RSI is low at {rsi:.1f}"
            )
        else:
            reasons.append(
                f"RSI is {rsi:.1f}"
            )

        return (
            f"{stance}\n\n"
            f"Why: {', '.join(reasons)}.\n\n"
            f"Current price: ${price:,.2f}\n"
            f"24H move: {change:+.2f}%\n"
            f"Opportunity score: {opportunity:.1f}/100\n"
            f"BUY gap: {confidence_gap:.1f} points.\n\n"
            f"This is SentixAI's market signal, not a guarantee "
            f"of future performance."
        )

    # ---------------------------------------------------------
    # WHY IS THIS SIGNAL?
    # ---------------------------------------------------------

    if (
        "why" in q
        and any(x in q for x in [
            "hold",
            "buy",
            "sell",
            "signal",
            "decision"
        ])
    ):
        reasons = []

        if technical >= 65:
            reasons.append(
                f"strong technical conditions ({technical:.0f}/100)"
            )
        elif technical < 40:
            reasons.append(
                f"weak technical conditions ({technical:.0f}/100)"
            )
        else:
            reasons.append(
                f"mixed technical conditions ({technical:.0f}/100)"
            )

        if fundamental >= 65:
            reasons.append(
                f"supportive fundamentals ({fundamental:.0f}/100)"
            )
        elif fundamental < 40:
            reasons.append(
                f"weak fundamentals ({fundamental:.0f}/100)"
            )
        else:
            reasons.append(
                f"mixed fundamentals ({fundamental:.0f}/100)"
            )

        if trend5 > 0 and trend20 > 0:
            reasons.append(
                "positive 5D and 20D trend alignment"
            )
        elif trend5 < 0 and trend20 < 0:
            reasons.append(
                "negative 5D and 20D trend alignment"
            )
        else:
            reasons.append(
                "mixed short-term and broader trend signals"
            )

        if rsi >= 70:
            reasons.append(
                f"elevated RSI ({rsi:.1f})"
            )
        elif 50 <= rsi < 70:
            reasons.append(
                f"constructive RSI ({rsi:.1f})"
            )
        else:
            reasons.append(
                f"weaker RSI ({rsi:.1f})"
            )

        return (
            f"{symbol} is currently {decision} with "
            f"{confidence:.1f}% confidence.\n\n"
            f"The signal is based on {', '.join(reasons)}.\n\n"
            f"BUY threshold: {buy_threshold:.1f}%\n"
            f"Current opportunity: {opportunity:.1f}/100\n"
            f"BUY gap: {confidence_gap:.1f} points."
        )

    # ---------------------------------------------------------
    # RSI
    # ---------------------------------------------------------

    if any(x in q for x in [
        "rsi",
        "overbought",
        "oversold"
    ]):
        if rsi >= 70:
            state = "overbought territory"
        elif rsi <= 35:
            state = "oversold territory"
        elif rsi >= 50:
            state = "a constructive range"
        else:
            state = "a weaker range"

        return (
            f"{symbol} has an RSI-14 of {rsi:.1f}, "
            f"currently in {state}.\n\n"
            f"SentixAI does not use RSI alone. It combines RSI "
            f"with momentum, multi-period trends, SMA20, "
            f"fundamentals and other market factors."
        )

    # ---------------------------------------------------------
    # TREND / MOMENTUM
    # ---------------------------------------------------------

    if any(x in q for x in [
        "trend",
        "momentum",
        "direction",
        "moving"
    ]):
        return (
            f"{symbol} is trading at ${price:,.2f}.\n\n"
            f"24H move: {change:+.2f}%\n"
            f"Momentum: {momentum:+.2f}%\n"
            f"5D trend: {trend5:+.2f}%\n"
            f"10D trend: {trend10:+.2f}%\n"
            f"20D trend: {trend20:+.2f}%\n"
            f"Price vs SMA20: {price_vs_sma:+.2f}%"
        )

    # ---------------------------------------------------------
    # FUNDAMENTALS
    # ---------------------------------------------------------

    if any(x in q for x in [
        "fundamental",
        "valuation",
        "p/e",
        "pe",
        "financial"
    ]):
        return (
            f"{symbol}'s SentixAI fundamental score is "
            f"{fundamental:.0f}/100.\n\n"
            f"Technical score: {technical:.0f}/100\n"
            f"Fundamental score: {fundamental:.0f}/100\n"
            f"Confidence: {confidence:.1f}%\n"
            f"Signal: {decision}\n\n"
            f"The fundamental score is combined with technical "
            f"market structure to produce the final signal."
        )

    # ---------------------------------------------------------
    # PRICE
    # ---------------------------------------------------------

    if any(x in q for x in [
        "price",
        "trading at",
        "quote"
    ]):
        return (
            f"{symbol} is currently trading at "
            f"${price:,.2f} on Bitget Reality.\n\n"
            f"24H move: {change:+.2f}%\n"
            f"Signal: {decision}\n"
            f"Confidence: {confidence:.1f}%"
        )

    # ---------------------------------------------------------
    # DEFAULT SUMMARY
    # ---------------------------------------------------------

    return (
        f"Here's the current SentixAI view on {symbol}:\n\n"
        f"Price: ${price:,.2f}\n"
        f"24H move: {change:+.2f}%\n"
        f"Signal: {decision}\n"
        f"Confidence: {confidence:.1f}%\n"
        f"Technical: {technical:.0f}/100\n"
        f"Fundamental: {fundamental:.0f}/100\n"
        f"RSI: {rsi:.1f}\n"
        f"Opportunity: {opportunity:.1f}/100\n\n"
        f"You can ask me why the signal is what it is, "
        f"whether the stock is a good buy, about RSI or trends, "
        f"or compare it with another stock."
    )

class DashboardHandler(BaseHTTPRequestHandler):

    def send_json(self, payload):

        body = json.dumps(
            payload,
            separators=(",", ":")
        ).encode()

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self):

        parsed = urlparse(self.path)

        if parsed.path == "/api/stocks":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]

            try:
                results = search_stock_universe(query, limit=12)
                self.send_json({
                    "status": "ok",
                    "count": len(results),
                    "total": len(get_stock_universe()),
                    "stocks": results,
                })
            except Exception as e:
                self.send_json({
                    "status": "error",
                    "message": f"{type(e).__name__}: {e}",
                })

            return

        if parsed.path == "/api/data":

            params = parse_qs(parsed.query)

            symbol = params.get("symbol", ["AMZN"])[0]

            try:

                self.send_json(
                    get_dashboard_data(symbol)
                )

            except Exception as e:

                self.send_json({
                    "status": "error",
                    "message":
                        f"{type(e).__name__}: {e}"
                })

            return

        if parsed.path == "/api/chat":

            params = parse_qs(parsed.query)

            symbol = params.get("symbol", ["AMZN"])[0].upper()
            question = params.get("question", [""])[0].strip()

            if not question:

                self.send_json({
                    "status": "error",
                    "message": "Please enter a question."
                })

                return

            try:

                market_response = get_dashboard_data(symbol)

                market = market_response.get(
                    "selected",
                    market_response
                )

                answer = sentix_chat_answer(
                    symbol,
                    question,
                    market
                )

                self.send_json({
                    "status": "ok",
                    "symbol": symbol,
                    "question": question,
                    "answer": answer
                })

            except Exception as e:

                self.send_json({
                    "status": "error",
                    "message":
                        f"{type(e).__name__}: {e}"
                })

            return

        if parsed.path == "/":

            body = HTML.encode()

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )

            self.send_header(
                "Content-Length",
                str(len(body))
            )

            self.end_headers()

            self.wfile.write(body)

            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        print("[DASHBOARD]", format % args)


if __name__ == "__main__":

    print("=" * 60)
    print("SENTIXAI DASHBOARD")
    print("=" * 60)
    print("Data source : Bitget Reality US Stocks")
    print("Address     : http://0.0.0.0:8080")
    print("=" * 60)

    server = ThreadingHTTPServer(
        (HOST, PORT),
        DashboardHandler
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()
