"""Business logic for the report-templates domain (CONTRACTS.md §4/§9/§12, spec §26 —
organization branding + custom report sections/labels).

`ensure_default_template` is called from the signup flow (CONTRACTS.md §2 — signup creates
an Organization + a default ReportTemplate) and MUST stay idempotent: it never creates a
second default template for an org that already has one.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories.template_repository import TemplateRepository
from app.schemas.common import PaginationParams
from app.schemas.template import TemplateCreate, TemplateStyleSchema, TemplateUpdate
from app.storage import get_storage
from app.utils.ids import new_id, to_public, to_public_list

_ALLOWED_LOGO_MIME_PREFIXES = ("image/",)
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2MB -- plenty for a letterhead logo, small enough to
                                     # keep PDF generation fast and bound preview memory use


def _logo_prefix(organization_id: str) -> str:
    return f"template_logo/{organization_id}/"


def _sanitize_logo_key(header: dict[str, Any], organization_id: str) -> dict[str, Any]:
    """Drops a client-supplied logoKey that this org's own upload endpoint didn't actually
    issue (wrong org, guessed/tampered, or a key from an unrelated storage category) --
    without this, any authenticated user could point a template at another org's (or
    another category's) storage key and have the server fetch and embed those bytes into
    a PDF they can download. Silently nulls rather than raising so a stale/bad value never
    blocks a save; the template just renders with no logo."""
    key = header.get("logoKey")
    if key and not key.startswith(_logo_prefix(organization_id)):
        return {**header, "logoKey": None}
    return header


def _with_signed_logo(template: dict[str, Any] | None) -> dict[str, Any] | None:
    if template is None:
        return None
    header = template.get("header") or {}
    logo_key = header.get("logoKey")
    if not logo_key:
        return template
    signed_url = get_storage().generate_signed_url(logo_key)
    return {**template, "header": {**header, "logoUrl": signed_url}}


def _sample_report_data(sections: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Fabricated patient/study/content used to render a template preview -- there's no
    real report to show yet while someone is still designing or picking a template, so this
    stands in for one. Emits a sample entry for every section the draft has (including
    disabled ones); build_report_pdf's own enabled-sections filter (and its separate,
    fixed impression/recommendations blocks) already do the right thing with that, so this
    doesn't need to duplicate that filtering logic here."""
    patient = {"name": "Jordan Alvarez", "mrn": "MRN-000123", "dateOfBirth": "1985-04-12", "sex": "male"}
    study = {"modality": "CT", "bodyPart": "Chest", "studyDate": datetime.now(timezone.utc).date().isoformat()}
    content = {
        "summary": "Sample AI-generated summary illustrating how a finished report reads in this template.",
        "sections": [
            {
                "key": s["key"],
                "title": s["title"],
                "content": f"Sample {s['title'].lower()} text illustrating this section's placement and formatting.",
            }
            for s in sections
        ],
        "impression": "Sample impression — no acute findings in this illustrative preview.",
        "recommendations": "Sample recommendation — follow-up imaging in 6 months if clinically indicated.",
    }
    return patient, study, content

# The standard sections every freshly-provisioned organization starts with. Orders are
# left with gaps (10, 20, ...) so an org_admin can insert a custom section between two
# existing ones later without having to renumber everything.
#
# Deliberately does NOT include "impression"/"recommendations" as sections: those are
# dedicated top-level fields on GeneratedReportContent (see app/ai/base.py), always
# rendered by both ReportViewer.tsx and pdf_service.py's build_report_pdf as their own
# labeled blocks after the section loop. Including them here too would render every
# report with a duplicated Impression/Recommendations block — this list is the report
# BODY only (spec's "Findings" and preceding narrative), not the full document structure.
_DEFAULT_SECTIONS: list[dict[str, Any]] = [
    # Title is "Clinical Indication" (the standard ACR term); the key stays
    # "clinical_history" -- it's an opaque identifier the AI-generation pipeline threads
    # through generically (see analysis_service.py's TemplateSectionSpec construction,
    # keyed generically off title/guidance, never on this literal string), so renaming only
    # the display title is safe and doesn't touch generation logic.
    {
        "key": "clinical_history",
        "title": "Clinical Indication",
        "order": 10,
        "enabled": True,
        "guidance": "Summarize the reason for the study and relevant patient history provided at ordering time.",
    },
    {
        "key": "technique",
        "title": "Technique",
        "order": 20,
        "enabled": True,
        "guidance": "Describe the imaging modality, protocol, and any technical limitations.",
    },
    # Enabled by default: real structured radiology reports include a Comparison section
    # even with nothing to compare against, explicitly stating that (per ACR
    # structured-reporting guidance, which lists it as one of the standard sections
    # alongside clinical indication/technique/findings/impression) rather than omitting it.
    {
        "key": "comparison",
        "title": "Comparison",
        "order": 25,
        "enabled": True,
        "guidance": "State prior imaging reviewed, with study dates and modalities, or note none was available.",
    },
    {
        "key": "findings",
        "title": "Findings",
        "order": 30,
        "enabled": True,
        "guidance": "Describe observed findings systematically, by region/structure.",
    },
]


