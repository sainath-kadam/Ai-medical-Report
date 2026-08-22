"""Studies domain routes (CONTRACTS.md §9). Every route requires auth. Per the RBAC matrix
(CONTRACTS.md §3) and `app/api/studies/README.md`: `org_admin`/`doctor`, uniformly — every
route below (list/create/view/update/delete) is gated the same way, since there's no
reduced-permission role left to carve out now that `technician` is gone. PATCH here only
ever touches descriptive metadata/assignment, never `status` (that stays pipeline-owned —
see `app/schemas/study.py`).

Routers stay thin: parse the request, call the service, return `ok(...)`.
"""

from __future__ import annotations

from pydantic import ValidationError

from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.exceptions import AppError
from app.core.security import CurrentUser, require_admin_or_doctor
from app.core.subscription import require_active_subscription
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreateRequest
from app.schemas.study import StudyCreate, StudyUpdate
from app.services.study_service import StudyService
from app.utils.response import ok

router = APIRouter(prefix="/studies", tags=["studies"])


def _validation_error(exc: ValidationError) -> AppError:
    first = exc.errors()[0] if exc.errors() else None
    field = ".".join(str(p) for p in first["loc"]) if first else None
    message = f"{field}: {first['msg']}" if first and field else "Invalid request data"
    return AppError.bad_request(message, "VALIDATION_ERROR")


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    """IP/user-agent captured by `RequestContextMiddleware`, forwarded to audit log calls
    (CONTRACTS.md §4 audit_logs `ip?`/`userAgent?`)."""
    return getattr(request.state, "client_ip", None), getattr(request.state, "user_agent", None)


@router.get("")
async def list_studies(
    pagination: PaginationParams = Depends(pagination_params),
    patient_id: str | None = Query(None, alias="patientId"),
    status: str | None = Query(None),
    modality: str | None = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    result = await StudyService(db).list_studies(
        current_user.organization_id,
        pagination,
        patient_id=patient_id,
        status=status,
        modality=modality,
    )
    return ok(result)


@router.post("/intake", status_code=201)
async def create_study_intake(
    request: Request,
    file: UploadFile,
    modality: str = Form(...),
    body_part: str = Form(..., alias="bodyPart"),
    study_date: str = Form(..., alias="studyDate"),
    clinical_history: str | None = Form(None, alias="clinicalHistory"),
    template_id: str | None = Form(None, alias="templateId"),
    patient_id: str | None = Form(None, alias="patientId"),
    patient_mrn: str | None = Form(None, alias="patientMrn"),
    patient_name: str | None = Form(None, alias="patientName"),
    patient_date_of_birth: str | None = Form(None, alias="patientDateOfBirth"),
    patient_sex: str | None = Form(None, alias="patientSex"),
    patient_contact_phone: str | None = Form(None, alias="patientContactPhone"),
    patient_contact_email: str | None = Form(None, alias="patientContactEmail"),
    run_analysis: bool = Form(True, alias="runAnalysis"),
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    """One-request "new study" flow — resolves/creates the patient, creates the study,
    uploads the file, and (if `run_analysis`) runs AI analysis synchronously, returning the
    draft report in a single response. Replaces the old client-side chain of separate
    patient/study/upload/analyze calls the chat-based intake used to make. See
    `StudyService.create_from_intake` for the actual orchestration."""
    ip, user_agent = _client_meta(request)

    new_patient: PatientCreateRequest | None = None
    if not patient_id:
        if not (patient_mrn and patient_name and patient_date_of_birth and patient_sex):
            raise AppError.bad_request(
                "Provide patientId, or the new patient's mrn/name/dateOfBirth/sex.",
                "PATIENT_INFO_REQUIRED",
            )
        try:
            new_patient = PatientCreateRequest(
                mrn=patient_mrn,
                name=patient_name,
                dateOfBirth=patient_date_of_birth,
                sex=patient_sex,
                contactPhone=patient_contact_phone,
                contactEmail=patient_contact_email,
            )
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    # Only gate on subscription/trial quota when analysis will actually run — a
    # draft-only submission (run_analysis=false) shouldn't be blocked by it.
    if run_analysis:
        await require_active_subscription(current_user, db)

    try:
        result = await StudyService(db).create_from_intake(
            current_user,
            patient_id=patient_id,
            new_patient=new_patient,
            modality=modality,
            body_part=body_part,
            clinical_history=clinical_history,
            study_date=study_date,
            template_id=template_id,
            file=file,
            run_analysis=run_analysis,
            ip=ip,
            user_agent=user_agent,
        )
    except ValidationError as exc:
        raise _validation_error(exc) from exc

    return ok(result, status_code=201)


@router.post("", status_code=201)
async def create_study(
    payload: StudyCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    study = await StudyService(db).create_study(current_user, payload, ip=ip, user_agent=user_agent)
    return ok(study, status_code=201)


@router.get("/{study_id}")
async def get_study(
    study_id: str,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    study = await StudyService(db).get_study(study_id, current_user.organization_id)
    return ok(study)


@router.patch("/{study_id}")
async def update_study(
    study_id: str,
    payload: StudyUpdate,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    study = await StudyService(db).update_study(study_id, current_user, payload, ip=ip, user_agent=user_agent)
    return ok(study)


@router.delete("/{study_id}")
async def delete_study(
    study_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    await StudyService(db).delete_study(study_id, current_user, ip=ip, user_agent=user_agent)
    return ok(None)
