"""Business logic for the analysis domain (CONTRACTS.md §7/§9/§12; spec §16-24/§53).

`AnalysisService.run_analysis(study_id, organization_id) -> dict` is called directly,
in-request, by `POST /analysis/studies/{id}/analyze` (`app/api/analysis/routes.py`) —
there is no background worker (Redis/ARQ were removed; a prior version enqueued this to
one instead of blocking the request, per CONTRACTS.md §7's original "the HTTP request
never blocks on AI calls" requirement — no longer true, by request).

This service's signature carries no `job_id`/actor parameter (a leftover of the
worker-based design, kept because nothing needs a `job_id` param to call it), so it:
  - locates the `queued` job the route already created for this study (falling back to
    creating one itself, so `run_analysis` also works if ever invoked directly/in a test
    without going through the HTTP route first) instead of receiving the job id directly;
  - attributes the `AI_ANALYSIS_*` audit entries and the completion notification to the
    study's assigned doctor (falling back to whoever created the study if unassigned) —
    the person actually responsible for reviewing this study — rather than to "the user who
    clicked analyze", which this method has no way to know.

SAFETY (spec §53, reinforced by CONTRACTS.md §5): the report this method creates is always
inserted with `status="ai_generated"` and `author="ai"` on its one version — a licensed
clinician's explicit review/finalize action (owned by the `reports` domain, built in
parallel) is the only thing that can ever move it past that. Nothing here ever logs
clinical text, patient names, or file contents (spec §31) — audit metadata is ids/enums only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import (
    StudyContext,
    TemplateSectionSpec,
    get_imaging_provider,
    get_report_provider,
    resolve_generation_tier,
)
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.repositories.analysis_job_repository import AnalysisJobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.template_repository import TemplateRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.storage import get_storage
from app.utils.ids import to_public

logger = get_logger(__name__)

# Job statuses that mean "already running" for a study — a second analyze call while one
# of these is in flight would race the first on `study.status`/`study.lastFindings` and
# waste an AI call, so it's rejected outright rather than enqueued. Shared by
# `start_analysis` below and `POST /studies/intake` (via the same method).
_IN_FLIGHT_STATUSES = ("queued", "preprocessing", "analyzing", "generating_report")

# Mirrors the tier->model mapping `AnthropicImagingProvider`/`AnthropicReportProvider` use
# internally (`app/ai/providers/anthropic_provider.py::_MODEL_FOR_TIER`, private to that
# module) so the `analysis_jobs.imagingModel` field can be populated even though
# `StructuredFindings` itself doesn't carry a model name back (only `GeneratedContent`
# does, via `model_used`, which is used for `reportModel` directly). Only meaningful when
# `AI_PROVIDER=anthropic` — see `_resolve_imaging_model` for the provider-aware version.
_TIER_MODEL_MAP: dict[str, str] = {
    "fast": settings.ai_model_fast,
    "default": settings.ai_model_default,
    "highAccuracy": settings.ai_model_high_accuracy,
    "max": settings.ai_model_max,
}


def _resolve_imaging_model(tier: str) -> str:
    """`get_imaging_provider()` (app/ai/base.py) picks the actual provider from
    `AI_PROVIDER`; this mirrors that same selection just to get a display-only model name
    for `analysis_jobs.imagingModel` — it never affects which provider actually runs.
    Only Anthropic is tiered; Gemini is a single model for everything."""
    if not settings.ai_configured:
        return "mock"
    if settings.ai_provider == "gemini":
        return settings.gemini_model
    return _TIER_MODEL_MAP[tier]


def _calculate_age(date_of_birth: str | None) -> int | None:
    """`patients.dateOfBirth` is stored as an ISO date string (CONTRACTS.md §4); the AI
    context wants a plain integer age. Returns `None` rather than raising on a malformed or
    missing value — age is a helpful hint for the model, not something worth failing an
    entire analysis run over."""
    if not date_of_birth:
        return None
    try:
        dob = date.fromisoformat(str(date_of_birth)[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class AnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.jobs = AnalysisJobRepository(db)
        self.studies = StudyRepository(db)
        self.patients = PatientRepository(db)
        self.templates = TemplateRepository(db)
        self.organizations = OrganizationRepository(db)
        self.reports = ReportRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    # ------------------------------------------------------------------
    # Cross-domain entry point (CONTRACTS.md §12) — called by the analysis worker.
    # ------------------------------------------------------------------

    async def run_analysis(self, study_id: str, organization_id: str) -> dict[str, Any]:
        study = await self.studies.find_by_id_scoped(study_id, organization_id)
        if not study:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

        patient = await self.patients.find_by_id_scoped(study["patientId"], organization_id)
        if not patient:
            raise AppError.not_found("Patient not found", "PATIENT_NOT_FOUND")

        organization = await self.organizations.find_by_id(organization_id)
        if not organization:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

        template = None
        if study.get("templateId"):
            template = await self.templates.find_by_id_scoped(study["templateId"], organization_id)
        if not template:
            template = await self.templates.get_default(organization_id)
        if not template:
            raise AppError.not_found(
                "No report template is configured for this organization", "TEMPLATE_NOT_FOUND"
            )

        actor_user_id = study.get("assignedDoctorId") or study["createdBy"]
        high_accuracy = bool(organization.get("highAccuracyMode"))
        files = study.get("files") or []
        primary_file = files[0] if files else None

        job = await self._acquire_job(study_id, organization_id)
        job_id = job["_id"]

        input_hash = hashlib.sha256(
            json.dumps(
                {
                    "studyId": study_id,
                    "templateId": template["_id"],
                    "fileKeys": sorted(f["storageKey"] for f in files),
                    "studyUpdatedAt": study.get("updatedAt"),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        await self.audit.log(
            organization_id=organization_id,
            user_id=actor_user_id,
            action="AI_ANALYSIS_STARTED",
            resource_type="study",
            resource_id=study_id,
            metadata={"studyId": study_id, "jobId": job_id},
        )

        try:
            await self.studies.update_scoped(study_id, organization_id, {"status": "processing"})
            await self.jobs.update_scoped(
                job_id,
                organization_id,
                {
                    "status": "preprocessing",
                    "inputHash": input_hash,
                    "startedAt": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                },
            )

            image_bytes: bytes | None = None
            image_mime_type: str | None = None
            if primary_file:
                image_bytes = await get_storage().download(primary_file["storageKey"])
                image_mime_type = primary_file.get("mimeType")

            context = StudyContext(
                modality=study["modality"],
                body_part=study["bodyPart"],
                patient_age=_calculate_age(patient.get("dateOfBirth")),
                patient_sex=patient.get("sex"),
                clinical_history=study.get("clinicalHistory"),
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
            )

            await self.jobs.update_scoped(job_id, organization_id, {"status": "analyzing"})

            # No file on the study at all: still call the provider with an image-less
            # context rather than fabricating an "unanalyzable" result ourselves — every
            # `BaseMedicalImagingProvider` implementation is required (spec §53) to return
            # `analyzable=False`/`unanalyzableReason` instead of guessing when it has
            # nothing to look at, so the safety behavior lives in exactly one place.
            findings = await get_imaging_provider().analyze(context, high_accuracy)

            await self.studies.set_last_findings(
                study_id,
                {
                    "observations": findings.observations,
                    "rawSummary": findings.raw_summary,
                    "analyzable": findings.analyzable,
                    "unanalyzableReason": findings.unanalyzable_reason,
                },
            )

            tier = resolve_generation_tier(high_accuracy)
            imaging_model = _resolve_imaging_model(tier)
            await self.jobs.update_scoped(
                job_id, organization_id, {"status": "generating_report", "imagingModel": imaging_model}
            )

            sections = [
                TemplateSectionSpec(
                    key=section["key"],
                    title=section["title"],
                    order=section["order"],
                    enabled=section.get("enabled", True),
                    guidance=section.get("guidance"),
                )
                for section in template.get("sections", [])
            ]

            generated = await get_report_provider().generate(
                organization.get("name", ""), sections, context, findings, high_accuracy
            )

            version = {
                "versionNumber": 1,
                "content": {
                    "summary": generated.summary,
                    "sections": [
                        {"key": s.key, "title": s.title, "content": s.content} for s in generated.sections
                    ],
                    "impression": generated.impression,
                    "recommendations": generated.recommendations,
                },
                "author": "ai",
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "changeRequestNote": None,
                "reason": None,
                "aiModelUsed": generated.model_used,
            }
            report = await self.reports.insert(
                {
                    "organizationId": organization_id,
                    "studyId": study_id,
                    "templateId": template["_id"],
                    "versions": [version],
                    "currentVersion": 1,
                    "status": "ai_generated",
                    "finalizedBy": None,
                    "finalizedAt": None,
                }
            )

            await self.studies.update_scoped(study_id, organization_id, {"status": "completed"})

            await self.jobs.update_scoped(
                job_id,
                organization_id,
                {
                    "status": "completed",
                    "reportModel": generated.model_used,
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                },
            )

            await self.notifications.create(
                organization_id=organization_id,
                user_id=actor_user_id,
                type="analysis_completed",
                title="AI analysis complete",
                body=(
                    "The AI-assisted analysis for this study has finished. A preliminary, "
                    "AI-generated report is ready for your review — it is not a finalized "
                    "diagnosis until you review and approve it."
                ),
                link=f"/studies/{study_id}",
            )

            await self.audit.log(
                organization_id=organization_id,
                user_id=actor_user_id,
                action="AI_ANALYSIS_COMPLETED",
                resource_type="study",
                resource_id=study_id,
                metadata={"studyId": study_id, "jobId": job_id, "modelUsed": generated.model_used},
            )

            return to_public(report)

        except Exception as exc:
            # A DB-level failure earlier in this block (e.g. a constraint violation) leaves
            # the session's transaction needing a rollback before it can be used again —
            # unlike Mongo, where every operation was already its own independent,
            # never-poisoned call.
            await self.db.rollback()
            await self.studies.update_scoped(study_id, organization_id, {"status": "failed"})
            await self.jobs.update_scoped(
                job_id,
                organization_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                },
            )
            # ids/enums/type name only (spec §31) — never `str(exc)`, which could echo
            # back arbitrary input; the actual message is persisted on the job doc above,
            # where only org_admin/doctor can read it via the API, not the server log.
            logger.error(
                "Analysis job failed: jobId=%s studyId=%s organizationId=%s errorType=%s",
                job_id, study_id, organization_id, type(exc).__name__,
            )
            raise

    # ------------------------------------------------------------------
    # Route-facing entry point — shared by POST /analysis/studies/{id}/analyze and the
    # combined POST /studies/intake flow (StudyService.create_from_intake).
    # ------------------------------------------------------------------

    async def start_analysis(self, study_id: str, organization_id: str) -> dict[str, Any]:
        """Creates the `queued` analysis_job row, then runs `run_analysis` inline (see
        module docstring — no background worker exists). Returns `{jobId, report}`: `report`
        is the newly created draft (`to_public`-shaped) on success, or `None` if analysis
        failed — the exception itself is swallowed here (same as the old inline try/except
        in the route) so the caller still gets a `jobId` to poll/display, exactly as when a
        worker reported a failure asynchronously."""
        in_flight, _ = await self.jobs.list_scoped(
            organization_id,
            {"studyId": study_id, "status": {"$in": list(_IN_FLIGHT_STATUSES)}},
            sort=[("createdAt", -1)],
            skip=0,
            limit=1,
        )
        if in_flight:
            raise AppError.conflict(
                "An analysis is already in progress for this study", "ANALYSIS_ALREADY_IN_PROGRESS"
            )

        job = await self.jobs.insert(
            {
                "organizationId": organization_id,
                "studyId": study_id,
                "status": "queued",
                "provider": settings.ai_provider,
                "imagingModel": None,
                "reportModel": None,
                "inputHash": None,
                "error": None,
                "startedAt": None,
                "completedAt": None,
            }
        )
        job_id = job["_id"]

        report: dict[str, Any] | None = None
        try:
            report = await self.run_analysis(study_id, organization_id)
        except Exception:
            report = None

        return {"jobId": job_id, "report": report}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _acquire_job(self, study_id: str, organization_id: str) -> dict[str, Any]:
        """Finds the `queued` analysis_job the `POST /analysis/studies/{id}/analyze` route
        already created and handed to the worker (CONTRACTS.md §7/§9). `run_analysis`'s
        signature is fixed by CONTRACTS.md §12 to `(study_id, organization_id)` only, so it
        cannot be handed the job id directly — it locates the most recently created
        `queued` job for this study instead. Falls back to creating one so this method also
        works standalone (e.g. a direct/manual call that didn't go through the HTTP route
        first)."""
        pending, _ = await self.jobs.list_scoped(
            organization_id,
            {"studyId": study_id, "status": "queued"},
            sort=[("createdAt", -1)],
            skip=0,
            limit=1,
        )
        if pending:
            return pending[0]
        return await self.jobs.insert(
            {
                "organizationId": organization_id,
                "studyId": study_id,
                "status": "queued",
                "provider": settings.ai_provider,
                "imagingModel": None,
                "reportModel": None,
                "inputHash": None,
                "error": None,
                "startedAt": None,
                "completedAt": None,
            }
        )
