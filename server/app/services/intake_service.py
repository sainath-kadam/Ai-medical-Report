"""Business logic for the intake domain (CONTRACTS.md §9/§12) — the chat-style study
intake flow's one job: turn a physician's free-text chat message into structured
patient/study fields, merge them with what's already confirmed, and say what's still
missing. `AnalysisService`/`ReportService` never call into this — it exists purely to
support the frontend's `ChatIntake` conversation before a patient/study record exists yet.
"""

from __future__ import annotations

from typing import Any

from app.ai.base import get_report_provider
from app.schemas.intake import IntakeParseRequest

# Mirrors exactly what `PatientCreateRequest`/`StudyCreate` (app/schemas/) actually require
# with no default — `sex` is required too, but always safely defaults to "unspecified"
# (matching PatientForm's own convention) so it's deliberately NOT asked about here.
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "patient": ["name", "mrn", "dateOfBirth"],
    "study": ["modality", "bodyPart"],
}

_FOLLOW_UP_QUESTIONS: dict[str, str] = {
    "name": "What's the patient's full name?",
    "mrn": "What's the patient's MRN (medical record number)?",
    "dateOfBirth": "What's the patient's date of birth?",
    "modality": "What kind of scan is this — X-ray, CT, MRI, or ultrasound?",
    "bodyPart": "Which body part is being scanned?",
}


async def parse_intake(payload: IntakeParseRequest) -> dict[str, Any]:
    provider = get_report_provider()
    extracted = await provider.extract_intake(payload.kind, payload.message, payload.known)

    merged = {**payload.known, **extracted}
    missing = [f for f in _REQUIRED_FIELDS[payload.kind] if not merged.get(f)]

    return {
        "fields": merged,
        "missingFields": missing,
        "followUpQuestion": _FOLLOW_UP_QUESTIONS[missing[0]] if missing else None,
        "complete": not missing,
    }
