"""No-API-key fallback. Every method returns clearly-labeled placeholder content so local
development and CI never require a real Anthropic key, and so it's never ambiguous to a
reader (or, critically, to a doctor in a demo environment) that this is not a real AI
analysis (spec §53 — never let AI output look more authoritative than it is).

`extract_intake` is the one exception to "placeholder content only": the chat-style study
intake flow (CONTRACTS.md §9 `/intake`) is unusable end-to-end without SOME extraction
happening, so this runs a plain regex/keyword heuristic instead of an LLM call — good
enough to click through the flow locally, but never claims to be AI-generated."""

import re
from typing import Literal

from app.ai.base import (
    BaseMedicalImagingProvider,
    BaseReportGenerationProvider,
    ChangeRequestClassification,
    GeneratedContent,
    ReportSectionContent,
    StructuredFindings,
    StudyContext,
    TemplateSectionSpec,
)

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_MRN_RE = re.compile(r"\bmrn\W*([a-z0-9-]+)\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(\+?\d[\d\s-]{7,}\d)\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.IGNORECASE)
_MODALITY_KEYWORDS = [
    ("x_ray", ("x-ray", "xray", "x ray")),
    ("ct", ("ct scan", "cat scan", " ct", "ct-")),
    ("mri", ("mri",)),
    ("ultrasound", ("ultrasound", "sono", "sonogram")),
]


def _extract_patient_fields(message: str, known: dict[str, str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    lowered = message.lower()

    mrn_match = _MRN_RE.search(message)
    if mrn_match:
        fields["mrn"] = mrn_match.group(1)

    # Strip the date before scanning for a phone number — a bare digit-run regex would
    # otherwise happily match "1990-05-01" itself as a plausible-looking phone number.
    date_match = _DATE_RE.search(message)
    remainder_for_phone = message
    if date_match:
        fields["dateOfBirth"] = date_match.group(1)
        remainder_for_phone = message.replace(date_match.group(1), "")

    for value in ("male", "female", "other", "unspecified"):
        if re.search(rf"\b{value}\b", lowered):
            fields["sex"] = value
            break

    phone_match = _PHONE_RE.search(remainder_for_phone)
    if phone_match:
        fields["contactPhone"] = phone_match.group(1).strip()

    email_match = _EMAIL_RE.search(message)
    if email_match:
        fields["contactEmail"] = email_match.group(0)

    if "name" not in known:
        # Best-effort only (this is the no-API-key fallback, not real NLU): the first
        # comma-separated segment that isn't itself one of the fields just extracted above.
        first_segment = message.split(",")[0].strip()
        skip_words = ("mrn", "male", "female", "other", "unspecified", "dob", "born")
        if first_segment and not any(w in first_segment.lower() for w in skip_words) and not _DATE_RE.search(first_segment):
            fields["name"] = first_segment

    return fields


def _extract_study_fields(message: str, known: dict[str, str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    lowered = message.lower()

    for modality, keywords in _MODALITY_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            fields["modality"] = modality
            break

    date_match = _DATE_RE.search(message)
    if date_match:
        fields["studyDate"] = date_match.group(1)

    if "bodyPart" not in known:
        # Only the segment before the first comma is treated as body-part material — a
        # comma is the one reliable signal (in this crude heuristic, not real NLU) that the
        # physician moved on to something else, e.g. clinical history. Strip a recognized
        # modality phrase from what's left.
        first_segment = message.split(",")[0]
        for _, keywords in _MODALITY_KEYWORDS:
            for kw in keywords:
                first_segment = re.sub(re.escape(kw), "", first_segment, flags=re.IGNORECASE)
        first_segment = re.sub(r"\btoday\b", "", first_segment, flags=re.IGNORECASE).strip(" ,.-\n")
        if first_segment and len(first_segment) < 60:
            fields["bodyPart"] = first_segment

    if "clinicalHistory" not in known:
        rest = ",".join(message.split(",")[1:]).strip(" ,.-\n")
        if rest:
            fields["clinicalHistory"] = rest

    return fields

_MOCK_NOTE = (
    "[MOCK MODE] No AI_API_KEY is configured on the server, so this is placeholder "
    "content demonstrating the report structure only — it is not AI-generated. Set "
    "AI_API_KEY in server/.env to enable real drafting."
)


class MockImagingProvider(BaseMedicalImagingProvider):
    async def analyze(self, context: StudyContext, high_accuracy_mode: bool) -> StructuredFindings:
        return StructuredFindings(observations=[_MOCK_NOTE], raw_summary=_MOCK_NOTE, analyzable=True)


class MockReportProvider(BaseReportGenerationProvider):
    async def generate(self, organization_name, sections, context, findings, high_accuracy_mode) -> GeneratedContent:
        return self._mock_content(sections)

    async def revise(self, organization_name, sections, context, findings, previous, instruction, classification, high_accuracy_mode) -> GeneratedContent:
        return self._mock_content(sections)

    async def classify_change_request(self, instruction: str, sections: list[TemplateSectionSpec]) -> ChangeRequestClassification:
        return ChangeRequestClassification(target_sections=[s.key for s in sections], formatting_only=False)

    async def summarize_for_notification(self, modality: str, body_part: str, summary: str) -> str:
        return f"AI draft ready for review — {modality} ({body_part})."

    async def summarize_findings(self, organization_name, context, findings, high_accuracy_mode=False) -> str:
        return _MOCK_NOTE

    async def extract_intake(self, kind: Literal["patient", "study"], message: str, known: dict[str, str]) -> dict[str, str]:
        if kind == "patient":
            return _extract_patient_fields(message, known)
        return _extract_study_fields(message, known)

    def _mock_content(self, sections: list[TemplateSectionSpec]) -> GeneratedContent:
        enabled = sorted([s for s in sections if s.enabled], key=lambda s: s.order)
        return GeneratedContent(
            summary=_MOCK_NOTE,
            sections=[ReportSectionContent(key=s.key, title=s.title, content=_MOCK_NOTE) for s in enabled],
            impression=_MOCK_NOTE,
            recommendations=_MOCK_NOTE,
            model_used="mock (no AI_API_KEY configured)",
        )
