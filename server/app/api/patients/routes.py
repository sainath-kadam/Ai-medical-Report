"""Patients domain routes (CONTRACTS.md §9) — a NEW entity (§4). Every route requires
auth. RBAC (CONTRACTS.md §3, `app/api/patients/README.md`): org_admin/doctor,
uniformly — every route below (list/create/view/edit/delete, plus the nested
`GET /{id}/studies`) is gated the same way, since there's no reduced-permission role left
to carve out now that `technician` is gone.

Routers stay thin: parse the request, call the service, return `ok(...)`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.security import CurrentUser, require_admin_or_doctor
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreateRequest, PatientUpdateRequest
from app.services.patient_service import PatientService
from app.utils.response import ok

router = APIRouter(prefix="/patients", tags=["patients"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    """IP/user-agent captured by `RequestContextMiddleware`, forwarded to audit log calls
    (CONTRACTS.md §4 audit_logs `ip?`/`userAgent?`)."""
    return getattr(request.state, "client_ip", None), getattr(request.state, "user_agent", None)


@router.get("")
async def list_patients(
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    result = await PatientService(db).list_patients(current_user, pagination)
    return ok(result)


@router.post("", status_code=201)
async def create_patient(
    payload: PatientCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await PatientService(db).create_patient(current_user, payload, ip=ip, user_agent=user_agent)
    return ok(result, status_code=201)


@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    result = await PatientService(db).get_patient(current_user, patient_id)
    return ok(result)


@router.patch("/{patient_id}")
async def update_patient(
    patient_id: str,
    payload: PatientUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    result = await PatientService(db).update_patient(current_user, patient_id, payload, ip=ip, user_agent=user_agent)
    return ok(result)


@router.delete("/{patient_id}")
async def delete_patient(
    patient_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    await PatientService(db).delete_patient(current_user, patient_id, ip=ip, user_agent=user_agent)
    return ok(None)


@router.get("/{patient_id}/studies")
async def get_patient_studies(
    patient_id: str,
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    result = await PatientService(db).get_patient_studies(current_user, patient_id, pagination)
    return ok(result)