class TemplateService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TemplateRepository(db)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_templates(
        self, organization_id: str, pagination: PaginationParams
    ) -> tuple[list[dict[str, Any]], int]:
        extra_filter: dict[str, Any] = {}
        if pagination.search:
            extra_filter["name"] = {"$regex": pagination.search, "$options": "i"}
        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.repo.list_scoped(
            organization_id,
            extra_filter,
            sort=[("isDefault", -1), ("name", 1)],
            skip=skip,
            limit=pagination.page_size,
        )
        return [_with_signed_logo(t) for t in to_public_list(items)], total

    async def get_template(self, template_id: str, organization_id: str) -> dict[str, Any]:
        template = await self.repo.find_by_id_scoped(template_id, organization_id)
        if not template:
            raise AppError.not_found("Template not found")
        return _with_signed_logo(to_public(template))

    async def create_template(
        self, organization_id: str, created_by: str, payload: TemplateCreate
    ) -> dict[str, Any]:
        doc = {
            "_id": new_id(),
            "organizationId": organization_id,
            "name": payload.name,
            "isDefault": payload.is_default,
            "header": _sanitize_logo_key(payload.header.model_dump(by_alias=True), organization_id),
            "doctorInfo": payload.doctor_info.model_dump(by_alias=True),
            "sections": [s.model_dump(by_alias=True) for s in payload.sections],
            "footer": payload.footer.model_dump(by_alias=True),
            "accentColor": payload.accent_color,
            "style": (payload.style or TemplateStyleSchema()).model_dump(by_alias=True),
            "createdBy": created_by,
        }
        if payload.is_default:
            await self.repo.unset_other_defaults(organization_id)
        created = await self.repo.insert(doc)
        return _with_signed_logo(to_public(created))

    async def update_template(
        self, template_id: str, organization_id: str, payload: TemplateUpdate
    ) -> dict[str, Any]:
        existing = await self.repo.find_by_id_scoped(template_id, organization_id)
        if not existing:
            raise AppError.not_found("Template not found")

        update: dict[str, Any] = {}
        if payload.name is not None:
            update["name"] = payload.name
        if payload.header is not None:
            update["header"] = _sanitize_logo_key(payload.header.model_dump(by_alias=True), organization_id)
        if payload.doctor_info is not None:
            update["doctorInfo"] = payload.doctor_info.model_dump(by_alias=True)
        if payload.sections is not None:
            update["sections"] = [s.model_dump(by_alias=True) for s in payload.sections]
        if payload.footer is not None:
            update["footer"] = payload.footer.model_dump(by_alias=True)
        if payload.accent_color is not None:
            update["accentColor"] = payload.accent_color
        if payload.style is not None:
            update["style"] = payload.style.model_dump(by_alias=True)
        if payload.is_default is not None:
            update["isDefault"] = payload.is_default

        if not update:
            return _with_signed_logo(to_public(existing))

        # Only one default template per org at a time: setting isDefault=true here must
        # unset it everywhere else first.
        if payload.is_default:
            await self.repo.unset_other_defaults(organization_id, exclude_id=template_id)

        updated = await self.repo.update_scoped(template_id, organization_id, update)
        if not updated:
            raise AppError.not_found("Template not found")
        return _with_signed_logo(to_public(updated))

    # ------------------------------------------------------------------
    # Logo upload + live preview
    # ------------------------------------------------------------------

    async def upload_logo(self, organization_id: str, file: UploadFile) -> dict[str, Any]:
        content_type = file.content_type or "application/octet-stream"
        if not content_type.startswith(_ALLOWED_LOGO_MIME_PREFIXES):
            raise AppError.bad_request(
                f"Unsupported logo file type: {content_type}. Upload a PNG, JPEG, or WEBP image.",
                "UNSUPPORTED_FILE_TYPE",
            )
        data = await file.read()
        if len(data) > _MAX_LOGO_BYTES:
            raise AppError.bad_request("Logo exceeds the 2MB upload limit.", "FILE_TOO_LARGE")

        extension = os.path.splitext(file.filename or "")[1]
        storage_key = f"{_logo_prefix(organization_id)}{new_id()}{extension}"
        storage = get_storage()
        await storage.upload(storage_key, data, content_type)
        return {"logoKey": storage_key, "logoUrl": storage.generate_signed_url(storage_key)}

    async def render_preview_pdf(self, organization_id: str, payload: TemplateCreate, doctor_name: str) -> bytes:
        """Renders a sample report through this (possibly still-unsaved) template so the
        editor can show a live preview before the user hits Save. Deliberately stateless --
        unlike ReportService.get_pdf_bytes, nothing here is persisted or cached, since draft
        values change on every edit."""
        from app.services.pdf_service import build_report_pdf

        header = _sanitize_logo_key(payload.header.model_dump(by_alias=True), organization_id)
        sections = [s.model_dump(by_alias=True) for s in payload.sections]
        template_dict = {
            "header": header,
            "doctorInfo": payload.doctor_info.model_dump(by_alias=True),
            "sections": sections,
            "footer": payload.footer.model_dump(by_alias=True),
            "accentColor": payload.accent_color,
            "style": (payload.style or TemplateStyleSchema()).model_dump(by_alias=True),
        }

        logo_bytes = None
        if header.get("logoKey"):
            storage = get_storage()
            try:
                logo_bytes = await storage.download(header["logoKey"])
            except AppError:
                logo_bytes = None  # deleted/invalid -- render without a logo, don't 500

        patient, study, content = _sample_report_data(sections)
        return build_report_pdf(
            content=content,
            patient=patient,
            study=study,
            template=template_dict,
            doctor_name=doctor_name,
            report_id="PREVIEW",
            version_number=1,
            logo_bytes=logo_bytes,
        )

    async def delete_template(self, template_id: str, organization_id: str) -> None:
        existing = await self.repo.find_by_id_scoped(template_id, organization_id)
        if not existing:
            raise AppError.not_found("Template not found")
        if existing.get("isDefault"):
            raise AppError.conflict(
                "Cannot delete the default template. Set another template as default first.",
                "CANNOT_DELETE_DEFAULT_TEMPLATE",
            )
        deleted = await self.repo.delete_scoped(template_id, organization_id)
        if not deleted:
            raise AppError.not_found("Template not found")

    # ------------------------------------------------------------------
    # Cross-domain entry point (CONTRACTS.md §2/§12) — called from the signup flow.
    # ------------------------------------------------------------------

    async def ensure_default_template(
        self, organization_id: str, organization_name: str, created_by: str
    ) -> dict[str, Any]:
        """Idempotent: returns the org's existing default template if one already exists,
        otherwise provisions a sensible default (the 3 standard sections in
        `_DEFAULT_SECTIONS` above) and returns it."""
        existing = await self.repo.get_default(organization_id)
        if existing:
            return _with_signed_logo(to_public(existing))

        doc = {
            "_id": new_id(),
            "organizationId": organization_id,
            "name": "Default Report Template",
            "isDefault": True,
            "header": {"organizationName": organization_name, "logoKey": None, "tagline": None, "contactNumber": None},
            "doctorInfo": {
                "showDoctorName": True,
                "showSignatureLine": True,
                "showRegistrationNo": False,
            },
            "sections": [dict(section) for section in _DEFAULT_SECTIONS],
            "footer": {
                "text": None,
                "disclaimer": None,
            },
            "accentColor": "#0E7C86",
            # A real (if all-null-fields) TemplateStyleSchema, not a bare None -- the frontend's
            # ReportTemplate.style type is non-nullable, and this doc is what every new org's
            # template preview/download renders from, so it should look like every other template.
            "style": TemplateStyleSchema().model_dump(by_alias=True),
            "createdBy": created_by,
        }
        created = await self.repo.insert(doc)
        return _with_signed_logo(to_public(created))
