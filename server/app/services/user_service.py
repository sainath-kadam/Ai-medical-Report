"""Business logic for the users domain (CONTRACTS.md §9, §12). Routers stay thin — they
parse the request, call one of these methods, and hand the result to `ok(...)`.

RBAC note: every route except `GET /users/{id}` is org_admin-only, enforced in the router
via `require_roles("org_admin")`. `GET /users/{id}` allows a caller to fetch their own
record too (spec §9) — that one exception is enforced here in `get_user` so the route
dependency can stay a plain `get_current_user`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import CurrentUser, hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.user import UserInviteRequest, UserUpdateRequest
from app.services.audit_service import AuditService
from app.utils.ids import to_public, to_public_list
from app.utils.passwords import generate_temp_password, without_password_hash
from app.utils.response import paginated


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        self.audit = AuditService(db)

    async def list_users(self, current_user: CurrentUser, pagination: PaginationParams) -> dict:
        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.repo.list_by_organization(
            current_user.organization_id,
            skip,
            pagination.page_size,
            search=pagination.search,
        )
        clean_items = to_public_list([without_password_hash(d) for d in items])
        return paginated(clean_items, pagination.page, pagination.page_size, total)

    async def invite_user(
        self,
        current_user: CurrentUser,
        payload: UserInviteRequest,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict:
        if await self.repo.find_by_email(payload.email) is not None:
            raise AppError.conflict("A user with this email already exists", "EMAIL_TAKEN")

        # No SMTP provider is configured for this deployment (CONTRACTS.md §8 —
        # notification_service's email/SMS sending is a clearly-marked no-op logger seam).
        # Documented v1 behavior: generate the temporary password server-side and return it
        # once, directly in this endpoint's response, so the inviting org_admin can relay it
        # to the new teammate out-of-band. A deployment with real email configured would
        # send this instead of returning it; this response field is v1's stand-in for that.
        temp_password = generate_temp_password()
        doc = {
            "name": payload.name,
            "email": payload.email,
            "passwordHash": hash_password(temp_password),
            "googleId": None,
            "avatarUrl": None,
            "role": payload.role,
            "organizationId": current_user.organization_id,
            "isActive": True,
            "emailVerifiedAt": None,
        }
        inserted = await self.repo.insert(doc)

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="USER_INVITED",
            resource_type="user",
            resource_id=inserted["_id"],
            metadata={"role": payload.role},
            ip=ip,
            user_agent=user_agent,
        )

        public = to_public(without_password_hash(inserted))
        public["temporaryPassword"] = temp_password
        return public

    async def get_user(self, current_user: CurrentUser, user_id: str) -> dict:
        if current_user.role != "org_admin" and current_user.id != user_id:
            raise AppError.forbidden()

        doc = await self.repo.find_by_id(user_id)
        if doc is None or doc.get("organizationId") != current_user.organization_id:
            raise AppError.not_found("User not found")

        return to_public(without_password_hash(doc))

    async def update_user(
        self,
        current_user: CurrentUser,
        user_id: str,
        payload: UserUpdateRequest,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict:
        doc = await self.repo.find_by_id(user_id)
        if doc is None or doc.get("organizationId") != current_user.organization_id:
            raise AppError.not_found("User not found")

        update: dict[str, Any] = {}
        if payload.name is not None:
            update["name"] = payload.name
        if payload.role is not None:
            update["role"] = payload.role
        if payload.is_active is not None:
            update["isActive"] = payload.is_active

        previous_role = doc.get("role")
        result_doc = doc
        if update:
            result_doc = await self.repo.update(user_id, update)

        if payload.role is not None and payload.role != previous_role:
            await self.audit.log(
                organization_id=current_user.organization_id,
                user_id=current_user.id,
                action="PERMISSION_CHANGED",
                resource_type="user",
                resource_id=user_id,
                metadata={"fromRole": previous_role, "toRole": payload.role},
                ip=ip,
                user_agent=user_agent,
            )

        return to_public(without_password_hash(result_doc))

    async def delete_user(
        self,
        current_user: CurrentUser,
        user_id: str,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        if user_id == current_user.id:
            raise AppError.bad_request("You cannot remove your own account", "CANNOT_REMOVE_SELF")

        doc = await self.repo.find_by_id(user_id)
        if doc is None or doc.get("organizationId") != current_user.organization_id:
            raise AppError.not_found("User not found")

        await self.repo.delete(user_id)

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="USER_DELETED",
            resource_type="user",
            resource_id=user_id,
            ip=ip,
            user_agent=user_agent,
        )
