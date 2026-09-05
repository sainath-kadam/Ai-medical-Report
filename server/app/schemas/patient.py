"""Request-body validation for the patients domain (CONTRACTS.md §9, §4 — a NEW entity,
did not exist in the old Node app). Responses are plain dicts (repository docs run through
`to_public()`), never built from a response model — see CONTRACTS.md §1a and
`app/services/patient_service.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel

Sex = Literal["male", "female", "other", "unspecified"]


class PatientCreateRequest(CamelModel):
    """POST /patients — any authenticated org member (org_admin/doctor, CONTRACTS.md §3)
    may create a patient record for their own organization."""

    # Optional on purpose: a hospital with a RIS can pass its real medical record number,
    # everyone else leaves it out and the server assigns a per-organization `MRN-000123`
    # (see PatientService.create_patient) — the report still prints a Patient ID, and the
    # (organizationId, mrn) uniqueness that patient matching relies on is preserved.
    mrn: str | None = Field(None, min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    date_of_birth: date
    sex: Sex
    contact_phone: str | None = Field(None, max_length=40)
    contact_email: str | None = Field(None, max_length=200)


class PatientUpdateRequest(CamelModel):
    """PATCH /patients/{id} — every field optional; only the ones provided are applied.
    Allowed for org_admin/doctor, same as every other patient action."""

    mrn: str | None = Field(None, min_length=1, max_length=64)
    name: str | None = Field(None, min_length=1, max_length=200)
    date_of_birth: date | None = None
    sex: Sex | None = None
    contact_phone: str | None = Field(None, max_length=40)
    contact_email: str | None = Field(None, max_length=200)
