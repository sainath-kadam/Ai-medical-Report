"""Request-body validation for the users domain (CONTRACTS.md §9, §4). Responses are plain
dicts (repository docs run through `to_public()`), never built from a response model — see
CONTRACTS.md §1a and `app/services/user_service.py`.
"""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.security import InvitableRole
from app.schemas.common import CamelModel


class UserInviteRequest(CamelModel):
    """POST /users — an org_admin inviting a new teammate into their organization.
    `role` is deliberately `InvitableRole` (org_admin/doctor only), not the full `Role` —
    an org_admin granting `system_admin` (a platform-wide role with no organization) would
    be a privilege escalation."""

    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    role: InvitableRole


class UserUpdateRequest(CamelModel):
    """PATCH /users/{id} — role / isActive / name are the only mutable fields (CONTRACTS
    §9). All fields optional; only the ones provided are applied. `role` is `InvitableRole`
    for the same reason as `UserInviteRequest` above."""

    name: str | None = Field(None, min_length=1, max_length=200)
    role: InvitableRole | None = None
    is_active: bool | None = None
