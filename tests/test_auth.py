import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core.auth import require_user
from app.core.config import Settings
from app.main import app


class AuthenticationTests(unittest.TestCase):
    def test_planner_api_rejects_requests_without_bearer_token(self):
        client = TestClient(app)
        for path in (
            "/api/schedules",
            "/api/life-items?kind=meal",
            "/api/food/analyze",
            "/api/family",
            "/api/family/tasks",
            "/api/family/documents",
        ):
            with self.subTest(path=path):
                response = client.get(path) if "food" not in path else client.post(path, json={})
                self.assertEqual(response.status_code, 401, response.text)

    def test_id_token_must_be_valid_and_email_verified(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")
        with patch("app.core.auth._firebase_app", return_value=object()), \
             patch("app.core.auth.auth.verify_id_token", return_value={"uid": "user-123", "email_verified": True}):
            self.assertEqual(require_user(credentials), {"uid": "user-123", "email": None, "display_name": None})

        with patch("app.core.auth._firebase_app", return_value=object()), \
             patch("app.core.auth.auth.verify_id_token", return_value={"uid": "user-123", "email_verified": False}):
            with self.assertRaises(HTTPException) as error:
                require_user(credentials)
        self.assertEqual(error.exception.status_code, 403)

    def test_production_configuration_requires_secure_auth_database_and_cors(self):
        production = Settings()
        production.app_environment = "production"
        production.firebase_project_id = "test-project"
        production.firebase_service_account_json = '{"project_id":"test-project"}'
        production.mongodb_url = "mongodb://localhost:27017"
        production.cors_origins = ["*"]
        with self.assertRaisesRegex(RuntimeError, "mongodb\\+srv"):
            production.validate_production()

        production.mongodb_url = "mongodb+srv://cluster.example/database"
        with self.assertRaisesRegex(RuntimeError, "wildcard"):
            production.validate_production()

        production.cors_origins = ["https://app.example.com"]
        production.validate_production()
        production.cors_origins = []
        production.validate_production()


if __name__ == "__main__":
    unittest.main()
