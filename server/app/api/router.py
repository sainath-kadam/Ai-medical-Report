"""The single aggregator for every `/api/v1/*` route. Domain routers are added here as
they're built — this file is intentionally the LAST thing touched when adding a new
domain module, to avoid two people/agents editing the same file at once. Each domain
module still owns and exports its own `router = APIRouter(prefix="/xxx", tags=["xxx"])`.
"""

from fastapi import APIRouter

from app.ai.base import is_ai_configured

router = APIRouter()


@router.get("/health")
async def health_check():
    from app.utils.response import ok

    return ok({"status": "ok", "aiConfigured": is_ai_configured()})


# --- Domain routers (added incrementally; each import is independent and order-agnostic) ---
from app.api.auth.routes import router as auth_router  # noqa: E402
from app.api.users.routes import router as users_router  # noqa: E402
from app.api.organizations.routes import router as organizations_router  # noqa: E402
from app.api.patients.routes import router as patients_router  # noqa: E402
from app.api.studies.routes import router as studies_router  # noqa: E402
from app.api.uploads.routes import router as uploads_router  # noqa: E402
from app.api.intake.routes import router as intake_router  # noqa: E402
from app.api.analysis.routes import router as analysis_router  # noqa: E402
from app.api.reports.routes import router as reports_router  # noqa: E402
from app.api.templates.routes import router as templates_router  # noqa: E402
from app.api.dashboard.routes import router as dashboard_router  # noqa: E402
from app.api.audit_logs.routes import router as audit_logs_router  # noqa: E402
from app.api.notifications.routes import router as notifications_router  # noqa: E402
from app.api.billing.routes import router as billing_router  # noqa: E402
from app.api.platform.routes import router as platform_router  # noqa: E402

router.include_router(auth_router)
router.include_router(users_router)
router.include_router(organizations_router)
router.include_router(patients_router)
router.include_router(studies_router)
router.include_router(uploads_router)
router.include_router(intake_router)
router.include_router(analysis_router)
router.include_router(reports_router)
router.include_router(templates_router)
router.include_router(dashboard_router)
router.include_router(audit_logs_router)
router.include_router(notifications_router)
router.include_router(billing_router)
router.include_router(platform_router)
