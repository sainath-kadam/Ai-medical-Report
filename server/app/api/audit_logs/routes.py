"""Audit-logs routes (CONTRACTS.md §9): `GET /audit-logs`.

`org_admin` only (RBAC matrix, CONTRACTS.md §3 — "View audit logs"). Supports optional
filters (`action`, `userId`, `resourceType`, `dateFrom`/`dateTo`) and standard pagination,
sorted newest-first.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.security import CurrentUser, require_roles
from app.schemas.common import PaginationParams
from app.services.audit_service import AuditService
from app.utils.ids import to_public_list
from app.utils.response import ok, paginated

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("")
async def list_audit_logs(
    action: str | None = Query(None),
    user_id: str | None = Query(None, alias="userId"),
    resource_type: str | None = Query(None, alias="resourceType"),
    date_from: datetime | None = Query(None, alias="dateFrom"),
    date_to: datetime | None = Query(None, alias="dateTo"),
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    skip = (pagination.page - 1) * pagination.page_size
    items, total = await AuditService(db).list_logs(
        organization_id=current_user.organization_id,
        skip=skip,
        limit=pagination.page_size,
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(paginated(to_public_list(items), pagination.page, pagination.page_size, total))
