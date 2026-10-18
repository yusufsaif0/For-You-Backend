from fastapi import APIRouter, Depends

from app.core.auth import require_user
from app.schemas.food_analysis import FoodAnalysisResult, FoodImageRequest
from app.services.food_analyzer import analyze_food_image

router = APIRouter(prefix="/food", tags=["Food photo analysis"])


@router.post("/analyze", response_model=FoodAnalysisResult)
async def analyze_food(request: FoodImageRequest, _user: dict = Depends(require_user)) -> FoodAnalysisResult:
    return await analyze_food_image(request)
