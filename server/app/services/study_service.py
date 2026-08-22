"""Business logic for the studies domain (CONTRACTS.md §4/§9/§12). Routers stay thin —
parse the request, call one of these methods, and hand the result to `ok(...)`.

RBAC (CONTRACTS.md §3): org_admin/doctor may both read/create/update/delete studies in
their own organization; `assignedDoctorId` (see `_ASSIGNABLE_REVIEWER_ROLES` below) just
records who's the reviewing clinician of record, it isn't an access-control field.

Multi-tenant isolation itself is never optional: every read/write below is filtered by
`organization_id` via `BaseRepository`'s `*_scoped` methods.
"""

from __future__ import annotations

from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import CurrentUser
from app.repositories.patient_repository import PatientRepository
from app.repositories.study_repository import StudyRepository
from app.repositories.template_repository import TemplateRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreateRequest
from app.schemas.study import StudyCreate, StudyUpdate
from app.services.analysis_service import AnalysisService
from app.services.audit_service import AuditService
from app.services.patient_service import PatientService
from app.services.upload_service import UploadService
from app.storage import get_storage
from app.utils.ids import to_public, to_public_list
from app.utils.response import paginated


def with_signed_urls(study: dict[str, Any]) -> dict[str, Any]:
    """Attaches a short-lived `signedUrl` to each embedded file so the frontend can render
    an `<img src=...>`/download link directly (spec §14 — never a public/static mount).
    Generating these is cheap (local HMAC or an S3 presign call, no I/O against the file
    itself), so it's done unconditionally on every single-study read.

    Public (no leading underscore) because it's the one shared place this transform
    happens — also used by `ReportService._enrich` (a report's embedded `study.files`)
    and `app/api/uploads/routes.py` (the freshly-updated study returned after an upload),
    rather than each duplicating the same `{**f, "signedUrl": ...}` comprehension."""
    storage = get_storage()
    files = [{**f, "signedUrl": storage.generate_signed_url(f["storageKey"])} for f in study.get("files", [])]
    return {**study, "files": files}

# Roles a study's `assignedDoctorId` may point at — matches CONTRACTS.md §3's "Review/
# edit/finalize reports" row.
_ASSIGNABLE_REVIEWER_ROLES = ("org_admin", "doctor")


class StudyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StudyRepository(db)
        self.patients = PatientRepository(db)
        self.templates = TemplateRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_studies(
        self,
        organization_id: str,
        pagination: PaginationParams,
        *,
        patient_id: str | None = None,
        status: str | None = None,
        modality: str | None = None,
    ) -> dict[str, Any]:
        extra_filter: dict[str, Any] = {}
        if patient_id:
            extra_filter["patientId"] = patient_id
        if status:
            extra_filter["status"] = status
        if modality:
            extra_filter["modality"] = modality
        if pagination.search:
            # Only free-text field on a study cheap/safe to substring-search directly;
            # `clinicalHistory` is left out of `search` on purpose (narrative clinical
            # text shouldn't double as a list-filter column).
            extra_filter["bodyPart"] = {"$regex": pagination.search, "$options": "i"}

        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.repo.list_scoped(
            organization_id,
            extra_filter,
            sort=[("createdAt", -1)],
            skip=skip,
            limit=pagination.page_size,
        )
        public_items = to_public_list(items)

        # The list view shows each row's patient by name (StudiesPage's Patient column),
        # not by id -- one batched lookup for the whole page instead of a query per row.
        patient_ids = list({item["patientId"] for item in public_items if item.get("patientId")})
        if patient_ids:
            patients, _ = await self.patients.list_scoped(organization_id, {"id": {"$in": patient_ids}}, limit=len(patient_ids))
            patients_by_id = {p["id"]: p for p in to_public_list(patients)}
            for item in public_items:
                patient = patients_by_id.get(item.get("patientId"))
                if patient:
                    item["patient"] = patient

        return paginated(public_items, pagination.page, pagination.page_size, total)

    async def get_study(self, study_id: str, organization_id: str) -> dict[str, Any]:
        study = await self.repo.find_by_id_scoped(study_id, organization_id)
        if not study:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")
        return to_public(with_signed_urls(study))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_study(
        self,
        current_user: CurrentUser,
        payload: StudyCreate,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        patient = await self.patients.find_by_id_scoped(payload.patient_id, current_user.organization_id)
        if not patient:
            raise AppError.not_found("Patient not found", "PATIENT_NOT_FOUND")

        if payload.template_id is not None:
            await self._require_template(payload.template_id, current_user.organization_id)

        doc = {
            "organizationId": current_user.organization_id,
            "patientId": payload.patient_id,
            "modality": payload.modality,
            "bodyPart": payload.body_part,
            "clinicalHistory": payload.clinical_history,
            "studyDate": payload.study_date.isoformat(),
            "status": "uploaded",
            "assignedDoctorId": None,
            "files": [],
            "templateId": payload.template_id,
            "lastFindings": None,
            # Nullable DICOM UID placeholders (spec §15) — not populated in v1.
            "studyInstanceUid": None,
            "seriesInstanceUid": None,
            "sopInstanceUid": None,
            "createdBy": current_user.id,
        }
        created = await self.repo.insert(doc)

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="STUDY_CREATED",
            resource_type="study",
            resource_id=created["_id"],
            metadata={"patientId": payload.patient_id, "modality": payload.modality},
            ip=ip,
            user_agent=user_agent,
        )
        return to_public(created)

    async def create_from_intake(
        self,
        current_user: CurrentUser,
        *,
        patient_id: str | None,
        new_patient: PatientCreateRequest | None,
        modality: str,
        body_part: str,
        clinical_history: str | None,
        study_date: str,
        template_id: str | None,
        file: UploadFile,
        run_analysis: bool,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        """Consolidates patient resolution + study creation + file upload + AI analysis
        into one call, so `POST /studies/intake` can hand the frontend a single request
        that returns a draft report — instead of the four separate calls (patients, studies,
        uploads, analysis) the old chat-based intake made in sequence. Every step below
        calls straight through to the existing service/repository method for that step;
        nothing is duplicated here.

        Exactly one of `patient_id`/`new_patient` is expected (validated by the route)."""
        if patient_id:
            existing_patient = await self.patients.find_by_id_scoped(patient_id, current_user.organization_id)
            if not existing_patient:
                raise AppError.not_found("Patient not found", "PATIENT_NOT_FOUND")
            resolved_patient_id = existing_patient["_id"]
        else:
            assert new_patient is not None
            created_patient = await PatientService(self.db).create_patient(
                current_user, new_patient, ip=ip, user_agent=user_agent
            )
            resolved_patient_id = created_patient["id"]

        study_payload = StudyCreate(
            patientId=resolved_patient_id,
            modality=modality,
            bodyPart=body_part,
            clinicalHistory=clinical_history,
            studyDate=study_date,
            templateId=template_id,
        )
        study = await self.create_study(current_user, study_payload, ip=ip, user_agent=user_agent)

        updated_study, _file_record = await UploadService(self.db).upload_file(
            study_id=study["id"],
            organization_id=current_user.organization_id,
            modality=modality,
            file=file,
            uploaded_by=current_user.id,
        )

        result: dict[str, Any] = {
            "study": to_public(with_signed_urls(updated_study)),
            "report": None,
            "analysisJobId": None,
        }

        if run_analysis:
            analysis = await AnalysisService(self.db).start_analysis(study["id"], current_user.organization_id)
            result["analysisJobId"] = analysis["jobId"]
            result["report"] = analysis["report"]
            refreshed = await self.repo.find_by_id_scoped(study["id"], current_user.organization_id)
            if refreshed:
                result["study"] = to_public(with_signed_urls(refreshed))

        return result

    async def update_study(
        self,
        study_id: str,
        current_user: CurrentUser,
        payload: StudyUpdate,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        existing = await self.repo.find_by_id_scoped(study_id, current_user.organization_id)
        if not existing:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

        update: dict[str, Any] = {}
        if payload.modality is not None:
            update["modality"] = payload.modality
        if payload.body_part is not None:
            update["bodyPart"] = payload.body_part
        if payload.clinical_history is not None:
            update["clinicalHistory"] = payload.clinical_history
        if payload.study_date is not None:
            update["studyDate"] = payload.study_date.isoformat()
        if payload.template_id is not None:
            await self._require_template(payload.template_id, current_user.organization_id)
            update["templateId"] = payload.template_id
        if payload.assigned_doctor_id is not None:
            await self._require_assignable_doctor(payload.assigned_doctor_id, current_user.organization_id)
            update["assignedDoctorId"] = payload.assigned_doctor_id

        if not update:
            return to_public(existing)

        updated = await self.repo.update_scoped(study_id, current_user.organization_id, update)
        if not updated:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="STUDY_UPDATED",
            resource_type="study",
            resource_id=study_id,
            metadata={"fields": sorted(update.keys())},
            ip=ip,
            user_agent=user_agent,
        )
        return to_public(updated)

    async def delete_study(
        self,
        study_id: str,
        current_user: CurrentUser,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        existing = await self.repo.find_by_id_scoped(study_id, current_user.organization_id)
        if not existing:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

        deleted = await self.repo.delete_scoped(study_id, current_user.organization_id)
        if not deleted:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="STUDY_DELETED",
            resource_type="study",
            resource_id=study_id,
            metadata={"status": existing.get("status")},
            ip=ip,
            user_agent=user_agent,
        )

    # ------------------------------------------------------------------
    # Internal FK validation helpers
    # ------------------------------------------------------------------

    async def _require_template(self, template_id: str, organization_id: str) -> None:
        template = await self.templates.find_by_id_scoped(template_id, organization_id)
        if not template:
            raise AppError.not_found("Report template not found", "TEMPLATE_NOT_FOUND")

    async def _require_assignable_doctor(self, user_id: str, organization_id: str) -> None:
        # `users` is not an organization-scoped collection in the `*_scoped` sense
        # (CONTRACTS.md §11), so the organization match is checked by hand here.
        user = await self.users.find_by_id(user_id)
        if (
            not user
            or user.get("organizationId") != organization_id
            or user.get("role") not in _ASSIGNABLE_REVIEWER_ROLES
        ):
            raise AppError.bad_request(
                "assignedDoctorId must be an org_admin or doctor in this organization",
                "ASSIGNED_DOCTOR_INVALID",
            )
