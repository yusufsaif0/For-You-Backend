import base64
import binascii
import json
import logging

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.food_analysis import FoodAnalysisResult, FoodImageRequest

MAX_IMAGE_BYTES = 6 * 1024 * 1024
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
logger = logging.getLogger(__name__)


def _decode_image(request: FoodImageRequest) -> bytes:
    try:
        image = base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail="The photo data is invalid.") from error
    if not image or len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Choose a photo smaller than 6 MB after resizing.")
    return image


async def analyze_food_image(request: FoodImageRequest) -> FoodAnalysisResult:
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="Food photo analysis is not configured. Add GEMINI_API_KEY to the backend .env file.",
        )

    _decode_image(request)
    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": request.mime_type,
                        "data": request.image_base64,
                    }
                },
                {
                    "text": (
                        "Determine whether the image clearly contains prepared food or drink. "
                        "If it does not, return is_food=false and an empty foods array. "
                        "If it does, identify each visible food and estimate its edible portion in grams, "
                        "calories, sugar grams, and fat grams for that portion. Use reasonable food-reference "
                        "estimates, not medical advice. Do not infer hidden ingredients. Return no more than "
                        "12 food items. Return only the requested JSON fields."
                    )
                },
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "is_food": {"type": "BOOLEAN"},
                    "foods": {
                        "type": "ARRAY",
                        "maxItems": 12,
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "portion_g": {"type": "NUMBER"},
                                "calories": {"type": "INTEGER"},
                                "sugar_g": {"type": "NUMBER"},
                                "fat_g": {"type": "NUMBER"},
                            },
                            "required": ["name", "portion_g", "calories", "sugar_g", "fat_g"],
                        },
                    },
                },
                "required": ["is_food", "foods"],
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            response = await client.post(
                GEMINI_API_URL.format(model=settings.gemini_model),
                headers={"x-goog-api-key": settings.gemini_api_key},
                json=payload,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Food analysis timed out. Please try again.") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Could not reach the food analysis service.") from error

    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="The Gemini free-tier limit was reached. Please try again later.")
    if response.is_error:
        if response.status_code in (400, 403, 404):
            try:
                provider_message = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                provider_message = ""
            if not isinstance(provider_message, str):
                provider_message = ""
            if settings.gemini_api_key:
                provider_message = provider_message.replace(settings.gemini_api_key, "[redacted]")
            if provider_message:
                logger.warning("Gemini rejected food analysis request: HTTP %s: %s", response.status_code, provider_message[:500])
                raise HTTPException(
                    status_code=502,
                    detail=f"Gemini could not process the request: {provider_message[:300]}",
                )
        raise HTTPException(status_code=502, detail="The food analysis service could not process this photo.")

    try:
        response_body = response.json()
        text = "".join(
            part["text"]
            for candidate in response_body["candidates"]
            for part in candidate["content"]["parts"]
            if isinstance(part.get("text"), str)
        )
        result = FoodAnalysisResult.model_validate(json.loads(text))
    except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
        raise HTTPException(status_code=502, detail="The food analysis service returned an invalid result.") from error
    return result
