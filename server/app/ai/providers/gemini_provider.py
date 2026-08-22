"""Gemini-backed image analysis AND report generation — the `gemini` `AI_PROVIDER` option
(the default). One model (`GEMINI_MODEL`, via the `google-genai` SDK, `GEMINI_API_KEY`)
does both jobs, no tiers — deliberately simple.

UNVERIFIED AGAINST A LIVE KEY: written to match the documented `google-genai` SDK surface
as accurately as possible, but — unlike `anthropic_provider.py`, which was tested against
real requests during development — no Gemini API key was available to actually exercise
this file. Re-check against current SDK docs if it errors on first real use.
"""

from __future__ import annotations

import json
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
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

_FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {"type": "array", "items": {"type": "string"}},
        "rawSummary": {"type": "string"},
        "analyzable": {"type": "boolean"},
        "unanalyzableReason": {"type": "string"},
    },
    "required": ["observations", "rawSummary", "analyzable"],
}

_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}},
                "required": ["key", "title", "content"],
            },
        },
        "impression": {"type": "string"},
        "recommendations": {"type": "string"},
    },
    "required": ["summary", "sections", "impression", "recommendations"],
}

_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "targetSections": {"type": "array", "items": {"type": "string"}},
        "formattingOnly": {"type": "boolean"},
    },
    "required": ["targetSections", "formattingOnly"],
}

_PATIENT_INTAKE_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("name", "mrn", "dateOfBirth", "sex", "contactPhone", "contactEmail")},
    "required": ["name", "mrn", "dateOfBirth", "sex", "contactPhone", "contactEmail"],
}

_STUDY_INTAKE_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("modality", "bodyPart", "studyDate", "clinicalHistory")},
    "required": ["modality", "bodyPart", "studyDate", "clinicalHistory"],
}


def _client():
    if not settings.gemini_api_key:
        raise AppError("Gemini is not configured (GEMINI_API_KEY unset)", 503, "AI_NOT_CONFIGURED")
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _generate_json(system_text: str, parts: list, schema: dict, max_tokens: int = 4096) -> dict:
    from google.genai import types

    client = _client()
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system_text,
                response_mime_type="application/json",
                response_schema=schema,
                max_output_tokens=max_tokens,
            ),
        )
    except Exception as exc:  # SDK exception hierarchy varies by version — normalize to AppError
        logger.error("Gemini API error: %s", exc)
        raise AppError("The AI service returned an error while processing this request.", 502, "AI_PROVIDER_ERROR") from exc

    if not response.text:
        raise AppError("The AI service returned an empty response.", 502, "AI_EMPTY_RESPONSE")
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise AppError("The AI service returned a response in an unexpected format.", 502, "AI_MALFORMED_RESPONSE") from exc


def _safety_preamble(organization_name: str) -> str:
    return (
        f"You are assisting a licensed physician at {organization_name} with a preliminary imaging analysis. "
        "This is DRAFT decision-support only, for the physician's review — never state or imply a finalized "
        "diagnosis, and never assert certainty the image does not clearly support. Use precise, neutral "
        "radiological language. Explicitly flag ambiguous, low-confidence, or partially obscured findings "
        "rather than guessing, and never invent findings, measurements, or clinical history not present in "
        "the input."
    )


def _context_meta_lines(context: StudyContext) -> list[str]:
    return [
        f"Modality: {context.modality}",
        f"Body part: {context.body_part}",
        f"Patient age: {context.patient_age}" if context.patient_age else None,
        f"Patient sex: {context.patient_sex}" if context.patient_sex else None,
        f"Clinical history from referring physician: {context.clinical_history}" if context.clinical_history else "Clinical history: none provided.",
    ]


def _findings_block(findings: StructuredFindings) -> str:
    if not findings.analyzable:
        return f"Image analysis result: NOT ANALYZABLE ({findings.unanalyzable_reason or 'unknown reason'})."
    lines = [f"Image analysis summary: {findings.raw_summary}", "Observations:"]
    lines += [f"- {o}" for o in findings.observations] or ["(none reported)"]
    return "\n".join(lines)


def _build_report_system(organization_name: str, sections: list[TemplateSectionSpec]) -> str:
    enabled = sorted([s for s in sections if s.enabled], key=lambda s: s.order)
    section_list = "\n".join(f'- "{s.key}" ({s.title})' + (f" — {s.guidance}" if s.guidance else "") for s in enabled)
    return (
        _safety_preamble(organization_name)
        + "\n\nYou will be given structured findings from a separate image-analysis step (not the image itself). "
        "Write the full structured report body from those findings.\n\n"
        f"Structure the report using exactly these sections, in this order:\n{section_list}\n\n"
        "Write plain prose for each section — no markdown headers or bullet characters. Keep the summary to "
        "1-2 sentences. If clinical history is provided, explicitly reconcile the findings against it."
    )


def _parse_content(data: dict) -> GeneratedContent:
    return GeneratedContent(
        summary=data.get("summary", ""),
        sections=[ReportSectionContent(key=s["key"], title=s["title"], content=s["content"]) for s in data.get("sections", [])],
        impression=data.get("impression", ""),
        recommendations=data.get("recommendations", ""),
        model_used=settings.gemini_model,
    )


