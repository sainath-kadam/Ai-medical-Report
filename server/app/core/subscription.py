"""Trial/subscription gating (new — not part of the original CONTRACTS.md spec).

Every organization starts on a time- and volume-limited free trial at signup
(`AuthService._provision_org_and_admin_user` sets `subscriptionStatus="trial"`,
`trialEndsAt = now + settings.trial_days`). `require_active_subscription` is the one gate
applied where new AI reports get created (`POST /analysis/studies/{id}/analyze`): once the
trial window has passed and there's no active paid subscription, that route is blocked
(402) until the organization pays via `app/api/billing/routes.py`. While still inside the
trial window, report generation is capped at `settings.trial_daily_report_limit` per UTC
calendar day.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import CurrentUser, get_current_user
from app.database.models import Organization, Report


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """SQLite (used in tests, see `tests/conftest.py`) silently drops tzinfo on
    `DateTime(timezone=True)` round-trips, unlike Postgres — normalize before comparing so
    this comparison is correct on both backends instead of raising
    `TypeError: can't compare offset-naive and offset-aware datetimes` under SQLite."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def require_active_subscription(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Depends()-chain gate for routes that create a new AI report. Raises
    `AppError.payment_required` (402) if the trial has ended with no active paid
    subscription; otherwise, while still trialing, enforces the daily report cap."""
    org = await db.get(Organization, current_user.organization_id)
    if org is None:
        raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

    if org.subscription_status == "active":
        return current_user

    now = datetime.now(timezone.utc)
    trial_ends_at = _as_aware_utc(org.trial_ends_at)
    if org.subscription_status != "trial" or trial_ends_at is None or now >= trial_ends_at:
        raise AppError.payment_required(
            "Your free trial has ended. Subscribe to keep generating AI reports.", "TRIAL_EXPIRED"
        )

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
