import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone


BASE_URL = "https://api.bitget.com"


class BitgetMarket:
    """
    Public Bitget US-equity market data.

    Reality symbols:
        AAPL -> RAAPLUSDT
        TSLA -> RTSLAUSDT
        NVDA -> RNVDAUSDT
        MSFT -> RMSFTUSDT
        AMZN -> RAMZNUSDT
    """

    def __init__(self):
        self.base_url = BASE_URL

    @staticmethod
    def reality_symbol(symbol):
        symbol = symbol.upper().replace(".US", "").replace("/", "")
        return f"R{symbol}USDT"

    def request(self, path, params):
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SentixAI/1.0",
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode())

    def quote(self, symbol):
        """
        Get current Bitget US-stock quote.
        """
        rb = self.reality_symbol(symbol)

        data = self.request(
            "/api/v3/market/tickers",
            {
                "category": "SPOT",
                "symbol": rb,
            },
        )

        rows = data.get("data", [])

        if not rows:
            raise RuntimeError(f"No Bitget quote returned for {symbol}")

        row = rows[0]

        return {
            "symbol": symbol.upper(),
            "bitget_symbol": rb,
            "price": float(row["lastPrice"]),
            "open_24h": float(row["openPrice24h"]),
            "high_24h": float(row["highPrice24h"]),
            "low_24h": float(row["lowPrice24h"]),
            "bid": float(row["bid1Price"]),
            "ask": float(row["ask1Price"]),
            "bid_size": float(row["bid1Size"]),
            "ask_size": float(row["ask1Size"]),
            "change_24h": float(row["price24hPcnt"]) * 100,
            "volume_24h": float(row["volume24h"]),
            "turnover_24h": float(row["turnover24h"]),
            "timestamp": int(row["ts"]),
            "source": "Bitget",
        }

    def candles(self, symbol, interval="1D", limit=100):
        """
        Get historical Bitget Reality candles.
        """
        rb = self.reality_symbol(symbol)

        data = self.request(
            "/api/v3/market/candles",
            {
                "category": "SPOT",
                "symbol": rb,
                "interval": interval,
                "limit": limit,
            },
        )

        return {
            "symbol": symbol.upper(),
            "bitget_symbol": rb,
            "source": "Bitget",
            "data": data.get("data", []),
        }

    def company_overview(self, symbol):
        """Get Bitget Reality company overview."""
        code = symbol.upper().replace(".US", "").replace("/", "")
        data = self.request(
            "/api/v3/reality/market/company-overview",
            {"code": code},
        )
        return data.get("data", {})

    def valuation_indicators(self, symbol):
        """Get Bitget Reality valuation indicators."""
        code = symbol.upper().replace(".US", "").replace("/", "")
        data = self.request(
            "/api/v3/reality/market/valuation-indicators",
            {"code": code},
        )
        return data.get("data", {})

    def earnings_forecast(self, symbol):
        """Get Bitget Reality earnings forecast."""
        code = symbol.upper().replace(".US", "").replace("/", "")
        data = self.request(
            "/api/v3/reality/market/earnings-forecast",
            {"code": code},
        )
        return data.get("data", {})

    def market_state(self):
        """
        Bitget US market session state.
        """
        data = self.request(
            "/api/v3/reality/market/states",
            {}
        )

        return data.get("data", {})


def test():
    client = BitgetMarket()

    print("=" * 60)
    print("SENTIXAI — BITGET US STOCK MARKET")
    print("=" * 60)

    for symbol in ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]:
        try:
            quote = client.quote(symbol)

            print(
                f"{symbol:5} "
                f"${quote['price']:<10.2f} "
                f"24h: {quote['change_24h']:+.2f}%"
            )

        except Exception as e:
            print(f"{symbol:5} ERROR: {e}")

    print()
    print("Market state:")
    print(json.dumps(client.market_state(), indent=2))

    print()
    print("TSLA candles:")
    candles = client.candles("TSLA", "1D", 5)

    for candle in candles["data"]:
        print(candle)


if __name__ == "__main__":
    test()
