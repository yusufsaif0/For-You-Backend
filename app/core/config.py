import os
import json

from dotenv import load_dotenv


load_dotenv()


class Settings:
    """Environment-backed application settings."""

    app_name = "Daily Life API"
    api_v1_prefix = "/api"
    mongodb_url = os.getenv("MONGODB_URL")
    mongodb_database = os.getenv("DATABASE_NAME", "daily_life")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    applications_gemini_model = os.getenv("APPLICATIONS_GEMINI_MODEL", gemini_model).strip()
    applications_personal_data_enabled = os.getenv("APPLICATIONS_PERSONAL_DATA_ENABLED", "false").lower() == "true"
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    firebase_service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    app_environment = os.getenv("APP_ENV", "development").strip().lower()
    cors_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "*").split(",")
        if origin.strip()
    ]

    def validate_production(self) -> None:
        if self.app_environment != "production":
            return
        if not self.firebase_project_id:
            raise RuntimeError("FIREBASE_PROJECT_ID is required in production.")
        if not self.mongodb_url or not self.mongodb_url.startswith("mongodb+srv://"):
            raise RuntimeError("Production MONGODB_URL must use a TLS-enabled mongodb+srv:// Atlas connection.")
        if not self.firebase_service_account_json:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is required in production.")
        try:
            account = json.loads(self.firebase_service_account_json)
        except json.JSONDecodeError as error:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON must contain valid JSON.") from error
        if account.get("project_id") != self.firebase_project_id:
            raise RuntimeError("The Firebase service account project does not match FIREBASE_PROJECT_ID.")
        if "*" in self.cors_origins:
            raise RuntimeError("CORS_ORIGINS must not include a wildcard in production.")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise RuntimeError("Every production CORS_ORIGINS entry must use HTTPS.")


settings = Settings()
