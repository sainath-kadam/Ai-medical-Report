"""Platform domain routes (new — see `README.md` in this folder). Every route here is
`system_admin`-only — this is the one domain in the app that operates across
organizations instead of within one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.security import CurrentUser, require_roles
from app.schemas.common import PaginationParams
from app.schemas.platform import CreateOrganizationRequest, InviteSystemAdminRequest, UpdateOrganizationAccessRequest
from app.services.platform_service import PlatformService
from app.utils.response import ok

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/organizations")
async def list_organizations(
    pagination: PaginationParams = Depends(pagination_params),
    _current_user: CurrentUser = Depends(require_roles("system_admin")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await PlatformService(db).list_organizations(pagination))


@router.get("/organizations/{organization_id}")
async def get_organization(
    organization_id: str,
    _current_user: CurrentUser = Depends(require_roles("system_admin")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await PlatformService(db).get_organization(organization_id))


@router.patch("/organizations/{organization_id}/access")
async def update_organization_access(
    organization_id: str,
    payload: UpdateOrganizationAccessRequest,
    current_user: CurrentUser = Depends(require_roles("system_admin")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await PlatformService(db).update_access(organization_id, payload, current_user.id))


@router.get("/system-admins")
async def list_system_admins(
    _current_user: CurrentUser = Depends(require_roles("system_admin")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await PlatformService(db).list_system_admins())


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
