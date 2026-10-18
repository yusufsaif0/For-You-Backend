import base64
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import require_user
from app.core.config import settings
from app.main import app
from app.schemas.document_ocr import DocumentOCRRequest, DocumentOCRResult
from app.services.document_ocr import _decode_document, extract_document_fields


class DocumentOCRSchemaTests(unittest.TestCase):
    def test_only_supported_document_mime_types_are_accepted(self):
        with self.assertRaises(ValidationError):
            DocumentOCRRequest(mime_type="image/gif", file_base64="aW1hZ2U=")

    def test_pdf_signature_and_base64_are_validated(self):
        with self.assertRaises(HTTPException) as invalid_base64:
            _decode_document(DocumentOCRRequest(mime_type="image/jpeg", file_base64="not base64!"))
        self.assertEqual(invalid_base64.exception.status_code, 422)

        with self.assertRaises(HTTPException) as invalid_pdf:
            _decode_document(DocumentOCRRequest(
                mime_type="application/pdf",
                file_base64=base64.b64encode(b"not a PDF").decode(),
            ))
        self.assertEqual(invalid_pdf.exception.status_code, 422)

        with self.assertRaises(HTTPException) as invalid_image:
            _decode_document(DocumentOCRRequest(
                mime_type="image/png",
                file_base64=base64.b64encode(b"not a PNG").decode(),
            ))
        self.assertEqual(invalid_image.exception.status_code, 422)

    def test_document_fields_are_bounded(self):
        with self.assertRaises(ValidationError):
            DocumentOCRResult.model_validate({
                "document_type": "Aadhaar",
                "fields": [{"label": "ID", "value": "x" * 501}],
            })


class FakeResponse:
    status_code = 200
    is_error = False

    @staticmethod
    def json():
        return {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"document_type":"PAN Card","fields":[{"label":"PAN number","value":"ABCDE1234F"}]}'
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


class DocumentOCRServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_is_sent_to_gemini_and_response_is_validated(self):
        request = DocumentOCRRequest(
            mime_type="image/jpeg",
            file_base64=base64.b64encode(b"\xff\xd8\xffdocument").decode(),
        )
        client = FakeAsyncClient()
        with patch.object(settings, "gemini_api_key", "test-key"), \
             patch.object(settings, "gemini_model", "test-model"), \
             patch("app.services.document_ocr.httpx.AsyncClient", return_value=client):
            result = await extract_document_fields(request)
        self.assertEqual(result.document_type, "PAN Card")
        self.assertEqual(result.fields[0].value, "ABCDE1234F")
        self.assertEqual(client.headers, {"x-goog-api-key": "test-key"})
        self.assertEqual(client.json["contents"][0]["parts"][0]["inline_data"]["data"], request.file_base64)

    async def test_missing_gemini_key_fails_without_contacting_provider(self):
        request = DocumentOCRRequest(
            mime_type="image/jpeg",
            file_base64=base64.b64encode(b"document").decode(),
        )
        with patch.object(settings, "gemini_api_key", ""), \
             patch("app.services.document_ocr.httpx.AsyncClient") as client:
            with self.assertRaises(HTTPException) as error:
                await extract_document_fields(request)
        self.assertEqual(error.exception.status_code, 503)
        client.assert_not_called()


class DocumentOCRRouteTests(unittest.TestCase):
    def test_extraction_requires_authentication(self):
        response = TestClient(app).post("/api/documents/extract", json={
            "mime_type": "image/jpeg",
            "file_base64": base64.b64encode(b"document").decode(),
        })
        self.assertEqual(response.status_code, 401)

    def test_authenticated_extraction_returns_validated_fields(self):
        result = DocumentOCRResult.model_validate({
            "document_type": "PAN Card",
            "fields": [{"label": "PAN number", "value": "ABCDE1234F"}],
        })
        app.dependency_overrides[require_user] = lambda: {"uid": "test-user", "email": "test@example.com"}
        try:
            with patch("app.api.routes.document_ocr.extract_document_fields", new=AsyncMock(return_value=result)):
                response = TestClient(app).post("/api/documents/extract", json={
                    "mime_type": "image/png",
                    "file_base64": base64.b64encode(b"test image").decode(),
                })
        finally:
            app.dependency_overrides.pop(require_user, None)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["fields"][0]["value"], "ABCDE1234F")
