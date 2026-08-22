"""Dashboard aggregate stats + recent-activity feed (CONTRACTS.md §9).

Read-only, org-scoped rollups over `studies`, `reports`, and `analysis_jobs`. Per the build
note for this domain, no dedicated repository class is needed here — just a few
`count()`/`select()` queries directly against the SQLAlchemy models in
`app.database.models`, always filtered by `organizationId` (never a client-supplied org id
— callers pass `current_user.organization_id`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AnalysisJob, AuditLog, Report, Study
from app.utils.ids import to_public_list

# Report statuses considered "still in the human/AI review pipeline" vs. "done" (CONTRACTS.md
# §4 `reports.status` enum: ai_generated|pending_review|draft|doctor_modified|finalized|amended).
_PENDING_REVIEW_STATUSES = ("ai_generated", "pending_review")
_COMPLETED_REPORT_STATUSES = ("finalized", "amended")

# analysis_jobs statuses that mean "AI is actively working" (CONTRACTS.md §4 `analysis_jobs.status`).
_AI_PROCESSING_STATUSES = ("queued", "preprocessing", "analyzing", "generating_report")

_RECENT_ITEMS_LIMIT = 5
_RECENT_ACTIVITY_LIMIT = 10


def _start_of_current_week(now: datetime) -> datetime:
    """Monday 00:00:00 UTC of the current ISO week."""
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_current_month(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _study_summary(row: Study) -> dict[str, Any]:
    # Lean projection for the "recent studies" dashboard widget — this is a summary
    # rollup, not the studies detail view, so free-text clinical fields are left out.
    return {
        "_id": row.id,
        "patientId": row.patient_id,
        "modality": row.modality,
        "bodyPart": row.body_part,
        "status": row.status,
        "studyDate": row.study_date,
        "assignedDoctorId": row.assigned_doctor_id,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


def _report_summary(row: Report) -> dict[str, Any]:
    return {
        "_id": row.id,
        "studyId": row.study_id,
        "templateId": row.template_id,
        "status": row.status,
        "currentVersion": row.current_version,
        "finalizedBy": row.finalized_by,
        "finalizedAt": row.finalized_at,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_stats(self, organization_id: str) -> dict[str, Any]:
        """Backs `GET /dashboard/stats`: the headline counters plus small "recent studies"/
        "recent reports" lists for the dashboard widgets."""
        now = datetime.now(timezone.utc)
        week_start = _start_of_current_week(now)
        month_start = _start_of_current_month(now)

        async def count(model: type[Any], *conditions: Any) -> int:
            stmt = select(func.count()).select_from(model).where(model.organization_id == organization_id, *conditions)
            return (await self.db.execute(stmt)).scalar_one()

        total_studies = await count(Study)
        pending_review = await count(Report, Report.status.in_(_PENDING_REVIEW_STATUSES))
        ai_processing = await count(AnalysisJob, AnalysisJob.status.in_(_AI_PROCESSING_STATUSES))
        completed_reports = await count(Report, Report.status.in_(_COMPLETED_REPORT_STATUSES))
        reports_this_week = await count(Report, Report.created_at >= week_start)
        reports_this_month = await count(Report, Report.created_at >= month_start)

        recent_studies = (
            await self.db.execute(
                select(Study)
                .where(Study.organization_id == organization_id)
                .order_by(Study.created_at.desc())
                .limit(_RECENT_ITEMS_LIMIT)
            )
        ).scalars().all()
        recent_reports = (
            await self.db.execute(
                select(Report)
                .where(Report.organization_id == organization_id)
                .order_by(Report.created_at.desc())
                .limit(_RECENT_ITEMS_LIMIT)
            )
        ).scalars().all()

        return {
            "totalStudies": total_studies,
            "pendingReview": pending_review,
            "aiProcessing": ai_processing,
            "completedReports": completed_reports,
            "reportsThisWeek": reports_this_week,
            "reportsThisMonth": reports_this_month,
            "recentStudies": to_public_list([_study_summary(r) for r in recent_studies]),
            "recentReports": to_public_list([_report_summary(r) for r in recent_reports]),
        }

    async def get_recent_activity(
        self, organization_id: str, limit: int = _RECENT_ACTIVITY_LIMIT
    ) -> list[dict[str, Any]]:
        """Backs `GET /dashboard/recent-activity`: a lightweight activity feed built from the
        most recent `audit_logs` entries for the org. Those entries already carry only
        ids/enums/small non-PHI metadata (CONTRACTS.md §4/§31), so they're safe to surface
        to the dashboard as-is."""
        rows = (
            await self.db.execute(
                select(AuditLog)
                .where(AuditLog.organization_id == organization_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        items = [
            {
                "_id": row.id,
                "organizationId": row.organization_id,
                "userId": row.user_id,
                "action": row.action,
                "resourceType": row.resource_type,
                "resourceId": row.resource_id,
                "metadata": row.metadata_,
                "ip": row.ip,
                "userAgent": row.user_agent,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows
        ]
        return to_public_list(items)
