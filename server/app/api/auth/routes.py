"""Auth domain routes (CONTRACTS.md §2, §9). No auth required on signup/login/google/
refresh/forgot-password/reset-password; auth required on logout/me/change-password.

Routers stay thin: parse the request, call `AuthService`, return `ok(...)`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import CurrentUser, get_current_user
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
from app.services.auth_service import AuthService
from app.utils.response import ok

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    """IP/user-agent captured by `RequestContextMiddleware`, forwarded to audit log calls
    (CONTRACTS.md §4 audit_logs `ip?`/`userAgent?`)."""
    return getattr(request.state, "client_ip", None), getattr(request.state, "user_agent", None)


@router.post("/signup", status_code=201)
async def signup(
    payload: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await AuthService(db).signup(payload, ip=ip, user_agent=user_agent)
    return ok(result, status_code=201)


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await AuthService(db).login(payload, ip=ip, user_agent=user_agent)
    return ok(result)


@router.post("/google")
async def google_auth(
    payload: GoogleAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await AuthService(db).google_auth(payload, ip=ip, user_agent=user_agent)
    return ok(result)


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await AuthService(db).refresh(payload)
    return ok(result)


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    await AuthService(db).logout(payload, current_user=current_user, ip=ip, user_agent=user_agent)
    return ok(None)


@router.get("/me")
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await AuthService(db).get_me(current_user)
    return ok(result)


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).forgot_password(payload)
    # Always the same response whether or not the email exists (no account enumeration).
    return ok({"success": True})


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).reset_password(payload)
    return ok(None)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).change_password(current_user, payload)
    return ok(None)
