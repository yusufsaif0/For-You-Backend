from app.api.routes.schedules import router as schedules_router
from app.api.routes.life_items import router as life_items_router
from app.api.routes.food_analysis import router as food_analysis_router
from app.api.routes.market import router as market_router
from app.api.routes.document_ocr import router as document_ocr_router
from app.api.routes.family import router as family_router

__all__ = ["schedules_router", "life_items_router", "food_analysis_router", "market_router", "document_ocr_router", "family_router"]
