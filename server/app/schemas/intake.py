"""Request-body validation for the intake domain (CONTRACTS.md §9) — the chat-style study
intake flow's one endpoint. Responses are plain dicts, never these classes (CONTRACTS.md
§1a).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel


class IntakeParseRequest(CamelModel):
    kind: Literal["patient", "study"]
    message: str = Field(..., min_length=1, max_length=2000)
    # Fields already confirmed in earlier turns of this same conversation, keyed by the
    # camelCase field name (e.g. "mrn", "bodyPart") — merged with what this message adds.
    known: dict[str, str] = Field(default_factory=dict)
