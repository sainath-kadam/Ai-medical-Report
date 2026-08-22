"""Organizations repository (CONTRACTS.md §4, §12).

The `organizations` table is NOT itself organization-scoped — an organization IS the
tenant boundary, not a tenant-scoped resource — so this repository looks up and updates
rows by their own `id` only, never by an `organizationId` filter. It therefore uses
`BaseRepository`'s `insert` / `find_by_id` as-is and adds a plain (non-scoped) `update`,
matching the exact signature other domains (auth signup/login, etc.) depend on per
CONTRACTS.md §12: `insert(doc)`, `find_by_id(id) -> dict|None`, `update(id, update) ->
dict|None`.

`find_by_stripe_customer_id` is a custom lookup for `billing_service.py`'s webhook
handler (Stripe's `customer.subscription.*` events carry a Stripe customer id, not our
own), added the same way `UserRepository.find_by_email`/`find_by_google_id` add their
own custom, non-`_scoped` finders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.database.models import Organization
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository):
    model = Organization

    async def update(self, doc_id: str, update: dict[str, Any]) -> dict[str, Any] | None:
        row = await self.session.get(Organization, doc_id)
        if row is None:
            return None
        for key, value in self._to_kwargs(update).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)

    async def find_by_stripe_customer_id(self, customer_id: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(Organization).where(Organization.stripe_customer_id == customer_id))
        ).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None
