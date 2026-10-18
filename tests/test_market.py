import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes import market as market_route
from app.main import app
from app.schemas.market import MarketQuote, MarketQuotesResponse
from app.services import market_service


def chart(symbol, price, previous, currency, timestamp=1792144800):
    return {
        "meta": {
            "symbol": symbol,
            "currency": currency,
            "regularMarketPrice": price,
            "chartPreviousClose": previous,
            "regularMarketTime": timestamp,
        }
    }


class MarketQuoteTests(unittest.TestCase):
    def test_quote_conversion_preserves_market_change_and_timestamp(self):
        gold = chart("GC=F", 3000, 2900, "USD")
        quote = market_service._quote(
            "GOLD / 10G",
            gold,
            factor=90 * 10 / market_service.TROY_OUNCE_GRAMS,
            unit="estimated INR / 10 g · COMEX futures",
        )
        self.assertAlmostEqual(quote.price, 90 * 3000 * 10 / market_service.TROY_OUNCE_GRAMS)
        self.assertAlmostEqual(quote.change_percent, (3000 / 2900 - 1) * 100)
        self.assertEqual(quote.updated_at, datetime.fromtimestamp(1792144800, tz=timezone.utc))

    def test_missing_quote_price_is_rejected(self):
        with self.assertRaises(ValueError):
            market_service._market_values({"meta": {"regularMarketPrice": None}})


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, **_):
        self.responses = {
            "^NSEI": chart("^NSEI", 25000, 24900, "INR"),
            "GC=F": chart("GC=F", 3000, 2900, "USD"),
            "SI=F": chart("SI=F", 30, 29, "USD"),
            "INR=X": chart("INR=X", 90, 89, "INR"),
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, **_):
        symbol = url.split("/")[-1]
        return FakeResponse({"chart": {"result": [self.responses[symbol]]}})


class MarketFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_nifty_metals_and_currency_then_converts_quotes(self):
        with patch("app.services.market_service.httpx.AsyncClient", FakeAsyncClient):
            result = await market_service._fetch_quotes()
        self.assertEqual([quote.symbol for quote in result.quotes], ["NIFTY 50", "GOLD / 10G", "SILVER / KG"])
        self.assertEqual(result.quotes[0].price, 25000)
        self.assertAlmostEqual(result.quotes[1].price, 90 * 3000 * 10 / market_service.TROY_OUNCE_GRAMS)
        self.assertAlmostEqual(result.quotes[2].price, 90 * 30 * 1000 / market_service.TROY_OUNCE_GRAMS)
        self.assertFalse(result.is_stale)

    async def test_returns_marked_stale_cache_after_provider_failure(self):
        cached = MarketQuotesResponse(
            quotes=[MarketQuote(
                symbol="NIFTY 50", price=25000, change_percent=0.4, unit="points",
                market_symbol="^NSEI", updated_at=datetime.now(timezone.utc),
            ), MarketQuote(
                symbol="GOLD / 10G", price=80000, change_percent=0.3, unit="estimated INR / 10 g · COMEX futures",
                market_symbol="GC=F", updated_at=datetime.now(timezone.utc),
            ), MarketQuote(
                symbol="SILVER / KG", price=90000, change_percent=0.2, unit="estimated INR / kg · COMEX futures",
                market_symbol="SI=F", updated_at=datetime.now(timezone.utc),
            )],
            fetched_at=datetime.now(timezone.utc),
        )
        with patch.object(market_service, "_cached_quotes", cached), \
             patch.object(market_service, "_cache_time", 0), \
             patch.object(market_service, "_fetch_quotes", new=AsyncMock(side_effect=HTTPException(status_code=502))):
            response = await market_service.get_market_quotes()
        self.assertTrue(response.is_stale)
        self.assertEqual(response.quotes[0].price, 25000)


class MarketRouteTests(unittest.TestCase):
    def test_market_endpoint_returns_quote_payload(self):
        result = MarketQuotesResponse(
            quotes=[MarketQuote(
                symbol="NIFTY 50", price=25000, change_percent=0.4, unit="points",
                market_symbol="^NSEI", updated_at=datetime.now(timezone.utc),
            ), MarketQuote(
                symbol="GOLD / 10G", price=80000, change_percent=0.3,
                unit="estimated INR / 10 g · COMEX futures", market_symbol="GC=F",
                updated_at=datetime.now(timezone.utc),
            ), MarketQuote(
                symbol="SILVER / KG", price=90000, change_percent=0.2,
                unit="estimated INR / kg · COMEX futures", market_symbol="SI=F",
                updated_at=datetime.now(timezone.utc),
            )],
            fetched_at=datetime.now(timezone.utc),
        )
        with patch.object(market_route, "get_market_quotes", new=AsyncMock(return_value=result)):
            response = TestClient(app).get("/api/market/quotes")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["quotes"][0]["symbol"], "NIFTY 50")
