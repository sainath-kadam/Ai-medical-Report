"""Request-body validation for the auth domain (CONTRACTS.md §2, §9). Responses are plain
dicts (never a response Pydantic model) — see CONTRACTS.md §1a and `app/services/auth_service.py`.
"""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.common import CamelModel


class SignupRequest(CamelModel):
    """POST /auth/signup — creates a brand-new Organization (role `org_admin` for the
    creator) plus a default report template. See `TemplateService.ensure_default_template`."""

    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    organization_name: str = Field(..., min_length=1, max_length=200)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class GoogleAuthRequest(CamelModel):
    """POST /auth/google — matches the existing `GoogleButton.tsx` payload shape exactly
    (CONTRACTS.md §2): `{idToken, organizationName?}`. `organization_name` is only used the
    first time this Google identity signs in (find-or-create, same as signup/login)."""

    id_token: str = Field(..., min_length=1)
    organization_name: str | None = Field(None, min_length=1, max_length=200)


class RefreshRequest(CamelModel):
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(CamelModel):
    refresh_token: str = Field(..., min_length=1)


class ForgotPasswordRequest(CamelModel):
    email: EmailStr


class ResetPasswordRequest(CamelModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
