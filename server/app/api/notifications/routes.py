"""Notifications routes (CONTRACTS.md §9): `GET /notifications`,
`PATCH /notifications/{id}/read`, `PATCH /notifications/read-all`.

Every route is scoped to the current user within their own organization — there is no way
for a caller to read or mark another user's notifications, and no organization id is ever
taken from the client.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.exceptions import AppError
from app.core.security import CurrentUser, get_current_user
from app.schemas.common import PaginationParams
from app.services.notification_service import NotificationService
from app.utils.ids import to_public, to_public_list
from app.utils.response import ok, paginated

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    skip = (pagination.page - 1) * pagination.page_size
    items, total = await NotificationService(db).list_for_user(
        current_user.organization_id, current_user.id, skip, pagination.page_size
    )
    return ok(paginated(to_public_list(items), pagination.page, pagination.page_size, total))


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await NotificationService(db).mark_read(notification_id, current_user.id)
    if updated is None:
        raise AppError.not_found("Notification not found")
    return ok(to_public(updated))


@router.patch("/read-all")
async def mark_all_notifications_read(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await NotificationService(db).mark_all_read(current_user.organization_id, current_user.id)
    return ok(None)
