"""Reports domain routes (CONTRACTS.md §9). RBAC (CONTRACTS.md §3): `org_admin`/`doctor`
may list/view/download/edit/request-changes/regenerate/finalize a report.

`POST /{id}/change-request` runs the AI revision inline now (Redis/ARQ removed — see
CLAUDE.md) but still returns `{jobId}` so the frontend's existing polling
(`GET /analysis/jobs/{jobId}`) keeps working unchanged. `POST /{id}/regenerate` is (and
always was) synchronous — see `ReportService.regenerate_report`'s docstring for why that's
the simpler, still-correct choice CONTRACTS.md authorized.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import get_db, pagination_params
from app.core.security import CurrentUser, require_admin_or_doctor
from app.schemas.common import PaginationParams
from app.schemas.report import ChangeRequestBody, ReportContentEdit
from app.services.report_service import ReportService
from app.utils.response import ok

router = APIRouter(prefix="/reports", tags=["reports"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return getattr(request.state, "client_ip", None), getattr(request.state, "user_agent", None)


@router.get("")
async def list_reports(
    pagination: PaginationParams = Depends(pagination_params),
    status: str | None = Query(None),
    patient_id: str | None = Query(None, alias="patientId"),
    modality: str | None = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db=Depends(get_db),
):
    result = await ReportService(db).list_reports(
        current_user.organization_id, pagination, status=status, patient_id=patient_id, modality=modality
    )
    return ok(result)


@router.get("/{report_id}")
async def get_report(report_id: str, current_user: CurrentUser = Depends(require_admin_or_doctor()), db=Depends(get_db)):
    report = await ReportService(db).get_report(report_id, current_user.organization_id)
    return ok(report)


@router.get("/{report_id}/versions")
async def get_report_versions(report_id: str, current_user: CurrentUser = Depends(require_admin_or_doctor()), db=Depends(get_db)):
    versions = await ReportService(db).get_versions(report_id, current_user.organization_id)
    return ok(versions)


@router.patch("/{report_id}")
async def update_report(
    report_id: str,
    payload: ReportContentEdit,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db=Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    report = await ReportService(db).update_report(report_id, current_user, payload, ip=ip, user_agent=user_agent)
    return ok(report)


@router.post("/{report_id}/change-request", status_code=200)
async def request_changes(
    report_id: str,
    payload: ChangeRequestBody,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db=Depends(get_db),
):
    result = await ReportService(db).request_changes(report_id, current_user, payload)
    return ok(result)


@router.post("/{report_id}/regenerate")
async def regenerate_report(
    report_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db=Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    report = await ReportService(db).regenerate_report(report_id, current_user, ip=ip, user_agent=user_agent)
    return ok(report)


@router.post("/{report_id}/finalize")
async def finalize_report(
    report_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db=Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    report = await ReportService(db).finalize_report(report_id, current_user, ip=ip, user_agent=user_agent)
    return ok(report)


@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db=Depends(get_db),
):
    ip, user_agent = _client_meta(request)
    pdf_bytes = await ReportService(db).get_pdf_bytes(report_id, current_user, ip=ip, user_agent=user_agent)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.pdf"'},
    )
