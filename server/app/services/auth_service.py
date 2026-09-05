"""Business logic for the auth domain (CONTRACTS.md §2, §9, §12).

AI safety note (repo-wide convention, not specific to auth): nothing in this module ever
touches AI-generated content, but it is the gate that decides *who* is allowed to review
and finalize it later — so RBAC roles assigned here (`org_admin`/`doctor`) matter
downstream in the reports domain.

Cross-domain dependencies used here exactly as documented in CONTRACTS.md §12 —
`OrganizationRepository`, `UserRepository`, `SessionRepository`, `PasswordResetRepository`,
`TemplateService.ensure_default_template`, `AuditService.log` — are either already built or
being built in parallel; this module imports them by the exact names/signatures given there.

Refresh tokens are opaque random strings (`generate_refresh_token()`); only their sha256
hash (`hash_refresh_token()`) is ever persisted, in `sessions`, and every `/refresh` call
rotates the token (old one revoked, new one issued) so a stolen-but-unused old token stops
working the moment the legitimate client refreshes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.subscription import with_access
from app.core.logging import get_logger
from app.core.security import (
    CurrentUser,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
)
from app.services.audit_service import AuditService
from app.services.template_service import TemplateService
from app.utils.ids import new_id, to_public
from app.utils.passwords import without_password_hash

logger = get_logger(__name__)

# No SMTP is configured in v1 (CONTRACTS.md §8) — a reset link stays valid for this long
# before the caller has to request a new one.
_PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserRepository(db)
        self.orgs = OrganizationRepository(db)
        self.sessions = SessionRepository(db)
        self.password_resets = PasswordResetRepository(db)
        self.templates = TemplateService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def provision_org_and_admin_user(
        self,
        *,
        organization_name: str,
        name: str,
        email: str,
        password_hash: str | None,
        google_id: str | None,
        avatar_url: str | None,
        email_verified: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """New-org bootstrap shared by signup and first-time Google sign-in: the creator
        always gets `org_admin` (CONTRACTS.md §2), and every new org gets a default report
        template via `TemplateService.ensure_default_template` (idempotent, CONTRACTS.md §12).

        Every new org also starts a free trial (`app/core/subscription.py` enforces it):
        `settings.trial_days` days, capped at `settings.trial_daily_report_limit` AI reports
        per day while trialing. Generating reports after the trial ends requires paying via
        `app/api/billing/routes.py`."""
        org_id = new_id()
        user_id = new_id()

        org_doc: dict[str, Any] = {
            "_id": org_id,
            "name": organization_name,
            "logoUrl": None,
            "address": None,
            "contactEmail": None,
            "contactPhone": None,
            "website": None,
            "plan": "free",
            "highAccuracyMode": False,
            "reportHeader": None,
            "reportFooter": None,
            "primaryColor": None,
            "createdBy": user_id,
            "subscriptionStatus": "trial",
            "trialEndsAt": datetime.now(timezone.utc) + timedelta(days=settings.trial_days),
            "stripeCustomerId": None,
            "stripeSubscriptionId": None,
        }
        await self.orgs.insert(org_doc)

        user_doc: dict[str, Any] = {
            "_id": user_id,
            "name": name,
            "email": email,
            "passwordHash": password_hash,
            "googleId": google_id,
            "avatarUrl": avatar_url,
            "role": "org_admin",
            "organizationId": org_id,
            "isActive": True,
            "emailVerifiedAt": datetime.now(timezone.utc).isoformat() if email_verified else None,
        }
        await self.users.insert(user_doc)

        await self.templates.ensure_default_template(org_id, organization_name, user_id)
        return user_doc, org_doc

    async def _create_tokens(self, user_doc: dict[str, Any], *, user_agent: str | None) -> dict[str, str]:
        access_token = create_access_token(
            user_id=user_doc["_id"], organization_id=user_doc["organizationId"], role=user_doc["role"]
        )
        raw_refresh_token = generate_refresh_token()
        await self.sessions.create_session(
            user_doc["_id"], hash_refresh_token(raw_refresh_token), refresh_token_expiry(), user_agent
        )
        return {"accessToken": access_token, "refreshToken": raw_refresh_token}

    @staticmethod
    def _auth_payload(tokens: dict[str, str], user_doc: dict[str, Any], org_doc: dict[str, Any]) -> dict[str, Any]:
        return {
            **tokens,
            "user": to_public(without_password_hash(user_doc)),
            "organization": to_public(with_access(org_doc)),
        }

    async def _verify_google_id_token(self, raw_id_token: str) -> dict[str, Any]:
        if not settings.google_client_id:
            raise AppError.bad_request("Google sign-in is not configured", "GOOGLE_NOT_CONFIGURED")
        try:
            # `verify_oauth2_token` does a (cached) blocking HTTP call to fetch Google's
            # public certs — offload it so it never blocks the event loop.
            return await asyncio.to_thread(
                google_id_token.verify_oauth2_token,
                raw_id_token,
                google_requests.Request(),
                settings.google_client_id,
            )
        except ValueError as exc:
            raise AppError.unauthorized("Invalid Google credential", "GOOGLE_TOKEN_INVALID") from exc

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    async def signup(self, payload: SignupRequest, *, ip: str | None, user_agent: str | None) -> dict[str, Any]:
        if await self.users.find_by_email(payload.email) is not None:
            raise AppError.conflict("An account with this email already exists", "EMAIL_TAKEN")

        user_doc, org_doc = await self.provision_org_and_admin_user(
            organization_name=payload.organization_name,
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            google_id=None,
            avatar_url=None,
            email_verified=False,
        )
        tokens = await self._create_tokens(user_doc, user_agent=user_agent)

        await self.audit.log(
            organization_id=org_doc["_id"],
            user_id=user_doc["_id"],
            action="USER_SIGNUP",
            resource_type="user",
            resource_id=user_doc["_id"],
            metadata={"method": "password"},
            ip=ip,
            user_agent=user_agent,
        )
        return self._auth_payload(tokens, user_doc, org_doc)

    async def login(self, payload: LoginRequest, *, ip: str | None, user_agent: str | None) -> dict[str, Any]:
        user_doc = await self.users.find_by_email(payload.email)
        if not user_doc or not user_doc.get("passwordHash") or not verify_password(payload.password, user_doc["passwordHash"]):
            # Same generic error for "no such account" and "wrong password" (no account
            # enumeration via the login path either).
            raise AppError.unauthorized("Invalid email or password", "INVALID_CREDENTIALS")
        if not user_doc.get("isActive", True):
            raise AppError.unauthorized("This account has been deactivated", "ACCOUNT_DEACTIVATED")

        # system_admin (CONTRACTS.md §2a) has no organizationId — a platform-wide account,
        # not a member of any one tenant. Every other role always has a real org.
        org_doc = None
        if user_doc["organizationId"] is not None:
            org_doc = await self.orgs.find_by_id(user_doc["organizationId"])
            if org_doc is None:
                raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

        tokens = await self._create_tokens(user_doc, user_agent=user_agent)

        # No org-scoped audit trail makes sense for a platform-wide login — skip rather
        # than violate audit_logs.organizationId's NOT NULL constraint. A dedicated
        # platform-level audit log is a reasonable future addition, not built here.
        if user_doc["organizationId"] is not None:
            await self.audit.log(
                organization_id=user_doc["organizationId"],
                user_id=user_doc["_id"],
                action="USER_LOGIN",
                resource_type="user",
                resource_id=user_doc["_id"],
                metadata={"method": "password"},
                ip=ip,
                user_agent=user_agent,
            )
        return self._auth_payload(tokens, user_doc, org_doc)

    async def google_auth(self, payload: GoogleAuthRequest, *, ip: str | None, user_agent: str | None) -> dict[str, Any]:
        idinfo = await self._verify_google_id_token(payload.id_token)
        google_id = idinfo.get("sub")
        email = idinfo.get("email")
        if not google_id or not email:
            raise AppError.unauthorized("Invalid Google credential", "GOOGLE_TOKEN_INVALID")
        name = idinfo.get("name") or email.split("@")[0]
        avatar_url = idinfo.get("picture")

        is_new = False
        user_doc = await self.users.find_by_google_id(google_id)
        if user_doc is None:
            user_doc = await self.users.find_by_email(email)
            if user_doc is not None:
                # Existing password-based account signing in with Google for the first
                # time: link the Google identity rather than creating a duplicate account.
                user_doc = await self.users.update(
                    user_doc["_id"],
                    {"googleId": google_id, "avatarUrl": user_doc.get("avatarUrl") or avatar_url},
                )

        if user_doc is None:
            is_new = True
            organization_name = payload.organization_name or f"{name}'s Organization"
            user_doc, org_doc = await self.provision_org_and_admin_user(
                organization_name=organization_name,
                name=name,
                email=email,
                password_hash=None,
                google_id=google_id,
                avatar_url=avatar_url,
                email_verified=True,
            )
        else:
            if not user_doc.get("isActive", True):
                raise AppError.unauthorized("This account has been deactivated", "ACCOUNT_DEACTIVATED")
            org_doc = await self.orgs.find_by_id(user_doc["organizationId"])
            if org_doc is None:
                raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

        tokens = await self._create_tokens(user_doc, user_agent=user_agent)

        await self.audit.log(
            organization_id=user_doc["organizationId"],
            user_id=user_doc["_id"],
            action="USER_SIGNUP" if is_new else "USER_LOGIN",
            resource_type="user",
            resource_id=user_doc["_id"],
            metadata={"method": "google"},
            ip=ip,
            user_agent=user_agent,
        )
        return self._auth_payload(tokens, user_doc, org_doc)

    async def refresh(self, payload: RefreshRequest) -> dict[str, str]:
        token_hash = hash_refresh_token(payload.refresh_token)
        session_doc = await self.sessions.find_valid(token_hash)
        if session_doc is None:
            raise AppError.unauthorized("Invalid or expired refresh token", "REFRESH_TOKEN_INVALID")

        user_doc = await self.users.find_by_id(session_doc["userId"])
        if user_doc is None or not user_doc.get("isActive", True):
            raise AppError.unauthorized("Account not found or deactivated", "ACCOUNT_DEACTIVATED")

        # Rotate on every call: revoke the token just used, then issue a brand-new one.
        await self.sessions.revoke(token_hash)
        return await self._create_tokens(user_doc, user_agent=session_doc.get("userAgent"))

    async def logout(
        self, payload: LogoutRequest, *, current_user: CurrentUser, ip: str | None, user_agent: str | None
    ) -> None:
        await self.sessions.revoke(hash_refresh_token(payload.refresh_token))
        # See login()'s identical comment: no org-scoped audit trail for a system_admin
        # (organization_id=None) — skip rather than violate the NOT NULL constraint.
        if current_user.organization_id is not None:
            await self.audit.log(
                organization_id=current_user.organization_id,
                user_id=current_user.id,
                action="USER_LOGOUT",
                resource_type="user",
                resource_id=current_user.id,
                ip=ip,
                user_agent=user_agent,
            )

    async def get_me(self, current_user: CurrentUser) -> dict[str, Any]:
        user_doc = await self.users.find_by_id(current_user.id)
        if user_doc is None:
            raise AppError.not_found("User not found")
        org_doc = None
        if current_user.organization_id is not None:
            org_doc = await self.orgs.find_by_id(current_user.organization_id)
            if org_doc is None:
                raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")
        # `access` (evaluated writability — app/core/subscription.py) rides along on the org
        # so the client can show its read-only banner without a second request.
        return {"user": to_public(without_password_hash(user_doc)), "organization": to_public(with_access(org_doc))}

    async def forgot_password(self, payload: ForgotPasswordRequest) -> None:
        user_doc = await self.users.find_by_email(payload.email)
        if user_doc is not None:
            raw_token = generate_refresh_token()
            expires_at = datetime.now(timezone.utc) + _PASSWORD_RESET_TOKEN_TTL
            await self.password_resets.create_token(user_doc["_id"], hash_refresh_token(raw_token), expires_at)

            # --- SEAM: no SMTP is configured in v1 (CONTRACTS.md §8 — notification_service's
            # email sending is a clearly-marked no-op for now). A real deployment would send
            # this link by email here instead; until then we log it so it's usable in dev.
            # Only the id/link (no clinical data, no password) is ever logged — spec §31.
            reset_link = f"{settings.client_url}/reset-password?token={raw_token}"
            logger.info("Password reset requested: userId=%s resetLink=%s", user_doc["_id"], reset_link)

            await self.audit.log(
                organization_id=user_doc["organizationId"],
                user_id=user_doc["_id"],
                action="PASSWORD_RESET_REQUESTED",
                resource_type="user",
                resource_id=user_doc["_id"],
            )
        # No account enumeration: behave identically whether or not the email exists.

    async def reset_password(self, payload: ResetPasswordRequest) -> None:
        token_hash = hash_refresh_token(payload.token)
        record = await self.password_resets.find_valid(token_hash)
        if record is None:
            raise AppError.bad_request("This password reset link is invalid or has expired", "RESET_TOKEN_INVALID")

        user_doc = await self.users.find_by_id(record["userId"])
        if user_doc is None:
            raise AppError.bad_request("This password reset link is invalid or has expired", "RESET_TOKEN_INVALID")

        await self.users.update(user_doc["_id"], {"passwordHash": hash_password(payload.new_password)})
        await self.password_resets.consume(token_hash)
        # Password reset invalidates every existing session, everywhere.
        await self.sessions.revoke_all_for_user(user_doc["_id"])

        await self.audit.log(
            organization_id=user_doc["organizationId"],
            user_id=user_doc["_id"],
            action="PASSWORD_RESET_COMPLETED",
            resource_type="user",
            resource_id=user_doc["_id"],
        )

    async def change_password(self, current_user: CurrentUser, payload: ChangePasswordRequest) -> None:
        user_doc = await self.users.find_by_id(current_user.id)
        if user_doc is None:
            raise AppError.not_found("User not found")
        if not user_doc.get("passwordHash") or not verify_password(payload.current_password, user_doc["passwordHash"]):
            raise AppError.unauthorized("Current password is incorrect", "INVALID_CREDENTIALS")

        await self.users.update(user_doc["_id"], {"passwordHash": hash_password(payload.new_password)})
        # Changing a password invalidates every other logged-in session.
        await self.sessions.revoke_all_for_user(current_user.id)

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="PASSWORD_CHANGED",
            resource_type="user",
            resource_id=current_user.id,
        )
