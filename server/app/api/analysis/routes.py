"""Analysis domain routes (CONTRACTS.md §7/§9). `POST .../analyze` delegates to
`AnalysisService.start_analysis`, which creates the `analysis_job` record (status `queued`)
then runs `AnalysisService.run_analysis` inline, in-request — there is no background worker
(Redis/ARQ were removed, see CLAUDE.md; a prior version enqueued this to one instead of
blocking the request). `start_analysis` is shared with the combined `POST /studies/intake`
flow (`app/api/studies/routes.py`) so the in-flight check + job bookkeeping isn't
duplicated. The two GET routes are plain reads of the same `analysis_jobs` table so the
frontend's existing polling (`GET /analysis/jobs/{jobId}`) keeps working unchanged — it
just sees the job already `completed`/`failed` on its very first poll instead of watching
it progress.

RBAC (CONTRACTS.md §3): running AI analysis is restricted to `org_admin`/`doctor` and also
requires an active subscription or unused trial quota — see
`app/core/subscription.py::require_active_subscription`. The two GET routes are open to
any authenticated org member.

Routers stay thin: parse the request, call the service/repository, return `ok(...)`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.exceptions import AppError
from app.core.security import CurrentUser, get_current_user, require_admin_or_doctor
from app.core.subscription import require_active_subscription
from app.repositories.analysis_job_repository import AnalysisJobRepository
from app.repositories.study_repository import StudyRepository
from app.schemas.common import PaginationParams
from app.services.analysis_service import AnalysisService
from app.utils.ids import to_public, to_public_list
from app.utils.response import ok, paginated

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/studies/{study_id}/analyze", status_code=200)
async def analyze_study(
    study_id: str,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    _subscription: CurrentUser = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    study = await StudyRepository(db).find_by_id_scoped(study_id, current_user.organization_id)
    if not study:
        raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

    result = await AnalysisService(db).start_analysis(study_id, current_user.organization_id)
    return ok(result)


@router.get("/jobs/{job_id}")
async def get_analysis_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await AnalysisJobRepository(db).find_by_id_scoped(job_id, current_user.organization_id)
    if not job:
        raise AppError.not_found("Analysis job not found", "ANALYSIS_JOB_NOT_FOUND")
    return ok(to_public(job))


@router.get("/studies/{study_id}/jobs")
async def list_study_analysis_jobs(
    study_id: str,
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    study = await StudyRepository(db).find_by_id_scoped(study_id, current_user.organization_id)
    if not study:
        raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

    skip = (pagination.page - 1) * pagination.page_size
    items, total = await AnalysisJobRepository(db).list_scoped(
        current_user.organization_id,
        {"studyId": study_id},
        sort=[("createdAt", -1)],
        skip=skip,
        limit=pagination.page_size,
    )
    return ok(paginated(to_public_list(items), pagination.page, pagination.page_size, total))
