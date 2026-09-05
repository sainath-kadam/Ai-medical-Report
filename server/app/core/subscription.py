"""Organization access: who may *write* right now, and why (CONTRACTS.md §2a/§2c).

Two questions, answered from one evaluator so the platform page, the billing page, the
analysis gate and the read-only gate can never disagree:

- `evaluate_access(org)` -> `OrgAccess`: is this organization currently allowed to write
  (create/edit anything), for how long, and on what basis — a free trial (`trial`), a paid
  Stripe subscription (`subscription`), or an access period a system_admin granted by hand
  (`manual`, e.g. paid by invoice). A system_admin's `isSuspended` flag overrides all three.
- `require_writable_organization` — the ONE read-only gate. Attached at router level (see
  `app/api/router.py`) to every organization-scoped domain that has write routes; it lets
  GET/HEAD/OPTIONS through untouched and refuses any other method with **402** while the
  organization isn't writable, the error code being the reason (`TRIAL_EXPIRED` /
  `ACCESS_EXPIRED` / `ORGANIZATION_SUSPENDED`) so the analyze route's long-standing
  `TRIAL_EXPIRED` contract is unchanged. Users keep logging in and reading everything;
  `auth`/`billing` are deliberately not gated so an org can still pay its way back in.
- `require_active_subscription` — the stricter gate on creating a *new AI report*
  (`POST /analysis/studies/{id}/analyze`, and `POST /studies` when it also runs analysis):
  same writability rule, plus the per-UTC-day report cap while the basis is the free trial.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import CurrentUser, _bearer_scheme, decode_access_token, get_current_user
from app.database.models import Organization, Report

AccessSource = Literal["subscription", "manual", "trial", "none"]
AccessReason = Literal["ORGANIZATION_SUSPENDED", "ACCESS_EXPIRED", "TRIAL_EXPIRED"]

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class OrgAccess:
    writable: bool
    # Why writes are refused; None while writable.
    reason: AccessReason | None
    # What grants access right now (or "none").
    source: AccessSource
    # When the current grant ends; None for an open-ended Stripe subscription or when
    # there is no grant at all.
    ends_at: datetime | None

    def to_public(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "writable": data["writable"],
            "reason": data["reason"],
            "source": data["source"],
            "endsAt": self.ends_at.isoformat() if self.ends_at else None,
        }

    def message(self) -> str:
        ended = f" on {self.ends_at.date().isoformat()}" if self.ends_at else ""
        if self.reason == "ORGANIZATION_SUSPENDED":
            return "Your organization's access has been suspended by the platform administrator. You can view existing records but not make changes."
        if self.reason == "ACCESS_EXPIRED":
            return f"Your organization's access period ended{ended}. You can view existing records; contact the platform administrator or subscribe to resume."
        return f"Your free trial ended{ended}. You can view existing records; subscribe to keep working."


def _as_aware_utc(value: Any) -> datetime | None:
    """Accepts a datetime, an ISO string (repository dicts hand datetimes back as ISO
    strings) or None. SQLite (tests) drops tzinfo on `DateTime(timezone=True)` round-trips,
    unlike Postgres — normalize so comparisons never raise `TypeError: can't compare
    offset-naive and offset-aware datetimes` on one backend and not the other."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def evaluate_access(org: Any, now: datetime | None = None) -> OrgAccess:
    """Works on either an `Organization` row or the camelCase dict repositories return.
    Precedence: suspended > Stripe active > manual period > trial > nothing."""
    now = now or datetime.now(timezone.utc)
    get = (lambda k, d: getattr(org, k, d)) if not isinstance(org, dict) else (lambda k, d: org.get(_camel(k), d))

    if bool(get("is_suspended", False)):
        return OrgAccess(False, "ORGANIZATION_SUSPENDED", "none", None)
    if get("subscription_status", None) == "active":
        return OrgAccess(True, None, "subscription", None)
    access_ends_at = _as_aware_utc(get("access_ends_at", None))
    if access_ends_at is not None and now < access_ends_at:
        return OrgAccess(True, None, "manual", access_ends_at)
    trial_ends_at = _as_aware_utc(get("trial_ends_at", None))
    if get("subscription_status", None) == "trial" and trial_ends_at is not None and now < trial_ends_at:
        return OrgAccess(True, None, "trial", trial_ends_at)
    if access_ends_at is not None:
        return OrgAccess(False, "ACCESS_EXPIRED", "none", access_ends_at)
    return OrgAccess(False, "TRIAL_EXPIRED", "none", trial_ends_at)


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(part.title() for part in rest)


# Columns only a system_admin may see; stripped from everything an organization's own users
# receive (`/auth/me`, `/organizations/me`, login/signup payloads).
_PLATFORM_ONLY_FIELDS = ("accessNote",)


def with_access(org_doc: dict[str, Any] | None, *, include_platform_fields: bool = False) -> dict[str, Any] | None:
    """Attaches `access` (the evaluated `OrgAccess`) to an organization dict about to be
    returned to a client, so the frontend never re-implements the precedence above. Unless
    `include_platform_fields` (platform routes, system_admin only), platform-internal
    columns such as the access note are removed."""
    if org_doc is None:
        return None
    public = {**org_doc, "access": evaluate_access(org_doc).to_public()}
    if not include_platform_fields:
        for field in _PLATFORM_ONLY_FIELDS:
            public.pop(field, None)
    return public


async def require_writable_organization(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """Router-level read-only gate — see module docstring. Resolves the organization from
    the (signed) access token rather than via `get_current_user`, for two reasons: router
    dependencies run before the route's own, so `request.state.current_user` isn't set yet;
    and some routers carry a public, token-less GET (the signed file download) that must not
    suddenly demand a bearer token. A missing/invalid token is left for the route's own
    auth dependency to reject with its usual 401."""
    if request.method in _SAFE_METHODS:
        return
    credentials = await _bearer_scheme(request)
    if credentials is None or not credentials.credentials:
        return
    try:
        payload = decode_access_token(credentials.credentials)
    except AppError:
        return
    organization_id = payload.get("orgId")
    if not organization_id:  # system_admin — no organization to be read-only about
        return
    org = await db.get(Organization, organization_id)
    if org is None:
        return
    access = evaluate_access(org)
    if not access.writable:
        raise AppError.payment_required(access.message(), access.reason or "TRIAL_EXPIRED")


async def require_active_subscription(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Depends()-chain gate for routes that create a new AI report. Raises
    `AppError.payment_required` (402) if the organization isn't writable (reason code as
    the error code: `TRIAL_EXPIRED` / `ACCESS_EXPIRED` / `ORGANIZATION_SUSPENDED`);
    otherwise, while the basis is still the free trial, enforces the daily report cap."""
    org = await db.get(Organization, current_user.organization_id)
    if org is None:
        raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

    access = evaluate_access(org)
    if not access.writable:
        raise AppError.payment_required(access.message(), access.reason or "TRIAL_EXPIRED")
    if access.source != "trial":
        return current_user

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reports_today = (
        await db.execute(
            select(func.count())
            .select_from(Report)
            .where(Report.organization_id == current_user.organization_id, Report.created_at >= today_start)
        )
    ).scalar_one()
    if reports_today >= settings.trial_daily_report_limit:
        raise AppError.payment_required(
            f"Trial accounts are limited to {settings.trial_daily_report_limit} reports per day. "
            "Subscribe for unlimited reports.",
            "TRIAL_DAILY_LIMIT_REACHED",
        )

    return current_user
