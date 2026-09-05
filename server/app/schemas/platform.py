"""Request-body validation for the platform domain (new — not part of the original
CONTRACTS.md spec; see `app/api/platform/README.md`). Responses are plain dicts, never
these classes — see CONTRACTS.md §1a.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.common import CamelModel


class CreateOrganizationRequest(CamelModel):
    """POST /platform/organizations — system_admin only. Creates a new organization AND
    its first org_admin user in one call, the same two-part shape
    `AuthService._provision_org_and_admin_user` already builds for self-signup — there is
    no other way for a system_admin-created org to ever get a first user who can log in."""

    organization_name: str = Field(..., min_length=1, max_length=200)
    admin_name: str = Field(..., min_length=1, max_length=200)
    admin_email: EmailStr


class InviteSystemAdminRequest(CamelModel):
    """POST /platform/system-admins — system_admin only. Mirrors
    `UserInviteRequest` (users domain) but for platform-wide accounts, which have no
    organization and therefore can't go through that endpoint."""

    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr


class UpdateOrganizationAccessRequest(CamelModel):
    """PATCH /platform/organizations/{id}/access — system_admin only (CONTRACTS.md §2c).
    Partial update: only fields the client sends are applied (`exclude_unset`).

    - `access_ends_at`: grant a manual access period until this instant (e.g. paid by
      invoice); `null` clears it. Independent of the Stripe/trial state.
    - `is_suspended`: hard read-only switch, overrides everything else while true.
    - `access_note`: platform-team-only note; never shown to the organization's users.
    - `plan`: the org's plan label (`free|pro|enterprise`) — display-only today.
    """

    access_ends_at: datetime | None = None
    is_suspended: bool | None = None
    access_note: str | None = Field(None, max_length=2000)
    plan: Literal["free", "pro", "enterprise"] | None = None
