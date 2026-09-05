"""User persistence (CONTRACTS.md §4, §11, §12).

Per CONTRACTS.md §11, `users` is NOT an organization-scoped table in the
`BaseRepository.*_scoped` sense (a user's primary key is its own `id`, not a parent
resource under an org filter) — so this repository only reuses `BaseRepository` for
`insert` / `find_by_id`, and adds the custom lookups other domains and the auth flow need.
Callers that must enforce multi-tenant isolation (e.g. the users service letting an
org_admin manage only their own org's roster) compare `organizationId` on the returned
document themselves — see `app/services/user_service.py`.

`insert(doc)`, `find_by_id(id)`, `find_by_email(email)`, `find_by_google_id(gid)`, and
`list_by_organization(organization_id, skip, limit)` match the EXACT signatures other
domains (auth) import — do not rename/reorder these.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select

from app.database.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    model = User

    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        row = (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def find_by_google_id(self, google_id: str) -> dict[str, Any] | None:
        row = (await self.session.execute(select(User).where(User.google_id == google_id))).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def list_by_organization(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 20,
        *,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = [User.organization_id == organization_id]
        if search:
            pattern = f"%{search}%"
            conditions.append(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

        total = (await self.session.execute(select(func.count()).select_from(User).where(*conditions))).scalar_one()
        stmt = select(User).where(*conditions).order_by(User.created_at.desc()).offset(skip).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_dict(r) for r in rows], total

    async def list_by_role(self, role: str) -> list[dict[str, Any]]:
        """Every account with `role` across the whole platform, oldest first. Only used for
        `role="system_admin"` (CONTRACTS.md §2b) — those have no organization to scope by."""
        stmt = select(User).where(User.role == role).order_by(User.created_at.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_dict(r) for r in rows]

    async def update(self, user_id: str, update: dict[str, Any]) -> dict[str, Any] | None:
        """Not organization-scoped (see module docstring) — callers must verify the
        target document belongs to the caller's organization before calling this."""
        row = await self.session.get(User, user_id)
        if row is None:
            return None
        for key, value in self._to_kwargs(update).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)

    async def delete(self, user_id: str) -> bool:
        """Not organization-scoped (see module docstring) — callers must verify the
        target document belongs to the caller's organization before calling this."""
        row = await self.session.get(User, user_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.commit()
        return True
