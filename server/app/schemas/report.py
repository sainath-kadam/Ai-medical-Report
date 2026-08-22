"""Request-body validation for the reports domain (CONTRACTS.md §4/§9). Responses are
always plain dicts, never these classes (CONTRACTS.md §1a).
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class ReportSectionEdit(CamelModel):
    key: str
    title: str
    content: str


class ReportContentEdit(CamelModel):
    """A doctor's manual edit of the current version's content (PATCH /reports/{id}).
    Every field is optional — only the ones the doctor actually changed need be sent;
    the service merges them onto the current version rather than requiring a full replace.
    """

    summary: str | None = None
    sections: list[ReportSectionEdit] | None = None
    impression: str | None = None
    recommendations: str | None = None


class ChangeRequestBody(CamelModel):
    instruction: str = Field(..., min_length=3, max_length=2000)
