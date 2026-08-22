"""Dashboard routes (CONTRACTS.md §9): `GET /dashboard/stats`, `GET /dashboard/recent-activity`.

Read-only summary/rollup endpoints. Any authenticated role may view the dashboard (RBAC
matrix, CONTRACTS.md §3, does not restrict this rollup itself — it only surfaces counts and
lean summaries of studies/reports/audit-log entries the org already has). Every query is
scoped to `current_user.organization_id` — never a client-supplied organization id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import CurrentUser, get_current_user
from app.services.dashboard_service import DashboardService
from app.utils.response import ok

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await DashboardService(db).get_stats(current_user.organization_id)
    return ok(stats)


@router.get("/recent-activity")
async def get_dashboard_recent_activity(
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await DashboardService(db).get_recent_activity(current_user.organization_id, limit)
    return ok(items)
