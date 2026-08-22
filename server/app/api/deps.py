"""Small dependencies shared across domain routers, kept separate from `core/security.py`
(auth-specific) so routers importing "just the DB" don't pull in the auth machinery."""

from typing import AsyncIterator

from fastapi import Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session_factory
from app.schemas.common import PaginationParams


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def pagination_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    search: str | None = Query(None),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size, search=search)
