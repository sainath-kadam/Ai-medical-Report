"""Repository for the `report_templates` table (CONTRACTS.md §4/§12). Standard
`BaseRepository` CRUD plus `get_default`, used both by `TemplateService` and by other
domains (analysis/report generation) that need "the org's default template" without
depending on the service layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.database.models import ReportTemplate
from app.repositories.base import BaseRepository


class TemplateRepository(BaseRepository):
    model = ReportTemplate

    async def get_default(self, organization_id: str) -> dict[str, Any] | None:
        stmt = select(ReportTemplate).where(
            ReportTemplate.organization_id == organization_id, ReportTemplate.is_default.is_(True)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def unset_other_defaults(self, organization_id: str, exclude_id: str | None = None) -> None:
        """Clears `isDefault` on every other template for the org so at most one template
        is ever the default at a time (CONTRACTS.md §9 requirement on the PATCH route)."""
        conditions = [ReportTemplate.organization_id == organization_id, ReportTemplate.is_default.is_(True)]
        if exclude_id is not None:
            conditions.append(ReportTemplate.id != exclude_id)
        await self.session.execute(
            update(ReportTemplate)
            .where(*conditions)
            .values(is_default=False, updated_at=datetime.now(timezone.utc))
        )
        await self.session.commit()
