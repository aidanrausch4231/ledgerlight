"""The only price network boundary. Fakes require explicit environment opt-in.

Only CoinGecko coin ids/symbols and stock tickers leave the machine; never
quantities, balances or account names. Errors are scrubbed before display.
"""

import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

COINGECKO = "https://api.coingecko.com/api/v3"
# Stock quotes are isolated here so the source can be swapped without callers changing.
# Yahoo's chart endpoint needs no key; the v7 batch quote endpoint returns 401.
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
# Exactly "Mozilla/5.0": live checks got 200, while a full Chrome UA got HTTP 429.
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT = 10
SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,19}$")
TICKER = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")
COIN_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{0,99}$")


class PriceError(ValueError):
    """Safe-to-display price source failure; never includes response bodies."""


def check_symbol(value):
    if not isinstance(value, str) or not SYMBOL.match(value.strip()):
        raise ValueError("Symbol must be 1-20 letters, digits, '.' or '-'")
    return value.strip().upper()


def check_ticker(value):
    """Stock ticker: uppercased, only [A-Z0-9.-^=], 1-15 characters."""
    ticker = value.strip().upper() if isinstance(value, str) else ""
    if not TICKER.match(ticker):
        raise ValueError("Ticker must be 1-15 letters, digits, '.', '-', '^' or '='")
    return ticker


def _iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def check_coin_id(value):
    if not isinstance(value, str) or not COIN_ID.match(value.strip()):
        raise ValueError("Coin id must be a lowercase CoinGecko id such as bitcoin")
    return value.strip()


def fake_enabled():
    return os.environ.get("LEDGERLIGHT_FAKE_PRICES") == "1"


class PriceClient:
    """CoinGecko (free public API) and Yahoo chart quotes, both without keys."""

    def _request(self, url, params, headers=None):
        # One retry for transient transport failures only; never log bodies.
        for attempt in range(2):
            try:
                response = httpx.get(
                    url, params=params, headers=headers, timeout=TIMEOUT
                )
                response.raise_for_status()
                return response
            except httpx.TransportError as exc:
                if attempt:
                    raise PriceError("Price source unreachable") from exc
            except httpx.HTTPStatusError as exc:
                raise PriceError(
                    f"Price source returned HTTP {exc.response.status_code}"
                ) from exc
            except httpx.HTTPError as exc:
                raise PriceError("Price source request failed") from exc

    def _json(self, url, params, headers=None):
        try:
            return self._request(url, params, headers).json()
        except ValueError as exc:
            if isinstance(exc, PriceError):
                raise
            raise PriceError("Price source returned invalid data") from exc

    def search_coin(self, symbol):
        symbol = check_symbol(symbol)
        body = self._json(f"{COINGECKO}/search", {"query": symbol})
        try:
            return [
                {
                    "id": str(coin["id"]),
                    "symbol": str(coin["symbol"]),
                    "name": str(coin["name"]),
                    "market_cap_rank": coin.get("market_cap_rank"),
                }
                for coin in body.get("coins", [])
                if str(coin.get("symbol", "")).upper() == symbol
            ]
        except (AttributeError, KeyError, TypeError) as exc:
            raise PriceError("Price source returned invalid data") from exc

    def crypto_prices(self, ids):
        ids = sorted({check_coin_id(id) for id in ids})
        if not ids:
            return {}
        result = {}
        for start in range(0, len(ids), 100):
            body = self._json(
                f"{COINGECKO}/simple/price",
                {
                    "ids": ",".join(ids[start : start + 100]),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
            )
            try:
                for id, value in body.items():
                    if id in ids and value.get("usd") is not None:
                        change = value.get("usd_24h_change")
                        result[id] = {
                            "usd": float(value["usd"]),
                            "usd_24h_change": None if change is None else float(change),
                        }
            except (AttributeError, TypeError, ValueError) as exc:
                raise PriceError("Price source returned invalid data") from exc
        return result

    def stock_quote(self, ticker):
        """One Yahoo chart request; only the ticker is in the URL."""
        ticker = check_ticker(ticker)
        body = self._json(
            f"{YAHOO_CHART}/{quote(ticker, safe='')}",
            {"range": "1d", "interval": "1d"},
            YAHOO_HEADERS,
        )
        try:
            chart = body["chart"]
            if chart.get("error") or not chart.get("result"):
                raise PriceError(f"No quote returned for {ticker}")
            meta = chart["result"][0]["meta"]
            price = float(meta["regularMarketPrice"])
            previous = meta.get("chartPreviousClose")
            timestamp = meta.get("regularMarketTime")
            return {
                "price": price,
                "as_of": _iso(int(timestamp)) if timestamp is not None else None,
                "change_24h": (price - float(previous)) / float(previous) * 100
                if previous
                else None,
            }
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, PriceError):
                raise
            raise PriceError("Price source returned invalid data") from exc

    def stock_prices(self, tickers):
        """Sequential per-ticker requests; a failed ticker gets {"error": ...}.

        Other tickers still update. Errors are scrubbed PriceError messages.
        """
        result = {}
        for ticker in sorted({check_ticker(t) for t in tickers}):
            try:
                result[ticker] = self.stock_quote(ticker)
            except PriceError as exc:
                result[ticker] = {"error": str(exc)}
        return result


class FakePriceClient:
    """Deterministic synthetic prices; selected only by LEDGERLIGHT_FAKE_PRICES=1."""

    COINS = [
        {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1},
        # Ambiguous synthetic symbol: lower rank must never win.
        {
            "id": "synthetic-bitcoin-clone",
            "symbol": "btc",
            "name": "Synthetic Bitcoin Clone",
            "market_cap_rank": 4200,
        },
        {"id": "ethereum", "symbol": "eth", "name": "Ethereum", "market_cap_rank": 2},
        {
            "id": "synthetic-unranked",
            "symbol": "eth",
            "name": "Synthetic Unranked",
            "market_cap_rank": None,
        },
    ]
    CRYPTO = {
        "bitcoin": {"usd": 60000.0, "usd_24h_change": 1.5},
        "synthetic-bitcoin-clone": {"usd": 0.5, "usd_24h_change": -10.0},
        "ethereum": {"usd": 3000.0, "usd_24h_change": -2.0},
    }
    STOCKS = {"AAPL": 200.0, "MSFT": 400.0, "VTI": 250.0}
    STOCK_CHANGE = {"AAPL": 1.0, "MSFT": -0.5, "VTI": 0.0}

    def search_coin(self, symbol):
        symbol = check_symbol(symbol)
        return [dict(c) for c in self.COINS if c["symbol"].upper() == symbol]

    def crypto_prices(self, ids):
        ids = {check_coin_id(id) for id in ids}
        return {id: dict(v) for id, v in self.CRYPTO.items() if id in ids}

    def stock_prices(self, tickers):
        tickers = {check_ticker(t) for t in tickers}
        return {
            t: {
                "price": p,
                "as_of": "2026-03-13T20:00:00Z",
                "change_24h": self.STOCK_CHANGE.get(t),
            }
            for t, p in self.STOCKS.items()
            if t in tickers
        }


def get_client():
    return FakePriceClient() if fake_enabled() else PriceClient()


def choose_coin(candidates):
    """Highest market-cap rank (lowest number) wins; unranked coins come last."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            c["market_cap_rank"] is None,
            c["market_cap_rank"] or 0,
            c["id"],
        ),
    )
