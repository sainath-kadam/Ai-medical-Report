"""Settings normalization that only matters once the app is deployed (see DEPLOY.md):
hosting providers hand out database URLs and origins in shapes the app must accept as-is.
"""

from app.core.config import Settings

_REQUIRED = {"JWT_SECRET": "x", "SIGNED_URL_SECRET": "x"}


def _settings(**overrides: str) -> Settings:
    # _env_file=None: don't let a developer's local server/.env leak into these assertions.
    return Settings(_env_file=None, **_REQUIRED, **overrides)  # type: ignore[call-arg]


def test_bare_postgresql_scheme_is_rewritten_to_asyncpg():
    # What Render's "Internal Database URL" / a Blueprint `fromDatabase` value looks like.
    s = _settings(DATABASE_URL="postgresql://medscan:pw@dpg-abc123-a/medscan")
    assert s.database_url == "postgresql+asyncpg://medscan:pw@dpg-abc123-a/medscan"


def test_legacy_postgres_scheme_is_rewritten_to_asyncpg():
    # What Heroku-style providers hand out.
    s = _settings(DATABASE_URL="postgres://u:p@host:5432/db")
    assert s.database_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_explicit_asyncpg_and_sqlite_urls_are_untouched():
    explicit = "postgresql+asyncpg://u:p@host:5432/db"
    assert _settings(DATABASE_URL=explicit).database_url == explicit
    sqlite = "sqlite+aiosqlite:///:memory:"
    assert _settings(DATABASE_URL=sqlite).database_url == sqlite


def test_client_url_trailing_slash_is_stripped():
    assert _settings(CLIENT_URL="https://medscan.netlify.app/").client_url == "https://medscan.netlify.app"
    assert _settings(CLIENT_URL="https://medscan.netlify.app").client_url == "https://medscan.netlify.app"
