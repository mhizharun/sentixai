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

    return {
        "symbol": symbol,
        "price": data.get("price", 0),
        "change_24h": data.get("change_24h", data.get("change_percent", 0)),
        "decision": analysis.get("decision", "HOLD"),
        "confidence": analysis.get("confidence", 0),
        "buy_threshold": float(MIN_CONFIDENCE) if "MIN_CONFIDENCE" in globals() else 70.0,
        "confidence_gap": max(
            0.0,
            (float(MIN_CONFIDENCE) if "MIN_CONFIDENCE" in globals() else 70.0)
            - float(analysis.get("confidence", 0))
        ),
        "signal_strength": thesis.get("signal_strength", ""),
        "technical": analysis.get("technical_score", 0),
        "fundamental": analysis.get("fundamental_score", 0),
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
        "historical": normalize_history(data.get("historical", [])),
        "thesis": thesis,
        "source": "Bitget Reality US Stocks",
    }


_DASHBOARD_CACHE = {}
_DASHBOARD_CACHE_TIME = {}
_DASHBOARD_CACHE_LOCK = threading.Lock()
_DASHBOARD_CACHE_SECONDS = 20


def get_dashboard_data(symbol="AMZN"):
    symbol = symbol.upper()

    if symbol not in SYMBOLS:
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
    font-size: 13px;
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
</style>
</head>

<body>

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
                    AI INVESTMENT THESIS
                </div>

                <div class="ai" id="thesis">
                    Loading...
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

    document.getElementById("bitgetSymbol").textContent =
        "Bitget symbol: " + s.bitget_symbol;

    const thesis =
        s.thesis && s.thesis.thesis
            ? s.thesis.thesis
            : [];

    document.getElementById("thesis").innerHTML =
        thesis.map(x => "<p>• " + x + "</p>").join("");

    const container =
        document.getElementById("stocks");

    container.innerHTML = "";

    data.stocks.forEach(stock => {

        const row =
            document.createElement("div");

        row.className = "stock-row";

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


function selectSymbol(symbol) {

    currentSymbol = symbol;

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

</script>

</body>
</html>
'''


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
