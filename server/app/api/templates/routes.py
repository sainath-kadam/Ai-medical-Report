"""Report-templates routes (CONTRACTS.md §9). Listing/reading is open to any authenticated
org member (a doctor needs to see template sections when reviewing a report);
create/update/delete are org_admin only (RBAC matrix, CONTRACTS.md §3 — "manage org
settings/branding/templates").
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, pagination_params
from app.core.security import CurrentUser, get_current_user, require_roles
from app.schemas.common import PaginationParams
from app.schemas.template import TemplateCreate, TemplateUpdate
from app.services.template_service import TemplateService
from app.utils.response import ok, paginated

router = APIRouter(prefix="/templates", tags=["templates"])


def _service(db: AsyncSession = Depends(get_db)) -> TemplateService:
    return TemplateService(db)


@router.get("")
async def list_templates(
    pagination: PaginationParams = Depends(pagination_params),
    current_user: CurrentUser = Depends(get_current_user),
    service: TemplateService = Depends(_service),
):
    items, total = await service.list_templates(current_user.organization_id, pagination)
    return ok(paginated(items, pagination.page, pagination.page_size, total))


@router.post("/logo", status_code=201)
async def upload_template_logo(
    file: UploadFile,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    service: TemplateService = Depends(_service),
):
    result = await service.upload_logo(current_user.organization_id, file)
    return ok(result, status_code=201)


@router.post("/preview-pdf")
async def preview_template_pdf(
    payload: TemplateCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: TemplateService = Depends(_service),
):
    # Any authenticated org member, not org_admin-only: a doctor picking a template while
    # starting a study needs to see this preview too, and nothing here is persisted.
    pdf_bytes = await service.render_preview_pdf(current_user.organization_id, payload, current_user.name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="template-preview.pdf"'},
    )


@router.post("", status_code=201)
async def create_template(
    payload: TemplateCreate,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    service: TemplateService = Depends(_service),
):
    template = await service.create_template(current_user.organization_id, current_user.id, payload)
    return ok(template, status_code=201)


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: TemplateService = Depends(_service),
):
    template = await service.get_template(template_id, current_user.organization_id)
    return ok(template)


@router.patch("/{template_id}")
async def update_template(
    template_id: str,
    payload: TemplateUpdate,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    service: TemplateService = Depends(_service),
):
    template = await service.update_template(template_id, current_user.organization_id, payload)
    return ok(template)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: CurrentUser = Depends(require_roles("org_admin")),
    service: TemplateService = Depends(_service),
):
    await service.delete_template(template_id, current_user.organization_id)
    return ok(None)
