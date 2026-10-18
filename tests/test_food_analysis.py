import base64
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.auth import require_user
from app.main import app
from app.schemas.food_analysis import FoodAnalysisResult, FoodImageRequest
from app.services.food_analyzer import _decode_image, analyze_food_image


class FoodAnalysisSchemaTests(unittest.TestCase):
    def test_image_request_restricts_mime_and_base64(self):
        with self.assertRaises(ValidationError):
            FoodImageRequest(mime_type="image/gif", image_base64="aW1hZ2U=")
        with self.assertRaises(ValidationError):
            FoodImageRequest(mime_type="image/jpeg", image_base64="")
        with self.assertRaises(HTTPException) as error:
            _decode_image(FoodImageRequest(mime_type="image/jpeg", image_base64="not base64!"))
        self.assertEqual(error.exception.status_code, 422)

    def test_food_classification_requires_matching_food_list(self):
        valid = FoodAnalysisResult.model_validate({
            "is_food": True,
            "foods": [{
                "name": "Rice",
                "portion_g": 150,
                "calories": 195,
                "sugar_g": 0.1,
                "fat_g": 0.4,
            }],
        })
        self.assertEqual(valid.foods[0].calories, 195)
        with self.assertRaises(ValidationError):
            FoodAnalysisResult.model_validate({"is_food": False, "foods": [{"name": "Rice"}]})


class FakeResponse:
    status_code = 200
    is_error = False

    @staticmethod
    def json():
        return {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"is_food":true,"foods":[{"name":"Rice","portion_g":150,"calories":195,"sugar_g":0.1,"fat_g":0.4}]}'
                    }]
                }
            }]
        }


class FakeAsyncClient:
    def __init__(self, **_):
        self.headers = None
        self.json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, _url, *, headers, json):
        self.headers = headers
        self.json = json
        return FakeResponse()


class FoodAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_fails_without_contacting_provider(self):
        request = FoodImageRequest(mime_type="image/jpeg", image_base64=base64.b64encode(b"photo").decode())
        with patch.object(settings, "gemini_api_key", ""), patch("app.services.food_analyzer.httpx.AsyncClient") as client:
            with self.assertRaises(HTTPException) as error:
                await analyze_food_image(request)
        self.assertEqual(error.exception.status_code, 503)
        client.assert_not_called()

    async def test_valid_image_is_sent_to_gemini_and_response_is_validated(self):
        request = FoodImageRequest(mime_type="image/jpeg", image_base64=base64.b64encode(b"photo").decode())
        client = FakeAsyncClient()
        with patch.object(settings, "gemini_api_key", "test-key"), \
             patch.object(settings, "gemini_model", "test-model"), \
             patch("app.services.food_analyzer.httpx.AsyncClient", return_value=client):
            result = await analyze_food_image(request)
        self.assertTrue(result.is_food)
        self.assertEqual(result.foods[0].name, "Rice")
        self.assertEqual(client.headers, {"x-goog-api-key": "test-key"})
        self.assertEqual(client.json["contents"][0]["parts"][0]["inline_data"]["data"], request.image_base64)


class FoodAnalysisRouteTests(unittest.TestCase):
    def test_analysis_route_returns_validated_food_nutrition(self):
        result = FoodAnalysisResult.model_validate({
            "is_food": True,
            "foods": [{
                "name": "Rice",
                "portion_g": 150,
                "calories": 195,
                "sugar_g": 0.1,
                "fat_g": 0.4,
            }],
        })
        app.dependency_overrides[require_user] = lambda: {"uid": "test-user", "email": "test@example.com"}
        try:
            with patch("app.api.routes.food_analysis.analyze_food_image", new=AsyncMock(return_value=result)):
                response = TestClient(app).post("/api/food/analyze", json={
                    "mime_type": "image/png",
                    "image_base64": base64.b64encode(b"test image").decode(),
                })
        finally:
            app.dependency_overrides.pop(require_user, None)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["foods"][0]["calories"], 195)
        self.assertEqual(response.json()["foods"][0]["sugar_g"], 0.1)
