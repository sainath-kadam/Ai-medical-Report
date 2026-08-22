"""Shared pytest fixtures. Tests run against an in-memory SQLite database (via aiosqlite)
instead of a real PostgreSQL server — fast, no external service needed, and correctness
for our purposes is about query/business logic, not Postgres's own server behavior.
`StaticPool` is what makes a `:memory:` SQLite database usable across the multiple
connections a real app takes (one per request) — without it, every new connection would
see a brand-new, empty database.

Every test that needs auth should go through `signup_and_login` rather than
hand-crafting a token, so tests keep exercising the real signup path (and stay valid if
the token shape ever changes).
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("SIGNED_URL_SECRET", "test-signed-url-secret")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import connection as db_connection
from app.database.models import Base


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    db_connection._engine = engine  # type: ignore[attr-defined]
    db_connection._session_factory = session_factory  # type: ignore[attr-defined]

    session = session_factory()
    yield session
    await session.close()
    await engine.dispose()
    db_connection._engine = None  # type: ignore[attr-defined]
    db_connection._session_factory = None  # type: ignore[attr-defined]


@pytest_asyncio.fixture
async def client(db):
    from app.main import app

    # NOTE: ASGITransport does not run FastAPI's lifespan — harmless here since there's
    # nothing left in the lifespan that a test needs (no background-job pool to set up;
    # analysis/change-request both run inline now, see app/api/analysis/README.md).
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac


@pytest_asyncio.fixture
async def signup_and_login(client):
    async def _signup(name="Dr. Test", email="doctor@example.com", password="testpass123", organization_name="Test Clinic"):
        response = await client.post(
            "/auth/signup",
            json={"name": name, "email": email, "password": password, "organizationName": organization_name},
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        client.headers["Authorization"] = f"Bearer {data['accessToken']}"
        return data

    return _signup
