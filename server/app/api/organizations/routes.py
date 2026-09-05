"""Organizations domain routes (CONTRACTS.md §9): GET/PATCH /organizations/me.

An organization IS the tenant boundary, so there is no list/create/delete here — only
"read my org" (any authenticated role) and "update my org" (`org_admin` only, spec §8).
Both routes work off `current_user.organization_id` — a client can never target another
organization's record.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.subscription import with_access
from app.schemas.organization import OrganizationUpdateRequest
from app.services.organization_service import OrganizationService
from app.utils.ids import to_public
from app.utils.response import ok

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me")
async def get_my_organization(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Wrapped as {"organization": ...} to match the sibling GET /auth/me shape
    # ({user, organization}) that the already-built frontend organization.api.ts assumes.
    org = await OrganizationService(db).get_by_id(current_user.organization_id)
    return ok({"organization": to_public(with_access(org))})


@router.patch("/me")
async def update_my_organization(
    body: OrganizationUpdateRequest,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    update = body.model_dump(by_alias=True, exclude_unset=True)
    org = await OrganizationService(db).update(current_user.organization_id, update, current_user.id)
    # Wrapped for the same reason GET above is — matches organization.api.ts's `.then((r)
    # => r.data.data.organization)` unwrap.
    return ok({"organization": to_public(with_access(org))})
