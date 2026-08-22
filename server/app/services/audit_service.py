"""Audit trail (CONTRACTS.md §4, §8, §11, §12; spec §30/§31).

`AuditService(db).log(...)` is the ONE way any document ever lands in `audit_logs` — every
service method that mutates state across the codebase calls it after the mutation succeeds,
using the exact keyword-only signature below so other domains (written in parallel) can
import and call it without knowing anything else about this module.

`metadata` must stay a small, non-PHI dict — ids, enums, and counts only. Never put
report/finding text, patient names, or file contents into it (spec §31).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._repo = AuditLogRepository(db)

    async def log(
        self,
        *,
        organization_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        # `audit_logs` has no `updatedAt` column (CONTRACTS.md §4 doesn't define one), so
        # `BaseRepository.insert` — which only stamps `updatedAt` when the table actually
        # has that column — is safe to use directly here, unlike the Mongo version which
        # had to bypass it by hand to avoid a stray field on a schemaless document.
        await self._repo.insert(
            {
                "organizationId": organization_id,
                "userId": user_id,
                "action": action,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "metadata": metadata or {},
                "ip": ip,
                "userAgent": user_agent,
            }
        )

    async def list_logs(
        self,
        *,
        organization_id: str,
        skip: int,
        limit: int,
        action: str | None = None,
        user_id: str | None = None,
        resource_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Backing query for `GET /audit-logs` (org_admin only, CONTRACTS.md §3/§9),
        sorted newest-first. Not part of the CONTRACTS.md §12 cross-domain surface — only
        this module's own router calls it."""
        extra_filter: dict[str, Any] = {}
        if action:
            extra_filter["action"] = action
        if user_id:
            extra_filter["userId"] = user_id
        if resource_type:
            extra_filter["resourceType"] = resource_type
        if date_from or date_to:
            created_range: dict[str, Any] = {}
            if date_from:
                created_range["$gte"] = date_from.isoformat()
            if date_to:
                created_range["$lte"] = date_to.isoformat()
            extra_filter["createdAt"] = created_range

        return await self._repo.list_scoped(
            organization_id,
            extra_filter,
            sort=[("createdAt", -1)],
            skip=skip,
            limit=limit,
        )
