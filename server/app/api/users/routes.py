"""Users domain routes (CONTRACTS.md §9). Every route requires auth; every route is
org_admin-only EXCEPT `GET /{user_id}`, which also allows a caller to fetch their own
record — that carve-out is enforced inside `UserService.get_user`, so the route dependency
here can stay a plain `get_current_user` rather than needing per-route custom logic.

Routers stay thin: parse the request, call the service, return `ok(...)`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.security import CurrentUser, get_current_user, require_roles
from app.schemas.common import PaginationParams
from app.schemas.user import UserInviteRequest, UserUpdateRequest
from app.services.user_service import UserService
from app.utils.response import ok

router = APIRouter(prefix="/users", tags=["users"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    """IP/user-agent captured by `RequestContextMiddleware`, forwarded to audit log calls
    (CONTRACTS.md §4 audit_logs `ip?`/`userAgent?`)."""
    return getattr(request.state, "client_ip", None), getattr(request.state, "user_agent", None)


@router.get("")
async def list_users(
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await UserService(db).list_users(current_user, pagination)
    return ok(result)


@router.post("", status_code=201)
async def invite_user(
    payload: UserInviteRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await UserService(db).invite_user(current_user, payload, ip=ip, user_agent=user_agent)
    return ok(result, status_code=201)


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await UserService(db).get_user(current_user, user_id)
    return ok(result)


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await UserService(db).update_user(current_user, user_id, payload, ip=ip, user_agent=user_agent)
    return ok(result)


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    await UserService(db).delete_user(current_user, user_id, ip=ip, user_agent=user_agent)
    return ok(None)
