"""In-app notifications (CONTRACTS.md §4, §8, §11, §12).

Email/SMS delivery is explicitly NOT implemented in this rebuild — see the single
`logger.info(...)` seam in `create()` below. Every notification lives only in the database
and is polled/read via the API for now; wiring a real provider later means filling in that
one call site, nothing else.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.notification_repository import NotificationRepository

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._repo = NotificationRepository(db)

    async def create(
        self,
        *,
        organization_id: str,
        user_id: str,
        type: str,  # noqa: A002 - matches the CONTRACTS.md §12 keyword name exactly
        title: str,
        body: str,
        link: str | None = None,
    ) -> dict[str, Any]:
        # `notifications` has no `updatedAt` column (CONTRACTS.md §4 doesn't define one),
        # so `BaseRepository.insert` — which only stamps `updatedAt` when the table actually
        # has that column — is safe to use directly here, unlike the Mongo version which
        # had to bypass it by hand to avoid a stray field on a schemaless document.
        created = await self._repo.insert(
            {
                "organizationId": organization_id,
                "userId": user_id,
                "type": type,
                "title": title,
                "body": body,
                "link": link,
                "readAt": None,
            }
        )

        # --- SEAM: email/SMS sending is intentionally NOT implemented yet. -----------------
        # A future integration (e.g. SES/SendGrid for email, Twilio for SMS) would dispatch
        # this same notification here, gated by user/org notification preferences. Until
        # then, notifications are in-app only. Only ids/enums are logged, never the title or
        # body text (spec §31).
        logger.info("Notification created (email/SMS delivery not implemented): type=%s userId=%s", type, user_id)

        return created

    async def list_for_user(
        self,
        organization_id: str,
        user_id: str,
        skip: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._repo.list_scoped(
            organization_id,
            {"userId": user_id},
            sort=[("createdAt", -1)],
            skip=skip,
            limit=limit,
        )

    async def mark_read(self, notification_id: str, user_id: str) -> dict[str, Any] | None:
        return await self._repo.mark_read(notification_id, user_id)

    async def mark_all_read(self, organization_id: str, user_id: str) -> None:
        await self._repo.mark_all_read(organization_id, user_id)
