"""Standard `BaseRepository` for the `notifications` table (CONTRACTS.md §4) plus
`mark_read`/`mark_all_read`, the two mutations that don't fit `update_scoped` (one is
conditional on the row's current state, the other is a bulk update with no single dict to
return) — `NotificationService` owns the surrounding business logic (CONTRACTS.md §12) but
never touches SQLAlchemy directly, same as every other domain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.database.models import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository):
    model = Notification

    async def mark_read(self, notification_id: str, user_id: str) -> dict[str, Any] | None:
        """Marks one notification read iff it belongs to `user_id`; a no-op if it was
        already read. Returns `None` if no such notification exists for that user."""
        stmt = select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        if row.read_at is None:
            row.read_at = datetime.now(timezone.utc).isoformat()
            await self.session.commit()
            await self.session.refresh(row)
        return self._to_dict(row)

    async def mark_all_read(self, organization_id: str, user_id: str) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(timezone.utc).isoformat())
        )
        await self.session.commit()
