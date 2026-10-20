import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import require_user
from app.core.config import settings
from app.main import app
from app.schemas.applications import ApplicationChatRequest, ApplicationScope
from app.services import application_assistant


def request_payload(**changes):
    return {
        "messages": [{"role": "user", "content": "I want to apply for an EWS certificate."}],
        "processing_consent": True,
        **changes,
    }


class ApplicationSchemaTests(unittest.TestCase):
    def test_processing_consent_is_required_and_cannot_be_false(self):
        with self.assertRaises(ValidationError):
            ApplicationChatRequest.model_validate({
                "messages": [{"role": "user", "content": "Find an application."}],
            })
        with self.assertRaises(ValidationError):
            ApplicationChatRequest.model_validate(request_payload(processing_consent=False))

    def test_empty_messages_and_oversized_message_are_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicationChatRequest.model_validate(request_payload(messages=[]))
        with self.assertRaises(ValidationError):
            ApplicationChatRequest.model_validate(request_payload(messages=[{
                "role": "user", "content": "x" * 4001,
            }]))

    def test_service_scope_is_limited_to_supported_values(self):
        with self.assertRaises(ValidationError):
            ApplicationScope(service="unsupported")


class ApplicationPrivacyTests(unittest.TestCase):
    def test_personal_processing_is_disabled_by_default(self):
        with patch.object(settings, "applications_personal_data_enabled", False):
            with self.assertRaises(HTTPException) as error:
                application_assistant.require_processing_configuration()
        self.assertEqual(error.exception.status_code, 503)

    def test_non_public_and_non_https_urls_are_rejected(self):
        self.assertEqual(application_assistant.clean_https_url("http://example.gov.in/apply"), "")
        self.assertEqual(application_assistant.clean_https_url("https://127.0.0.1/apply"), "")
        self.assertFalse(application_assistant.official_domain("https://fake-gov.in.example.com"))
        self.assertTrue(application_assistant.official_domain("https://service.gov.in/apply"))


class ApplicationRouteTests(unittest.TestCase):
    def test_capabilities_requires_authenticated_user(self):
        response = TestClient(app).get("/api/applications/capabilities")
        self.assertEqual(response.status_code, 401)

    def test_chat_requires_authenticated_user(self):
        response = TestClient(app).post("/api/applications/chat", json=request_payload())
        self.assertEqual(response.status_code, 401)

    def test_extract_requires_explicit_processing_consent(self):
        app.dependency_overrides[require_user] = lambda: {"uid": "test-user"}
        try:
            response = TestClient(app).post("/api/applications/extract", json={
                "mime_type": "image/jpeg",
                "file_base64": "YWJj",
            })
        finally:
            app.dependency_overrides.pop(require_user, None)
        self.assertEqual(response.status_code, 422)


class ApplicationAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def test_blank_model_service_is_normalized_to_unknown(self):
        request = ApplicationChatRequest.model_validate(request_payload())
        candidate = {
            "content": {
                "parts": [{
                    "text": (
                        '{"reply":"Namaste! What application do you need help with?",'
                        '"scope":{"service":"","state":"","district":"","institution":"","session":""}}'
                    ),
                }],
            },
        }
        with patch.object(application_assistant, "_gemini", new=AsyncMock(return_value=candidate)):
            result = await application_assistant._plan_response(request, None)

        self.assertEqual(result["scope"]["service"], "unknown")

    async def test_unverified_model_requirements_and_portal_are_discarded(self):
        from app.schemas.applications import ApplicationChatRequest

        request = ApplicationChatRequest.model_validate(request_payload())
        response_data = {
            "reply": "I need your state and district.",
            "scope": {"service": "unknown", "state": "", "district": "", "institution": "", "session": ""},
            "title": "EWS certificate",
            "portal_url": "https://service.gov.in/apply",
            "requirements": [{
                "key": "certificate",
                "label": "Income certificate",
                "kind": "document",
                "required": True,
                "description": "Upload an income certificate.",
                "source_url": "https://service.gov.in/apply",
            }],
            "fee": {"value": "₹100", "source_url": "https://service.gov.in/apply"},
            "deadline": {"value": "Tomorrow", "source_url": "https://service.gov.in/apply"},
            "suggested_values": {},
            "questions": ["Which state?"],
        }
        with patch.object(settings, "applications_personal_data_enabled", True), \
             patch.object(settings, "gemini_api_key", "test-key"), \
             patch.object(application_assistant, "_plan_response", new=AsyncMock(return_value=response_data)):
            result = await application_assistant.chat(request, "test-user")

        self.assertEqual(result.plan.requirements, [])
        self.assertEqual(result.plan.portal_url, "")
        self.assertEqual(result.plan.fee.value, "Not verified")
        self.assertEqual(result.plan.deadline.value, "Not verified")
        self.assertEqual(result.plan.sources, [])
