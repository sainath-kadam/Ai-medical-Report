"""Password-reset tokens (CONTRACTS.md §2, §11, §12).

Like `sessions`, `password_reset_tokens` is NOT organization-scoped (CONTRACTS.md §11) —
scoped by `userId` instead — so this repository only uses the unscoped `BaseRepository`
primitives plus the custom methods below, never the `*_scoped` helpers.

A token is single-use: `consume()` deletes the record outright so it can never be replayed,
even if the hash somehow leaked after use. `expiresAt` is a real `DateTime` column (not an
ISO string), matching the original Mongo TTL-index field — this table is internal-only and
never serialized into an API response.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.database.models import PasswordResetToken
from app.repositories.base import BaseRepository


class PasswordResetRepository(BaseRepository):
    model = PasswordResetToken

    async def create_token(self, user_id: str, token_hash: str, expires_at: datetime) -> dict[str, Any]:
        doc = {
            "userId": user_id,
            "tokenHash": token_hash,
            "expiresAt": expires_at,
        }
        return await self.insert(doc)

    async def find_valid(self, token_hash: str) -> dict[str, Any] | None:
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def consume(self, token_hash: str) -> None:
        """Deletes the token record so it can never be redeemed a second time."""
        await self.session.execute(delete(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
        await self.session.commit()
