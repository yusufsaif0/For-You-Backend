from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Literal["NIFTY 50", "GOLD / 10G", "SILVER / KG"]
    price: float = Field(gt=0)
    change_percent: float
    currency: Literal["INR"] = "INR"
    unit: str
    market_symbol: str
    updated_at: datetime
    source: Literal["Yahoo Finance"] = "Yahoo Finance"


class MarketQuotesResponse(BaseModel):
    quotes: list[MarketQuote] = Field(min_length=3, max_length=3)
    fetched_at: datetime
    is_stale: bool = False
