"""Refresh-token sessions (CONTRACTS.md §2, §11, §12; spec §5).

`sessions` is one of the tables that is NOT organization-scoped (CONTRACTS.md §11) — every
lookup here is keyed by `userId` or by the token hash itself, so this repository only
relies on the unscoped `insert` / `find_by_id` primitives from `BaseRepository` plus the
custom methods below. Never reach for the `*_scoped` helpers here; there is no
`organizationId` column on this table.

The refresh token itself is never persisted — only its sha256 hash
(`app/core/security.py::hash_refresh_token`) — so a leaked database dump can't be replayed
as a live session. `expiresAt` is a real `DateTime` column (not an ISO string), matching
the original Mongo TTL-index field so `find_valid`'s own expiry check keeps working
identically; this table is never serialized into an API response, so it sits outside the
"timestamps are ISO-8601 strings" wire convention in CONTRACTS.md §1 on purpose.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.database.models import Session
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository):
    model = Session

    async def create_session(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
    ) -> dict[str, Any]:
        doc = {
            "userId": user_id,
            "tokenHash": token_hash,
            "userAgent": user_agent,
            "expiresAt": expires_at,
            "revokedAt": None,
        }
        return await self.insert(doc)

    async def find_valid(self, token_hash: str) -> dict[str, Any] | None:
        """A session is valid iff it hasn't been revoked AND hasn't expired yet."""
        stmt = select(Session).where(
            Session.token_hash == token_hash,
            Session.revoked_at.is_(None),
            Session.expires_at > datetime.now(timezone.utc),
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def revoke(self, token_hash: str) -> None:
        await self.session.execute(
            update(Session).where(Session.token_hash == token_hash).values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.commit()

    async def revoke_all_for_user(self, user_id: str) -> None:
        """Used e.g. on password change/reset to kill every other logged-in session."""
        await self.session.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.commit()
