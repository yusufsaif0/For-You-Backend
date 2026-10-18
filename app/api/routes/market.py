from fastapi import APIRouter

from app.schemas.market import MarketQuotesResponse
from app.services.market_service import get_market_quotes

router = APIRouter(prefix="/market", tags=["Market data"])


@router.get("/quotes", response_model=MarketQuotesResponse)
async def market_quotes() -> MarketQuotesResponse:
    return await get_market_quotes()
