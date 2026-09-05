"""Centralized, environment-driven configuration.

Every other module reads settings from the single `settings` instance below rather than
calling `os.environ` directly — this is what makes the app's behavior fully controlled by
`.env` / real environment variables in every deployment (dev, CI, staging, prod) without
code changes, per the "environment-based configuration" requirement.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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
    # Full report text (generate()/revise()/classify_change_request()/extract_intake()).
    gemini_model: str = Field("gemini-3.6-flash", alias="GEMINI_MODEL")
    # Image interpretation (GeminiImagingProvider.analyze()) — the "look at the pixels"
    # step, kept as its own setting so it can run a different (e.g. higher-accuracy) model
    # than the text-only report-writing call above.
    # Flash, not Pro, on purpose: verified against the live ListModels/generateContent API —
    # `gemini-3.1-pro` does not exist (404), and the Pro models that do exist
    # (`gemini-3.1-pro-preview`, `gemini-pro-latest`) return quota errors on a free-tier
    # key, which silently failed every analysis. Pro is opt-in per organization instead,
    # via High-Accuracy Mode -> gemini_high_accuracy_model below.
    gemini_imaging_model: str = Field("gemini-3.8-flash", alias="GEMINI_IMAGING_MODEL")
    # The pre-report clinical-summary step (BaseReportGenerationProvider.summarize_findings)
    # — also its own setting, independent of both models above, so it can be tuned/swapped
    # without touching image interpretation or full report drafting.
    gemini_summary_model: str = Field("gemini-3.8-flash", alias="GEMINI_SUMMARY_MODEL")
    # Used INSTEAD of gemini_imaging_model / gemini_summary_model while the organization's
    # High-Accuracy Mode toggle (Organization Settings) is on — the two steps where a
    # stronger model changes what the doctor reads. Report text stays on gemini_model
    # (it only rewrites findings already computed). Pro has zero free-tier quota (429
    # "limit: 0", verified live), so on a free key the provider falls back to the standard
    # model and logs it rather than failing the analysis — see gemini_provider._tiered.
    # Needs a paid Gemini plan (billing enabled in AI Studio) to actually take effect.
    gemini_high_accuracy_model: str = Field("gemini-3.1-pro-preview", alias="GEMINI_HIGH_ACCURACY_MODEL")
    # Comma-separated models tried in order when the requested one is overloaded (503/429/
    # 5xx after a short retry) or doesn't exist (404) — see gemini_provider._generate_json.
    # Not `gemini-flash-latest`: verified live, it is an alias of the current Flash and
    # shares its free-tier daily quota (20 requests/day/model, both hit 429 together), so it
    # never rescues anything. Flash-Lite is the last resort instead — a separate quota
    # bucket with a free tier, so a day's reports keep flowing after both Flash quotas are
    # spent (clearly recorded in `model_used`; a doctor still reviews every draft).
    gemini_fallback_models: str = Field("gemini-3.6-flash,gemini-3.5-flash-lite", alias="GEMINI_FALLBACK_MODELS")

    # --- Storage ---
    # "local" needs zero config (default, always works for dev). "cloudinary"/"firebase"/
    # "s3"/"s3_compatible" are opt-in — each needs its own credentials below, so none of
    # them are the default (a missing bucket/credential would break the very first upload).
    storage_provider: Literal["local", "cloudinary", "firebase", "s3", "s3_compatible"] = Field("local", alias="STORAGE_PROVIDER")
    # Optional second provider: uploads go here whenever STORAGE_PROVIDER is unavailable
    # (not configured, or the upload fails); reads check both. See app/storage/fallback.py.
    storage_fallback_provider: Literal["local", "cloudinary", "firebase", "s3", "s3_compatible"] | None = Field(
        None, alias="STORAGE_FALLBACK_PROVIDER"
    )
    storage_local_dir: str = Field("uploads", alias="STORAGE_LOCAL_DIR")
    # Cloudinary: either the single CLOUDINARY_URL from the console
    # (cloudinary://<api_key>:<api_secret>@<cloud_name>) or the three separate values.
    cloudinary_url: str | None = Field(None, alias="CLOUDINARY_URL")
    cloudinary_cloud_name: str | None = Field(None, alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str | None = Field(None, alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str | None = Field(None, alias="CLOUDINARY_API_SECRET")
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

    # --- Normalization that makes copy-pasted hosting values work as-is (see DEPLOY.md) ---
    @field_validator("database_url", mode="before")
    @classmethod
    def _use_asyncpg_driver(cls, value: object) -> object:
        """Accept the bare `postgres://` / `postgresql://` URL that Render, Heroku, Supabase
        etc. hand out. Without the `+asyncpg` driver marker SQLAlchemy picks the sync
        psycopg2 driver, which isn't installed, so the app would die at startup with
        "No module named psycopg2" — normalize here instead of making every deployment
        hand-edit the scheme. SQLite (tests) and already-explicit URLs pass through untouched.
        """
        if isinstance(value, str):
            for bare_scheme in ("postgresql://", "postgres://"):
                if value.startswith(bare_scheme):
                    return "postgresql+asyncpg://" + value[len(bare_scheme):]
        return value

    @field_validator("client_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """CORSMiddleware compares this byte-for-byte against the browser's `Origin` header,
        which never carries a trailing slash — a pasted `https://app.netlify.app/` would
        silently block every request. It's also concatenated with `/reset-password...` and
        `/billing/...` paths, so the slash would otherwise double up there too."""
        return value.rstrip("/")

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
