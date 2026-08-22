"""Centralized, environment-driven configuration.

Every other module reads settings from the single `settings` instance below rather than
calling `os.environ` directly — this is what makes the app's behavior fully controlled by
`.env` / real environment variables in every deployment (dev, CI, staging, prod) without
code changes, per the "environment-based configuration" requirement.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Server ---
    environment: Literal["development", "test", "production"] = Field("development", alias="ENVIRONMENT")
    port: int = Field(8000, alias="PORT")
    client_url: str = Field("http://localhost:5173", alias="CLIENT_URL")

    # --- Database ---
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/medscan", alias="DATABASE_URL"
    )

    # --- Auth ---
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_access_token_minutes: int = Field(30, alias="JWT_ACCESS_TOKEN_MINUTES")
    jwt_refresh_token_days: int = Field(30, alias="JWT_REFRESH_TOKEN_DAYS")
    google_client_id: str | None = Field(None, alias="GOOGLE_CLIENT_ID")

    # --- AI ---
    # Default is "gemini": one model (Gemini) does both image analysis and report
    # writing, no tiering. "anthropic" (Claude, both jobs, tiered fast/default/
    # highAccuracy/max) is kept as an alternative, already-proven path — set AI_PROVIDER=
    # anthropic to use it instead.
    ai_provider: Literal["anthropic", "gemini", "mock"] = Field("gemini", alias="AI_PROVIDER")
    ai_api_key: str | None = Field(None, alias="AI_API_KEY")
    ai_model_fast: str = Field("claude-haiku-4-5", alias="AI_MODEL_FAST")
    ai_model_default: str = Field("claude-sonnet-5", alias="AI_MODEL_DEFAULT")
    ai_model_high_accuracy: str = Field("claude-opus-5", alias="AI_MODEL_HIGH_ACCURACY")
    ai_model_max: str = Field("claude-fable-5", alias="AI_MODEL_MAX")
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field("high", alias="AI_EFFORT")

    # --- Gemini (only read when ai_provider="gemini") ---
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-3.6-flash", alias="GEMINI_MODEL")

    # --- Storage ---
    # "local" needs zero config (default, always works for dev). "firebase"/"s3"/
    # "s3_compatible" are opt-in — each needs its own credentials below, so none of them
    # are the default (a missing bucket/credential would break the very first upload).
    storage_provider: Literal["local", "firebase", "s3", "s3_compatible"] = Field("local", alias="STORAGE_PROVIDER")
    storage_local_dir: str = Field("uploads", alias="STORAGE_LOCAL_DIR")
    storage_bucket: str | None = Field(None, alias="STORAGE_BUCKET")
    storage_region: str | None = Field(None, alias="STORAGE_REGION")
    storage_access_key: str | None = Field(None, alias="STORAGE_ACCESS_KEY")
    storage_secret_key: str | None = Field(None, alias="STORAGE_SECRET_KEY")
    storage_endpoint_url: str | None = Field(None, alias="STORAGE_ENDPOINT_URL")
    # Firebase Storage is Google Cloud Storage under the hood — the service-account JSON
    # key is from Firebase Console > Project Settings > Service Accounts.
    firebase_credentials_path: str | None = Field(None, alias="FIREBASE_CREDENTIALS_PATH")
    firebase_storage_bucket: str | None = Field(None, alias="FIREBASE_STORAGE_BUCKET")
    max_upload_mb: int = Field(50, alias="MAX_UPLOAD_MB")
    signed_url_secret: str = Field(..., alias="SIGNED_URL_SECRET")
    signed_url_ttl_seconds: int = Field(300, alias="SIGNED_URL_TTL_SECONDS")

    # --- Rate limiting ---
    rate_limit_auth_per_15min: int = Field(30, alias="RATE_LIMIT_AUTH_PER_15MIN")
    rate_limit_api_per_15min: int = Field(600, alias="RATE_LIMIT_API_PER_15MIN")

    # --- Trial & subscription (billing) ---
    trial_days: int = Field(3, alias="TRIAL_DAYS")
    trial_daily_report_limit: int = Field(100, alias="TRIAL_DAILY_REPORT_LIMIT")
    stripe_secret_key: str | None = Field(None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id: str | None = Field(None, alias="STRIPE_PRICE_ID")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def billing_configured(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_price_id)

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider == "anthropic":
            return bool(self.ai_api_key)
        if self.ai_provider == "gemini":
            return bool(self.gemini_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env/.env at runtime


settings = get_settings()
