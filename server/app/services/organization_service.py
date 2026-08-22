"""Business logic for the organizations domain (CONTRACTS.md §9).

An organization IS the tenant boundary for this app, so unlike every other domain module
there is no list/create/delete here — just "read my org" and "update my org". RBAC (only
`org_admin` may update) is enforced by the router's `require_roles` dependency; this
service assumes the caller has already been authorized and just needs an
`organization_id` + the acting user's id (for the audit trail).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories.organization_repository import OrganizationRepository
from app.services.audit_service import AuditService


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrganizationRepository(db)
        self.audit = AuditService(db)

    async def get_by_id(self, organization_id: str) -> dict[str, Any]:
        org = await self.repo.find_by_id(organization_id)
        if org is None:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")
        return org

    async def update(
        self,
        organization_id: str,
        update: dict[str, Any],
        actor_user_id: str,
    ) -> dict[str, Any]:
        if not update:
            # Nothing to change — still validate the org exists rather than no-op silently.
            return await self.get_by_id(organization_id)

        org = await self.repo.update(organization_id, update)
        if org is None:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

        # metadata is field names only — never the new values (could carry PHI-adjacent
        # branding/contact text) — per spec §30/§31 (see CONTRACTS.md §4 audit_logs note).
        await self.audit.log(
            organization_id=organization_id,
            user_id=actor_user_id,
            action="ORGANIZATION_UPDATED",
            resource_type="organization",
            resource_id=organization_id,
            metadata={"fields": sorted(update.keys())},
        )
        return org
