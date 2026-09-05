"""Business logic for the platform domain (new — see `app/api/platform/README.md`).
`system_admin` is the one role with no organization of its own (CONTRACTS.md §2a) — this
is where it acts across organizations instead of within one.

Both endpoints answer the same question the users domain already solved for inviting a
doctor into an existing org (CONTRACTS.md §8 — no SMTP configured): the new account's
temporary password is returned directly in the response, once, for the system_admin to
relay out-of-band — never emailed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.core.subscription import with_access
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.platform import CreateOrganizationRequest, InviteSystemAdminRequest, UpdateOrganizationAccessRequest
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.utils.ids import to_public, to_public_list
from app.utils.passwords import generate_temp_password, without_password_hash
from app.utils.response import paginated


class PlatformService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.orgs = OrganizationRepository(db)
        self.auth = AuthService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # Managing existing organizations (CONTRACTS.md §2c)
    # ------------------------------------------------------------------

    def _org_summary(self, org_doc: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
        """Public org + evaluated `access` + usage counts. `accessNote` is platform-only and
        stays in here on purpose — this shape is only ever returned to a system_admin."""
        return {**to_public(with_access(org_doc, include_platform_fields=True)), **counts}

    async def list_organizations(self, pagination: PaginationParams) -> dict[str, Any]:
        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.orgs.list_all(search=pagination.search, skip=skip, limit=pagination.page_size)
        counts = await self.orgs.usage_counts([o["_id"] for o in items])
        return paginated([self._org_summary(o, counts[o["_id"]]) for o in items], pagination.page, pagination.page_size, total)

    async def get_organization(self, organization_id: str) -> dict[str, Any]:
        """One organization with its access state, usage counts and member roster (no
        password hashes) — what the platform detail page shows."""
        org = await self.orgs.find_by_id(organization_id)
        if org is None:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")
        counts = await self.orgs.usage_counts([organization_id])
        members, _ = await self.users.list_by_organization(organization_id, 0, 200)
        return {
            "organization": self._org_summary(org, counts[organization_id]),
            "users": to_public_list([without_password_hash(u) for u in members]),
        }

    async def update_access(
        self, organization_id: str, payload: UpdateOrganizationAccessRequest, actor_user_id: str
    ) -> dict[str, Any]:
        """The system_admin's lever over an organization's access: grant/clear a manual
        access period, suspend/unsuspend, annotate, relabel the plan. Audit-logged against
        the target organization (action `ORGANIZATION_ACCESS_UPDATED`) so the org's own
        admins can see in their audit trail *that* the platform changed their access, and
        when — metadata carries field names and the new access values, never the note."""
        update = payload.model_dump(by_alias=True, exclude_unset=True)
        if not update:
            raise AppError.bad_request("Nothing to update", "EMPTY_UPDATE")
        org = await self.orgs.update(organization_id, update)
        if org is None:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

        loggable = {k: v for k, v in update.items() if k != "accessNote"}
        await self.audit.log(
            organization_id=organization_id,
            user_id=actor_user_id,
            action="ORGANIZATION_ACCESS_UPDATED",
            resource_type="organization",
            resource_id=organization_id,
            metadata={"fields": sorted(update.keys()), **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in loggable.items()}},
        )
        counts = await self.orgs.usage_counts([organization_id])
        return {"organization": self._org_summary(org, counts[organization_id])}

    async def list_system_admins(self) -> list[dict[str, Any]]:
        return to_public_list([without_password_hash(u) for u in await self.users.list_by_role("system_admin")])

    # ------------------------------------------------------------------
    # Onboarding (CONTRACTS.md §2b)
    # ------------------------------------------------------------------

    async def create_organization(self, payload: CreateOrganizationRequest, actor_user_id: str) -> dict[str, Any]:
        """Creates a new organization AND its first org_admin user in one call — reuses
        the exact same provisioning `AuthService.signup` uses (org + admin user + default
        report template), since there's no other way for this org to ever get a user who
        can log in. The new org also starts a free trial, same as self-signup, so it can
        go through the normal billing flow (`app/api/billing/`) from there."""
        if await self.users.find_by_email(payload.admin_email) is not None:
            raise AppError.conflict("An account with this email already exists", "EMAIL_TAKEN")

        temp_password = generate_temp_password()
        user_doc, org_doc = await self.auth.provision_org_and_admin_user(
            organization_name=payload.organization_name,
            name=payload.admin_name,
            email=payload.admin_email,
            password_hash=hash_password(temp_password),
            google_id=None,
            avatar_url=None,
            email_verified=False,
        )

        # Unlike a system_admin's own actions (see auth_service.py's login/logout), this
        # DOES have a real organization to log against — the one just created.
        await self.audit.log(
            organization_id=org_doc["_id"],
            user_id=actor_user_id,
            action="ORGANIZATION_CREATED_BY_ADMIN",
            resource_type="organization",
            resource_id=org_doc["_id"],
            metadata={"adminEmail": payload.admin_email},
        )

        return {
            "organization": to_public(org_doc),
            "adminUser": to_public(without_password_hash(user_doc)),
            "temporaryPassword": temp_password,
        }

    async def invite_system_admin(self, payload: InviteSystemAdminRequest) -> dict[str, Any]:
        """Creates another platform-wide account. No organization-scoped audit trail makes
        sense for this (see auth_service.py's identical reasoning for login/logout) — it's
        not logged."""
        if await self.users.find_by_email(payload.email) is not None:
            raise AppError.conflict("An account with this email already exists", "EMAIL_TAKEN")

        temp_password = generate_temp_password()
        created = await self.users.insert(
            {
                "name": payload.name,
                "email": payload.email,
                "passwordHash": hash_password(temp_password),
                "googleId": None,
                "avatarUrl": None,
                "role": "system_admin",
                "organizationId": None,
                "isActive": True,
                "emailVerifiedAt": None,
            }
        )
        public = to_public(without_password_hash(created))
        public["temporaryPassword"] = temp_password
        return public
