"""Business logic for the reports domain (CONTRACTS.md §4/§9/§12; spec §22-25/§53).

`ReportService.apply_change_request(report_id, organization_id, instruction,
actor_user_id) -> dict` is the fixed cross-domain entry point (CONTRACTS.md §12) that
`ReportService.request_changes` now calls directly and awaits, in-request — there is no
background worker anymore (Redis/ARQ were removed; a prior version instead had
`app/workers/report_worker.py::run_change_request_job` resolve and call it by that exact
name). It is NOT given a job id (there was never one to forward), so this method locates
the most recently queued analysis_job for the report's study itself, mirroring the same
`_acquire_job`-style pattern `AnalysisService.run_analysis` already uses, so `GET
/analysis/jobs/{jobId}` keeps working as the progress-polling mechanism for this flow too
(CONTRACTS.md §7) without inventing a second job-tracking collection the schema doesn't
define.

Every list/get response embeds `study` (with `patient` and signed-URL `files` nested
inside it) and `template`, because the frontend's report views (`ReportCard`,
`ReportViewer`, the report-detail workspace) render patient/study context and a file
thumbnail directly off `report.study` — see `_enrich`. This mirrors how AnalysisService
already treats "assemble everything needed for a report" as this domain's job, just for
reads instead of writes.

SAFETY (spec §25/§53): `append_version` (via `ReportRepository`) is the ONLY way a
report's content ever changes — nothing here mutates `versions[i]` in place. A
`finalized` report is immutable: every mutating method below checks for it first and
raises `AppError.conflict`, matching spec §25's "finalized reports are immutable; a
correction creates an amendment" rule.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import (
    GeneratedContent,
    ReportSectionContent,
    StructuredFindings,
    StudyContext,
    TemplateSectionSpec,
    get_imaging_provider,
    get_report_provider,
)
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.security import CurrentUser
from app.repositories.analysis_job_repository import AnalysisJobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.template_repository import TemplateRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.report import ChangeRequestBody, ReportContentEdit
from app.services.audit_service import AuditService
from app.services.study_service import with_signed_urls
from app.storage import get_storage
from app.utils.ids import to_public
from app.utils.response import paginated

logger = get_logger(__name__)

_IMMUTABLE_STATUS = "finalized"


def _calculate_age(date_of_birth: str | None) -> int | None:
    """Same logic as `AnalysisService`'s helper — duplicated rather than imported across
    domains, since it's a two-line pure function and CONTRACTS.md doesn't define a shared
    `utils` home for it."""
    if not date_of_birth:
        return None
    from datetime import date

    try:
        dob = date.fromisoformat(str(date_of_birth)[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.reports = ReportRepository(db)
        self.studies = StudyRepository(db)
        self.patients = PatientRepository(db)
        self.templates = TemplateRepository(db)
        self.organizations = OrganizationRepository(db)
        self.users = UserRepository(db)
        self.jobs = AnalysisJobRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_reports(
        self,
        organization_id: str,
        pagination: PaginationParams,
        *,
        status: str | None = None,
        patient_id: str | None = None,
        modality: str | None = None,
    ) -> dict[str, Any]:
        extra_filter: dict[str, Any] = {}
        if status:
            extra_filter["status"] = status

        if patient_id or modality:
            study_ids = await self.studies.find_ids_matching(organization_id, patient_id=patient_id, modality=modality)
            if not study_ids:
                return paginated([], pagination.page, pagination.page_size, 0)
            extra_filter["studyId"] = {"$in": study_ids}

        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.reports.list_scoped(
            organization_id,
            extra_filter,
            sort=[("createdAt", -1)],
            skip=skip,
            limit=pagination.page_size,
        )
        enriched = [await self._enrich(item, organization_id) for item in items]
        return paginated(enriched, pagination.page, pagination.page_size, total)

    async def get_report(self, report_id: str, organization_id: str) -> dict[str, Any]:
        report = await self.reports.find_by_id_scoped(report_id, organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        return await self._enrich(report, organization_id)

    async def get_versions(self, report_id: str, organization_id: str) -> list[dict[str, Any]]:
        report = await self.reports.find_by_id_scoped(report_id, organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        return report.get("versions", [])

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def update_report(
        self,
        report_id: str,
        current_user: CurrentUser,
        payload: ReportContentEdit,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        """A doctor's manual edit of the current version's content — always appends a new
        version (spec §25), never mutates an existing one."""
        report = await self.reports.find_by_id_scoped(report_id, current_user.organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        self._require_not_finalized(report)

        current_content = self._latest_content(report)
        merged = {
            "summary": payload.summary if payload.summary is not None else current_content["summary"],
            "sections": (
                [s.model_dump(by_alias=True) for s in payload.sections]
                if payload.sections is not None
                else current_content["sections"]
            ),
            "impression": payload.impression if payload.impression is not None else current_content["impression"],
            "recommendations": (
                payload.recommendations if payload.recommendations is not None else current_content["recommendations"]
            ),
        }

        version = {
            "versionNumber": report["currentVersion"] + 1,
            "content": merged,
            "author": current_user.id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "changeRequestNote": None,
            "reason": "Manual edit",
            "aiModelUsed": None,
        }
        updated = await self.reports.append_version(report_id, current_user.organization_id, version, "doctor_modified")
        if not updated:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="REPORT_EDITED",
            resource_type="report",
            resource_id=report_id,
            metadata={"versionNumber": version["versionNumber"]},
            ip=ip,
            user_agent=user_agent,
        )
        return await self._enrich(updated, current_user.organization_id)

    async def request_changes(
        self,
        report_id: str,
        current_user: CurrentUser,
        payload: ChangeRequestBody,
    ) -> dict[str, Any]:
        """Runs the AI revision inline now (Redis/ARQ removed — see CLAUDE.md); this
        method used to only enqueue it to a background worker. Returns a `jobId` tracked
        on the SAME `analysis_jobs` table the study's own analysis uses (there is no
        separate job table for this flow), so `GET /analysis/jobs/{jobId}` is still the
        one polling endpoint for both — `ReportDetail.tsx` sees the job already
        `completed`/`failed` on its first poll instead of watching it progress."""
        report = await self.reports.find_by_id_scoped(report_id, current_user.organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        self._require_not_finalized(report)

        job = await self.jobs.insert(
            {
                "organizationId": current_user.organization_id,
                "studyId": report["studyId"],
                "status": "queued",
                "provider": None,
                "imagingModel": None,
                "reportModel": None,
                "inputHash": None,
                "error": None,
                "startedAt": None,
                "completedAt": None,
            }
        )
        job_id = job["_id"]

        # apply_change_request has no try/except of its own (it used to rely on the now-
        # deleted worker's) — mark the job failed here on any error, so the frontend's
        # poll still discovers it via GET /analysis/jobs/{jobId} instead of a raw 500.
        try:
            await self.apply_change_request(report_id, current_user.organization_id, payload.instruction, current_user.id)
        except Exception as exc:
            logger.error(
                "request_changes failed reportId=%s jobId=%s organizationId=%s errorType=%s",
                report_id, job_id, current_user.organization_id, type(exc).__name__,
            )
            try:
                await self.db.rollback()
                await self.jobs.update_scoped(
                    job_id,
                    current_user.organization_id,
                    {
                        "status": "failed",
                        "error": str(exc),
                        "completedAt": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception:
                logger.error("request_changes: failed to persist failure status, jobId=%s", job_id)

        return {"jobId": job_id}

    async def regenerate_report(
        self,
        report_id: str,
        current_user: CurrentUser,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        """Re-runs report GENERATION only (text-only, cheap — spec §18) from the study's
        existing `lastFindings`, appending a new version to the SAME report. This is the
        simpler of the two CONTRACTS.md-authorized options over re-running the full
        imaging pipeline via `AnalysisService` (which would create a brand-new Report
        document with its own id, awkward for a UI that's already looking at this one) —
        if the study was never analyzed, this fails with a clear error rather than
        silently doing nothing. Synchronous (not job-queued): a single text-generation
        call is fast enough not to need it, unlike the change-request flow which may also
        re-run image analysis."""
        report = await self.reports.find_by_id_scoped(report_id, current_user.organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        self._require_not_finalized(report)

        study, patient, template, organization = await self._load_context_docs(report, current_user.organization_id)
        findings = self._findings_from_study(study)
        if findings is None:
            raise AppError.bad_request(
                "This study has not been analyzed yet — run AI analysis before regenerating a report.",
                "STUDY_NOT_ANALYZED",
            )

        context = self._build_context(study, patient, image_bytes=None)
        sections = self._template_sections(template)
        high_accuracy = bool(organization.get("highAccuracyMode"))

        generated = await get_report_provider().generate(
            organization.get("name", ""), sections, context, findings, high_accuracy
        )

        version = {
            "versionNumber": report["currentVersion"] + 1,
            "content": self._content_dict(generated),
            "author": "ai",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "changeRequestNote": None,
            "reason": f"Regenerated by {current_user.name}",
            "aiModelUsed": generated.model_used,
        }
        updated = await self.reports.append_version(report_id, current_user.organization_id, version, "pending_review")
        if not updated:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="REPORT_REGENERATED",
            resource_type="report",
            resource_id=report_id,
            metadata={"versionNumber": version["versionNumber"], "modelUsed": generated.model_used},
            ip=ip,
            user_agent=user_agent,
        )
        return await self._enrich(updated, current_user.organization_id)

    async def finalize_report(
        self,
        report_id: str,
        current_user: CurrentUser,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        report = await self.reports.find_by_id_scoped(report_id, current_user.organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        self._require_not_finalized(report)

        updated = await self.reports.update_scoped(
            report_id,
            current_user.organization_id,
            {
                "status": "finalized",
                "finalizedBy": current_user.id,
                "finalizedAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        if not updated:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="REPORT_FINALIZED",
            resource_type="report",
            resource_id=report_id,
            ip=ip,
            user_agent=user_agent,
        )
        return await self._enrich(updated, current_user.organization_id)

    async def get_pdf_bytes(
        self,
        report_id: str,
        current_user: CurrentUser,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> bytes:
        report = await self.reports.find_by_id_scoped(report_id, current_user.organization_id)
        if not report:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")

        # Persisted under a key derived from (report, version, status) — status is part of
        # the key because build_report_pdf() renders a different banner for a non-finalized
        # report (spec §22/§53), so a report finalized after its PDF was first generated at
        # the same version must still get a freshly rendered copy, not the stale cached one.
        storage = get_storage()
        storage_key = f"pdf/{report_id}_v{report['currentVersion']}_{report['status']}.pdf"
        try:
            pdf_bytes = await storage.download(storage_key)
        except AppError as exc:
            if exc.code != "FILE_NOT_FOUND":
                raise
            from app.services.pdf_service import build_report_pdf

            study, patient, template, _organization = await self._load_context_docs(report, current_user.organization_id)
            content = self._latest_content(report)

            logo_bytes = None
            logo_key = (template.get("header") or {}).get("logoKey")
            if logo_key:
                try:
                    logo_bytes = await storage.download(logo_key)
                except AppError:
                    logo_bytes = None

            pdf_bytes = build_report_pdf(
                content=content,
                patient=to_public(patient),
                study=to_public(study),
                template=to_public(template),
                doctor_name=current_user.name,
                report_status=report["status"],
                report_id=report["_id"],
                version_number=report["currentVersion"],
                logo_bytes=logo_bytes,
            )
            await storage.upload(storage_key, pdf_bytes, "application/pdf")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="REPORT_DOWNLOADED",
            resource_type="report",
            resource_id=report_id,
            ip=ip,
            user_agent=user_agent,
        )
        return pdf_bytes

    # ------------------------------------------------------------------
    # Cross-domain entry point (CONTRACTS.md §12) — called by run_change_request_job.
    # ------------------------------------------------------------------

    async def apply_change_request(
        self, report_id: str, organization_id: str, instruction: str, actor_user_id: str
    ) -> dict[str, Any]:
        report = await self.reports.find_by_id(report_id)
        if not report or report.get("organizationId") != organization_id:
            raise AppError.not_found("Report not found", "REPORT_NOT_FOUND")
        if report["status"] == _IMMUTABLE_STATUS:
            # A change request that was queued before someone else finalized the report —
            # fail loudly rather than silently mutating an immutable record.
            raise AppError.conflict("This report has already been finalized", "REPORT_FINALIZED")

        study, patient, template, organization = await self._load_context_docs(report, organization_id)
        high_accuracy = bool(organization.get("highAccuracyMode"))
        sections = self._template_sections(template)

        report_provider = get_report_provider()
        classification = await report_provider.classify_change_request(instruction, sections)

        job = await self._latest_job_for_study(study["_id"], organization_id)

        if classification.formatting_only:
            # Formatting-only: reuse the existing findings, never re-run imaging analysis
            # (spec §24/§18 — don't spend more than the task requires).
            findings = self._findings_from_study(study)
            if findings is None:
                findings = StructuredFindings(observations=[], raw_summary="", analyzable=False, unanalyzable_reason="Study not yet analyzed")
            image_bytes = None
        else:
            if job:
                await self.jobs.update_scoped(job["_id"], organization_id, {"status": "analyzing"})
            files = study.get("files") or []
            image_bytes = None
            image_mime_type = None
            if files:
                image_bytes = await get_storage().download(files[0]["storageKey"])
                image_mime_type = files[0].get("mimeType")
            context_for_analysis = self._build_context(study, patient, image_bytes=image_bytes, image_mime_type=image_mime_type)
            findings = await get_imaging_provider().analyze(context_for_analysis, high_accuracy)
            await self.studies.set_last_findings(
                study["_id"],
                {
                    "observations": findings.observations,
                    "rawSummary": findings.raw_summary,
                    "analyzable": findings.analyzable,
                    "unanalyzableReason": findings.unanalyzable_reason,
                },
            )

        if job:
            await self.jobs.update_scoped(job["_id"], organization_id, {"status": "generating_report"})

        context = self._build_context(study, patient, image_bytes=None)
        previous_content = self._content_from_dict(self._latest_content(report))

        revised = await report_provider.revise(
            organization.get("name", ""),
            sections,
            context,
            findings,
            previous_content,
            instruction,
            classification,
            high_accuracy,
        )

        version = {
            "versionNumber": report["currentVersion"] + 1,
            "content": self._content_dict(revised),
            "author": "ai",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "changeRequestNote": instruction,
            "reason": None,
            "aiModelUsed": revised.model_used,
        }
        updated = await self.reports.append_version(report_id, organization_id, version, "pending_review")

        if job:
            await self.jobs.update_scoped(
                job["_id"],
                organization_id,
                {"status": "completed", "reportModel": revised.model_used, "completedAt": datetime.now(timezone.utc).isoformat()},
            )

        await self.audit.log(
            organization_id=organization_id,
            user_id=actor_user_id,
            action="REPORT_REGENERATED",
            resource_type="report",
            resource_id=report_id,
            metadata={"versionNumber": version["versionNumber"], "formattingOnly": classification.formatting_only},
        )
        return await self._enrich(updated, organization_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_not_finalized(self, report: dict[str, Any]) -> None:
        if report["status"] == _IMMUTABLE_STATUS:
            raise AppError.conflict(
                "This report has been finalized and is immutable. Create an amendment instead.",
                "REPORT_FINALIZED",
            )

    def _latest_content(self, report: dict[str, Any]) -> dict[str, Any]:
        current = report["currentVersion"]
        for v in report["versions"]:
            if v["versionNumber"] == current:
                return v["content"]
        return report["versions"][-1]["content"]

    def _content_from_dict(self, content: dict[str, Any]) -> GeneratedContent:
        return GeneratedContent(
            summary=content.get("summary", ""),
            sections=[ReportSectionContent(key=s["key"], title=s["title"], content=s["content"]) for s in content.get("sections", [])],
            impression=content.get("impression", ""),
            recommendations=content.get("recommendations", ""),
            model_used="",
        )

    def _content_dict(self, generated: GeneratedContent) -> dict[str, Any]:
        return {
            "summary": generated.summary,
            "sections": [{"key": s.key, "title": s.title, "content": s.content} for s in generated.sections],
            "impression": generated.impression,
            "recommendations": generated.recommendations,
        }

    def _findings_from_study(self, study: dict[str, Any]) -> StructuredFindings | None:
        raw = study.get("lastFindings")
        if not raw:
            return None
        return StructuredFindings(
            observations=raw.get("observations", []),
            raw_summary=raw.get("rawSummary", ""),
            analyzable=raw.get("analyzable", True),
            unanalyzable_reason=raw.get("unanalyzableReason"),
        )

    def _template_sections(self, template: dict[str, Any]) -> list[TemplateSectionSpec]:
        return [
            TemplateSectionSpec(
                key=s["key"], title=s["title"], order=s["order"], enabled=s.get("enabled", True), guidance=s.get("guidance")
            )
            for s in template.get("sections", [])
        ]

    def _build_context(
        self,
        study: dict[str, Any],
        patient: dict[str, Any],
        *,
        image_bytes: bytes | None,
        image_mime_type: str | None = None,
    ) -> StudyContext:
        return StudyContext(
            modality=study["modality"],
            body_part=study["bodyPart"],
            patient_age=_calculate_age(patient.get("dateOfBirth")),
            patient_sex=patient.get("sex"),
            clinical_history=study.get("clinicalHistory"),
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )

    async def _latest_job_for_study(self, study_id: str, organization_id: str) -> dict[str, Any] | None:
        pending, _ = await self.jobs.list_scoped(
            organization_id, {"studyId": study_id, "status": "queued"}, sort=[("createdAt", -1)], skip=0, limit=1
        )
        return pending[0] if pending else None

    async def _load_context_docs(
        self, report: dict[str, Any], organization_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        study = await self.studies.find_by_id_scoped(report["studyId"], organization_id)
        if not study:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")
        patient = await self.patients.find_by_id_scoped(study["patientId"], organization_id)
        if not patient:
            raise AppError.not_found("Patient not found", "PATIENT_NOT_FOUND")
        template = await self.templates.find_by_id_scoped(report["templateId"], organization_id)
        if not template:
            raise AppError.not_found("Report template not found", "TEMPLATE_NOT_FOUND")
        organization = await self.organizations.find_by_id(organization_id)
        if not organization:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")
        return study, patient, template, organization

    async def _enrich(self, report: dict[str, Any], organization_id: str) -> dict[str, Any]:
        """Attaches `study` (with `patient` and signed-URL `files` nested) and `template`
        onto a report dict for every read response — see this module's docstring."""
        public = to_public(report)
        study = await self.studies.find_by_id_scoped(report["studyId"], organization_id)
        if study:
            patient = await self.patients.find_by_id_scoped(study["patientId"], organization_id)
            study_public = to_public(with_signed_urls(study))
            if patient:
                study_public["patient"] = to_public(patient)
            public["study"] = study_public

            template = await self.templates.find_by_id_scoped(report["templateId"], organization_id)
            if template:
                public["template"] = to_public(template)
        return public
