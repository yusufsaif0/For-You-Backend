import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from app.schemas.market import MarketQuote, MarketQuotesResponse

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
CACHE_SECONDS = 300
TROY_OUNCE_GRAMS = 31.1034768

_cached_quotes: MarketQuotesResponse | None = None
_cache_time = 0.0
_cache_lock = asyncio.Lock()


async def _fetch_chart(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    try:
        response = await client.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={"range": "1d", "interval": "1d"},
        )
        response.raise_for_status()
        body = response.json()
        result = body.get("chart", {}).get("result")
        if not result or not isinstance(result[0], dict):
            raise ValueError("Yahoo Finance returned no chart data.")
        return result[0]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as error:
        logger.warning("Unable to fetch Yahoo Finance market data for %s: %s", symbol, error)
        raise HTTPException(
            status_code=502,
            detail="Market data is temporarily unavailable. Please retry shortly.",
        ) from error


def _market_values(chart: dict[str, Any]) -> tuple[float, float, datetime]:
    meta = chart.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Missing market quote metadata.")
    price = meta.get("regularMarketPrice")
    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    timestamp = meta.get("regularMarketTime")
    if not isinstance(price, (float, int)) or price <= 0:
        raise ValueError("Missing or invalid market price.")
    if not isinstance(previous_close, (float, int)) or previous_close <= 0:
        raise ValueError("Missing or invalid previous close.")
    if not isinstance(timestamp, (float, int)) or timestamp <= 0:
        raise ValueError("Missing or invalid market timestamp.")
    change = meta.get("regularMarketChangePercent")
    if not isinstance(change, (float, int)):
        change = (price / previous_close - 1) * 100
    return float(price), float(change), datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _quote(symbol: str, chart: dict[str, Any], *, factor: float = 1.0, unit: str) -> MarketQuote:
    price, change_percent, updated_at = _market_values(chart)
    return MarketQuote(
        symbol=symbol,
        price=price * factor,
        change_percent=change_percent,
        unit=unit,
        market_symbol=str(chart.get("meta", {}).get("symbol", "unknown")),
        updated_at=updated_at,
    )


async def _fetch_quotes() -> MarketQuotesResponse:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0, connect=5.0),
        headers={"User-Agent": "Mozilla/5.0 DailyLife/1.0"},
    ) as client:
        nifty, gold, silver, usd_inr = await asyncio.gather(
            _fetch_chart(client, "^NSEI"),
            _fetch_chart(client, "GC=F"),
            _fetch_chart(client, "SI=F"),
            _fetch_chart(client, "INR=X"),
        )

    try:
        exchange_rate, _, _ = _market_values(usd_inr)
        if nifty.get("meta", {}).get("symbol") != "^NSEI" or nifty.get("meta", {}).get("currency") != "INR":
            raise ValueError("The NIFTY 50 index quote is unavailable.")
        if (
            gold.get("meta", {}).get("symbol") != "GC=F"
            or silver.get("meta", {}).get("symbol") != "SI=F"
            or gold.get("meta", {}).get("currency") != "USD"
            or silver.get("meta", {}).get("currency") != "USD"
        ):
            raise ValueError("The COMEX futures quote currency or symbol is not supported.")
        if usd_inr.get("meta", {}).get("symbol") != "INR=X":
            raise ValueError("The USD/INR exchange quote is unavailable.")

        return MarketQuotesResponse(
            quotes=[
                _quote("NIFTY 50", nifty, unit="points"),
                _quote(
                    "GOLD / 10G",
                    gold,
                    factor=exchange_rate * 10 / TROY_OUNCE_GRAMS,
                    unit="estimated INR / 10 g · COMEX futures",
                ),
                _quote(
                    "SILVER / KG",
                    silver,
                    factor=exchange_rate * 1000 / TROY_OUNCE_GRAMS,
                    unit="estimated INR / kg · COMEX futures",
                ),
            ],
            fetched_at=datetime.now(timezone.utc),
        )
    except (ValueError, TypeError, AttributeError) as error:
        logger.warning("Yahoo Finance returned invalid market quotes: %s", error)
        raise HTTPException(
            status_code=502,
            detail="Market data is temporarily unavailable. Please retry shortly.",
        ) from error


async def get_market_quotes() -> MarketQuotesResponse:
    global _cached_quotes, _cache_time

    if _cached_quotes is not None and time.monotonic() - _cache_time < CACHE_SECONDS:
        return _cached_quotes

    async with _cache_lock:
        if _cached_quotes is not None and time.monotonic() - _cache_time < CACHE_SECONDS:
            return _cached_quotes
        try:
            quotes = await _fetch_quotes()
        except HTTPException:
            if _cached_quotes is not None:
                logger.warning("Returning cached market quotes marked stale after upstream failure.")
                return _cached_quotes.model_copy(update={"is_stale": True})
            raise
        _cached_quotes = quotes
        _cache_time = time.monotonic()
        return quotes
