"""Report persistence (CONTRACTS.md §4/§12; spec §25 — never silently overwrite, always
append a new version).

Standard `BaseRepository` CRUD (table `reports`) plus `append_version`, the one
cross-domain-relied-on mutation: every version-producing action (manual edit, AI
change-request revision, regenerate) goes through this so `currentVersion`/`versions`/
`status` are always updated together, atomically, from one place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.database.models import Report
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository):
    model = Report

    async def append_version(
        self, report_id: str, organization_id: str, version: dict[str, Any], new_status: str
    ) -> dict[str, Any] | None:
        stmt = select(Report).where(Report.id == report_id, Report.organization_id == organization_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        # Reassign (rather than `.append`) so SQLAlchemy's change-tracking on the JSON
        # column actually detects the mutation and includes it in the UPDATE.
        row.versions = [*row.versions, version]
        row.current_version = version["versionNumber"]
        row.status = new_status
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)
