"""Request-body validation for the studies domain (CONTRACTS.md §4/§9). Responses are
always plain dicts (a `studies` document run through `to_public()`), never these classes —
see CONTRACTS.md §1a.

Note: `status` is intentionally NOT a client-settable field on either schema below. It
starts at `uploaded` on creation and is only ever advanced by the analysis pipeline
(`AnalysisService`, run inline by the analyze route) — see CONTRACTS.md §12 — never by a
direct PATCH from a caller, so the AI/processing pipeline stays the single source of truth
for it.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel

Modality = Literal["x_ray", "ct", "mri", "ultrasound", "other"]


def _coerce_study_date(value: object) -> object:
    """Accepts either a bare date (`"2026-08-17"`) or a full ISO datetime/timestamp
    (`"2026-08-17T10:30:00.000Z"`, what `Date.prototype.toISOString()` produces) and keeps
    only the date portion — `pydantic.date`'s default parsing rejects a datetime string
    whose time-of-day isn't exactly midnight, which would otherwise 422 a perfectly
    reasonable client payload. Non-strings (e.g. an already-parsed `date`) pass through
    untouched for pydantic's normal validation to handle."""
    if isinstance(value, str):
        return value.strip()[:10]
    return value


class StudyCreate(CamelModel):
    patient_id: str = Field(..., min_length=1)
    modality: Modality
    body_part: str = Field(..., min_length=1, max_length=200)
    clinical_history: str | None = Field(default=None, max_length=5000)
    study_date: date
    template_id: str | None = None
    referring_physician: str | None = Field(default=None, max_length=200)

    _coerce_study_date = field_validator("study_date", mode="before")(_coerce_study_date)


class StudyUpdate(CamelModel):
    modality: Modality | None = None
    body_part: str | None = Field(default=None, min_length=1, max_length=200)
    clinical_history: str | None = Field(default=None, max_length=5000)
    study_date: date | None = None
    template_id: str | None = None
    assigned_doctor_id: str | None = None
    referring_physician: str | None = Field(default=None, max_length=200)

    _coerce_study_date = field_validator("study_date", mode="before")(_coerce_study_date)
