"""Request-body schema for the organizations domain (CONTRACTS.md §9, §4).

Response bodies are plain dicts per §1a — there is intentionally no response model here.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class OrganizationUpdateRequest(CamelModel):
    """PATCH /organizations/me — org_admin only (enforced by the router, not here).

    Every field is optional: this is a partial update, so a client sends only the fields
    it wants to change. The router applies `exclude_unset=True` when serializing so
    fields the client omitted are left untouched rather than overwritten with `null`.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    logo_url: str | None = Field(None, max_length=1000)
    address: str | None = None
    contact_email: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=500)
    primary_color: str | None = Field(None, max_length=20)
    report_header: str | None = None
    report_footer: str | None = None
    high_accuracy_mode: bool | None = None
