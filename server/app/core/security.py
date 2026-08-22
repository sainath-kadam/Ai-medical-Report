"""Password hashing, JWT access tokens, opaque refresh tokens, and centralized RBAC.

Every organization-scoped route depends on `get_current_user` (never trusts a client-
supplied organization id) and, where relevant, `require_roles(...)`. This is what makes
the multi-tenant isolation guarantee (spec §7) and the RBAC matrix (spec §8, mirrored in
CONTRACTS.md §3) enforceable from one place instead of being re-implemented per route.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.exceptions import AppError

Role = Literal["org_admin", "doctor", "system_admin"]

# Roles an org_admin may assign via POST /users (invite) or PATCH /users/{id} (role
# change) — deliberately narrower than `Role`. `system_admin` is a platform-wide account
# with no organization_id (see `app/database/models.py::User`); an org_admin granting that
# from inside their own org would be a privilege escalation, so the two invite/update
# schemas type their `role` field as this, not `Role` — see `app/schemas/user.py`.
InvitableRole = Literal["org_admin", "doctor"]

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen for accounts we created) — fail closed.
        return False


# ---------------------------------------------------------------------------
# Access tokens (short-lived JWT)
# ---------------------------------------------------------------------------


def create_access_token(*, user_id: str, organization_id: str | None, role: Role) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "orgId": organization_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AppError.unauthorized("Session expired, please sign in again", "TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError.unauthorized("Invalid authentication token", "TOKEN_INVALID") from exc
    if payload.get("type") != "access":
        raise AppError.unauthorized("Invalid authentication token", "TOKEN_INVALID")
    return payload


# ---------------------------------------------------------------------------
# Refresh tokens (opaque random string; only the sha256 hash is ever persisted,
# in the `sessions` collection — see repositories/session_repository.py)
# ---------------------------------------------------------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_days)


# ---------------------------------------------------------------------------
# Current-user dependency
# ---------------------------------------------------------------------------


class CurrentUser(BaseModel):
    id: str
    # None only for role="system_admin" — see app/database/models.py::User. Every
    # org-scoped repository method requires a real string, so this being None is never a
    # silent gap in tenant isolation: a system_admin simply can't reach those routes.
    organization_id: str | None
    role: Role
    email: str
    name: str
    is_active: bool = True


_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise AppError.unauthorized("Missing or malformed Authorization header")

    payload = decode_access_token(credentials.credentials)

    # Imported lazily to avoid a circular import (repositories import database models,
    # which don't depend on security, but keeping the dependency direction one-way is
    # cleaner).
    from app.repositories.user_repository import UserRepository

    user_doc = await UserRepository(db).find_by_id(payload["sub"])
    if not user_doc or not user_doc.get("isActive", True):
        raise AppError.unauthorized("Account not found or deactivated")

    current = CurrentUser(
        id=user_doc["_id"],
        organization_id=user_doc["organizationId"],
        role=user_doc["role"],
        email=user_doc["email"],
        name=user_doc["name"],
        is_active=user_doc.get("isActive", True),
    )
    request.state.current_user = current
    return current


def require_roles(*roles: Role):
    """Dependency factory: `Depends(require_roles("org_admin"))`. Must be used together
    with (after) `get_current_user` in the route signature."""

    async def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise AppError.forbidden()
        return current_user

    return _dependency


def require_admin_or_doctor():
    return require_roles("org_admin", "doctor")


# ---------------------------------------------------------------------------
# Signed URLs for the local storage provider (spec §14 — files are never public)
# ---------------------------------------------------------------------------


def sign_storage_key(key: str, expires_at: int) -> str:
    message = f"{key}:{expires_at}".encode("utf-8")
    digest = hashlib.sha256(settings.signed_url_secret.encode("utf-8") + message).hexdigest()
    return f"{expires_at}.{digest}"


def verify_storage_signature(key: str, token: str) -> bool:
    try:
        expires_at_str, digest = token.split(".", 1)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return False
    if datetime.now(timezone.utc).timestamp() > expires_at:
        return False
    expected = sign_storage_key(key, expires_at)
    return hmac.compare_digest(expected, token)
