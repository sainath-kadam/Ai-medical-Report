"""A patient's age in years, for the report header, the PDF and the AI context.

Patients are created with just an age (`age`); older records carry a date of birth
instead, and their age is derived from it. Returns None rather than raising on a missing
or malformed value — age is shown/used when known, never worth failing a report over.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def patient_age(patient: dict[str, Any] | None) -> int | None:
    if not patient:
        return None
    if patient.get("age") is not None:
        return int(patient["age"])
    date_of_birth = patient.get("dateOfBirth")
    if not date_of_birth:
        return None
    try:
        born = date.fromisoformat(str(date_of_birth)[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
