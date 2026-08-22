"""Request-body schemas for the report-templates domain (CONTRACTS.md §4/§9, spec §26 —
organization branding + custom report sections/labels). Response bodies are always plain
dicts (a `report_templates` document run through `to_public()`), never these classes —
see CONTRACTS.md §1a.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel

_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class TemplateHeaderSchema(CamelModel):
    organization_name: str = Field(..., min_length=1, max_length=200)
    # A storage KEY returned by POST /templates/logo (e.g. "template_logo/<orgId>/<id>.png"),
    # never a URL -- a short-lived signed `logoUrl` is computed fresh on every read by
    # TemplateService (mirrors study_service.py::with_signed_urls) and is never accepted
    # here, so a stale signed URL can never get written back into the row.
    logo_key: str | None = None
    tagline: str | None = None
    contact_number: str | None = Field(default=None, max_length=40)


class TemplateStyleSchema(CamelModel):
    header_text_color: str | None = Field(default=None, pattern=_HEX_COLOR_PATTERN)
    background_color: str | None = Field(default=None, pattern=_HEX_COLOR_PATTERN)
    content_text_color: str | None = Field(default=None, pattern=_HEX_COLOR_PATTERN)
    # float, not int: the historical hardcoded body size this defaults to (in pdf_service.py)
    # is 10.5pt, and the frontend's "Medium" font-size option sends that same 10.5 -- an int
    # field would reject it ("Input should be a valid integer, got a number with a
    # fractional part"), which is exactly what broke the live preview for any template using
    # that default before this was a float.
    font_size: float | None = Field(default=None, ge=8, le=16)


class TemplateDoctorInfoSchema(CamelModel):
    show_doctor_name: bool = True
    show_signature_line: bool = True
    show_registration_no: bool = False


class TemplateSectionSchema(CamelModel):
    key: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    order: int = 0
    enabled: bool = True
    guidance: str | None = None


class TemplateFooterSchema(CamelModel):
    text: str | None = None
    disclaimer: str | None = None


class TemplateCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=200)
    is_default: bool = False
    header: TemplateHeaderSchema
    doctor_info: TemplateDoctorInfoSchema = Field(default_factory=TemplateDoctorInfoSchema)
    sections: list[TemplateSectionSchema] = Field(..., min_length=1)
    footer: TemplateFooterSchema = Field(default_factory=TemplateFooterSchema)
    accent_color: str = Field(default="#0E7C86", max_length=20)
    # Optional, not default_factory: a template fetched from the DB and round-tripped back
    # through this schema (preview-pdf's payload is exactly that) may carry a stored `null`
    # from before this field existed, and that must validate the same as "not provided".
    style: TemplateStyleSchema | None = None


class TemplateUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None
    header: TemplateHeaderSchema | None = None
    doctor_info: TemplateDoctorInfoSchema | None = None
    sections: list[TemplateSectionSchema] | None = Field(default=None, min_length=1)
    footer: TemplateFooterSchema | None = None
    accent_color: str | None = Field(default=None, max_length=20)
    style: TemplateStyleSchema | None = None