class GeminiImagingProvider(BaseMedicalImagingProvider):
    async def analyze(self, context: StudyContext, high_accuracy_mode: bool) -> StructuredFindings:
        from google.genai import types

        system = _safety_preamble("your organization") + (
            " Examine the provided image and return discrete, neutral observations only — do not write a full "
            "report or impression. If the source is not a directly viewable, interpretable image, set "
            "analyzable=false and explain why instead of fabricating visual observations."
        )
        meta_lines = [l for l in _context_meta_lines(context) if l]
        parts = []
        if context.image_bytes and context.image_mime_type:
            parts.append(types.Part.from_bytes(data=context.image_bytes, mime_type=context.image_mime_type))
        else:
            meta_lines.append("Note: the source file is not a directly viewable image format.")
        parts.append(types.Part.from_text(text="\n".join(meta_lines)))

        data = _generate_json(system, parts, _FINDINGS_SCHEMA, max_tokens=1024)
        return StructuredFindings(
            observations=data.get("observations", []),
            raw_summary=data.get("rawSummary", ""),
            analyzable=data.get("analyzable", True),
            unanalyzable_reason=data.get("unanalyzableReason"),
        )


class GeminiReportProvider(BaseReportGenerationProvider):
    async def generate(
        self,
        organization_name: str,
        sections: list[TemplateSectionSpec],
        context: StudyContext,
        findings: StructuredFindings,
        high_accuracy_mode: bool,
    ) -> GeneratedContent:
        from google.genai import types

        system = _build_report_system(organization_name, sections)
        meta = "\n".join(l for l in _context_meta_lines(context) if l)
        user_text = f"{meta}\n\n{_findings_block(findings)}\n\nDraft the full report now, in the structured format described above."
        data = _generate_json(system, [types.Part.from_text(text=user_text)], _REPORT_SCHEMA)
        return _parse_content(data)

    async def revise(
        self,
        organization_name: str,
        sections: list[TemplateSectionSpec],
        context: StudyContext,
        findings: StructuredFindings,
        previous: GeneratedContent,
        instruction: str,
        classification: ChangeRequestClassification,
        high_accuracy_mode: bool,
    ) -> GeneratedContent:
        from google.genai import types

        system = _build_report_system(organization_name, sections)
        previous_json = json.dumps(
            {
                "summary": previous.summary,
                "sections": [{"key": s.key, "title": s.title, "content": s.content} for s in previous.sections],
                "impression": previous.impression,
                "recommendations": previous.recommendations,
            }
        )
        meta = "\n".join(l for l in _context_meta_lines(context) if l)
        user_text = (
            f"{meta}\n\n{_findings_block(findings)}\n\n"
            f"A physician reviewed the previous draft below and requested this change:\n\"{instruction}\"\n\n"
            f"Previous draft (JSON):\n{previous_json}\n\n"
            "Return a complete, updated report in the same structured format, applying the requested change."
        )
        data = _generate_json(system, [types.Part.from_text(text=user_text)], _REPORT_SCHEMA)
        return _parse_content(data)

    async def classify_change_request(self, instruction: str, sections: list[TemplateSectionSpec]) -> ChangeRequestClassification:
        from google.genai import types

        section_keys = ", ".join(s.key for s in sections)
        system = (
            "Classify a physician's free-text request to modify a medical report draft. Decide which template "
            f"sections it targets (from: {section_keys} — empty array if it affects the whole report) and whether "
            "it is purely a formatting/wording/structure request (formattingOnly=true) versus one that requires "
            "reconsidering medical content (formattingOnly=false). When uncertain, prefer formattingOnly=false."
        )
        data = _generate_json(system, [types.Part.from_text(text=instruction)], _CLASSIFICATION_SCHEMA, max_tokens=256)
        return ChangeRequestClassification(target_sections=data.get("targetSections", []), formatting_only=data.get("formattingOnly", False))

    async def summarize_for_notification(self, modality: str, body_part: str, summary: str) -> str:
        if not settings.gemini_api_key:
            return f"AI draft ready for review — {modality} ({body_part})."
        from google.genai import types

        try:
            client = _client()
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=f"Write one short activity-feed sentence (under 15 words, no quotes) announcing that a new "
                                f"AI-drafted {modality} report is ready for physician review. Context: {summary}"
                            )
                        ],
                    )
                ],
                config=types.GenerateContentConfig(max_output_tokens=60),
            )
            return (response.text or "").strip() or f"AI draft ready for review — {modality} ({body_part})."
        except Exception:
            logger.warning("summarize_for_notification failed, using fallback text", exc_info=True)
            return f"AI draft ready for review — {modality} ({body_part})."

    async def extract_intake(self, kind: Literal["patient", "study"], message: str, known: dict[str, str]) -> dict[str, str]:
        from google.genai import types

        schema = _PATIENT_INTAKE_SCHEMA if kind == "patient" else _STUDY_INTAKE_SCHEMA
        known_lines = "\n".join(f"- {k}: {v}" for k, v in known.items() if v) or "(nothing yet)"
        system = (
            f"A physician is describing a {kind} through a conversational intake chat, one message at a time. "
            f"Extract only the fields this specific message states or clearly implies — leave a field as an "
            "empty string if this message doesn't address it. Never guess or invent a value. Already confirmed "
            f"so far (do not re-extract these unless this message changes one of them):\n{known_lines}"
        )
        data = _generate_json(system, [types.Part.from_text(text=message)], schema, max_tokens=256)
        return {k: v for k, v in data.items() if v}
