"""SQLAlchemy (async) engine/session lifecycle.

`connect_to_db()` / `close_db_connection()` are called once from the FastAPI lifespan in
`app/main.py` at process startup/shutdown.

Unlike the old Motor client (one handle safely shared across every concurrent request),
an `AsyncSession` is NOT safe to share — every request gets its own, created fresh via
`get_session_factory()`. `app/api/deps.py::get_db` is the FastAPI-dependency wrapper every
route uses.

(There used to be a second process here — an ARQ worker running AI analysis/report jobs
in the background over Redis, with its own copy of this same startup/shutdown lifecycle.
Both were removed to keep local dev to one process; `POST /analysis/studies/{id}/analyze`
now runs `AnalysisService.run_analysis` inline instead — see that module's docstring.)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def connect_to_db() -> None:
    global _engine, _session_factory
    _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    # Fail fast on startup if the database is unreachable, instead of on the first request.
    async with _engine.connect():
        pass
    logger.info("Connected to database")


async def close_db_connection() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database connection closed")
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialized — connect_to_db() has not run yet")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized — connect_to_db() has not run yet")
    return _session_factory
