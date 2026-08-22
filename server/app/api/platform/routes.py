"""Platform domain routes (new — see `README.md` in this folder). Every route here is
`system_admin`-only — this is the one domain in the app that operates across
organizations instead of within one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import CurrentUser, require_roles
from app.schemas.platform import CreateOrganizationRequest, InviteSystemAdminRequest
from app.services.platform_service import PlatformService
from app.utils.response import ok

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/organizations", status_code=201)
async def create_organization(
    payload: CreateOrganizationRequest,
    current_user: CurrentUser = Depends(require_roles("system_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await PlatformService(db).create_organization(payload, current_user.id)
    return ok(result, status_code=201)


@router.post("/system-admins", status_code=201)
async def invite_system_admin(
    payload: InviteSystemAdminRequest,
    _current_user: CurrentUser = Depends(require_roles("system_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await PlatformService(db).invite_system_admin(payload)
    return ok(result, status_code=201)
