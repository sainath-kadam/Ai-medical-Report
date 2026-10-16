"""FastAPI application entrypoint. `uvicorn app.main:app` (see Dockerfile / README)."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.database.connection import close_db_connection, connect_to_db, get_engine, get_session_factory
from app.database.models import Base
from app.database.schema_sync import sync_missing_columns
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.services.retention_service import run_retention_loop
from app.services.analysis_service import fail_interrupted_analyses
from app.services.video_service import fail_interrupted_compressions

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_db()
    # Greenfield schema management: create any missing tables on startup rather than
    # requiring a separate migration step before the app can run for the first time, then
    # add any column a model gained since the table was created (create_all alone never
    # alters an existing table — see database/schema_sync.py). Once the schema needs real
    # data-preserving migrations (renames, type changes, NOT NULL backfills), this is the
    # seam to replace with Alembic.
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        added_columns = await conn.run_sync(sync_missing_columns)
    if added_columns:
        logger.warning("Schema sync added %d missing column(s): %s", len(added_columns), ", ".join(added_columns))

    try:
        async with get_session_factory()() as session:
            await fail_interrupted_compressions(session)
            await fail_interrupted_analyses(session)
    except Exception:
        logger.exception("Could not check for interrupted background work")

    # Hourly storage cleanup: oldest videos go once storage passes STORAGE_CLEANUP_PERCENT,
    # plus the optional VIDEO_RETENTION_DAYS age rule (retention_service.py).
    cleanup_enabled = settings.storage_cleanup_percent > 0 or settings.video_retention_days > 0
    retention_task = asyncio.create_task(run_retention_loop()) if cleanup_enabled else None

    logger.info("Application startup complete (environment=%s)", settings.environment)

    yield

    if retention_task is not None:
        retention_task.cancel()
        with suppress(asyncio.CancelledError):
            await retention_task
    await close_db_connection()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Radiolens API",
    description=(
        "Medical imaging AI reporting platform API. AI-generated content is always "
        "preliminary decision-support and requires review/approval by a qualified "
        "medical professional before being treated as a final report."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Secure headers appropriate for a JSON API serving no HTML (spec §31).
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.client_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")
