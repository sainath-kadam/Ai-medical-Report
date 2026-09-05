"""Centralized Claude integration — every real (non-mock) AI call in the app goes through
this file. Swapping models, retuning prompts, or later adding a real specialized imaging
model behind `BaseMedicalImagingProvider` means editing only this module (and `base.py`'s
factory functions).

MODEL STRATEGY (carried over from the original Node prototype's ai.service.ts, ported
1:1 as it already reflected a deliberate cost/accuracy tradeoff):

    Tier          Model              Used for
    fast          claude-haiku-4-5   change-request classification, notification text,
                                      formatting-only report rewrites
    default       claude-sonnet-5    image interpretation + first-draft report writing
    highAccuracy  claude-opus-5      org opt-in (`highAccuracyMode`) for complex studies
    max           claude-fable-5     reserved for manual escalation only (not auto-selected)

Two real API calls happen per study analysis (imaging interpretation, then report
writing) rather than the one combined call the old prototype made — this is the
architectural separation spec §17 requires (medical imaging layer vs. report-generation
LLM layer are independent, swappable stages). The report-writing call is text-only (no
image re-sent), which offsets most of the added cost of splitting the call in two.

SAFETY (spec §53): every report produced here is stored by the caller with a
preliminary/AI-generated status. Prompts below explicitly instruct the model to flag
uncertainty and never fabricate findings, measurements, or history not present in the
input — but this is prompt guidance, not a guarantee; the mandatory human review step
downstream is the actual safety control.
"""

from __future__ import annotations

import json
from typing import Literal

import anthropic

from app.ai.base import (
    BaseMedicalImagingProvider,
    BaseReportGenerationProvider,
    ChangeRequestClassification,
    GeneratedContent,
    ModelTier,
    ReportSectionContent,
    StructuredFindings,
    StudyContext,
    TemplateSectionSpec,
    resolve_generation_tier,
)
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

_MODEL_FOR_TIER: dict[ModelTier, str] = {
    "fast": settings.ai_model_fast,
    "default": settings.ai_model_default,
    "highAccuracy": settings.ai_model_high_accuracy,
    "max": settings.ai_model_max,
}

# Haiku 4.5 predates the adaptive-thinking/effort parameter family and errors if sent it.
_TIER_SUPPORTS_EFFORT: dict[ModelTier, bool] = {"fast": False, "default": True, "highAccuracy": True, "max": True}

_VISION_COMPATIBLE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}

_FINDINGS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Discrete, neutral radiological observations, one per array entry. Empty if the image could not be meaningfully analyzed.",
        },
        "rawSummary": {"type": "string", "description": "1-2 sentence plain-language summary of what was observed."},
        "analyzable": {"type": "boolean", "description": "False if the source was not a directly viewable/interpretable image."},
        "unanalyzableReason": {"type": "string", "description": "If analyzable is false, state why (e.g. unsupported format)."},
    },
    "required": ["observations", "rawSummary", "analyzable"],
    "additionalProperties": False,
}

_REPORT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "A one-to-two sentence plain-language summary, for quick scanning in a list view."},
        "sections": {
            "type": "array",
            "description": "The report body. Exactly one entry per requested section key, in the given order.",
            # No "title" here on purpose -- the template already provides the authoritative
            # title for every section key (see _parse_content), and asking the model to
            # also echo one back invites it to occasionally write a full sentence into
            # "title" instead of a short label, especially on revise() (shown its own
            # previous JSON as context) -- exactly the bug that produced a duplicated
            # section heading in practice.
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Must exactly match one of the provided section keys."},
                    "content": {"type": "string", "description": "Clinical narrative for this section, in plain prose."},
                },
                "required": ["key", "content"],
                "additionalProperties": False,
            },
        },
        "impression": {"type": "string"},
        "recommendations": {"type": "string"},
    },
    "required": ["summary", "sections", "impression", "recommendations"],
    "additionalProperties": False,
}

_CLASSIFICATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "targetSections": {"type": "array", "items": {"type": "string"}, "description": "Section keys this instruction affects. Empty array means it affects the whole report."},
        "formattingOnly": {"type": "boolean", "description": "True if the instruction is purely about wording/formatting/structure and does not require re-examining the image or changing any medical content."},
    },
    "required": ["targetSections", "formattingOnly"],
    "additionalProperties": False,
}

_PATIENT_INTAKE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Patient's full name, or empty string if not stated in this message."},
        "mrn": {"type": "string", "description": "Medical record number, or empty string if not stated in this message."},
        "dateOfBirth": {"type": "string", "description": "ISO 8601 date (YYYY-MM-DD) if a date of birth was stated, else empty string."},
        "sex": {"type": "string", "description": "One of male, female, other, unspecified if stated/implied, else empty string."},
        "contactPhone": {"type": "string", "description": "Empty string if not mentioned."},
        "contactEmail": {"type": "string", "description": "Empty string if not mentioned."},
    },
    "required": ["name", "mrn", "dateOfBirth", "sex", "contactPhone", "contactEmail"],
    "additionalProperties": False,
}

_STUDY_INTAKE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "modality": {"type": "string", "description": "One of x_ray, ct, mri, ultrasound, other if stated/implied, else empty string."},
        "bodyPart": {"type": "string", "description": "Empty string if not stated in this message."},
        "studyDate": {"type": "string", "description": "ISO 8601 date (YYYY-MM-DD) if a study/scan date was stated, else empty string."},
        "clinicalHistory": {"type": "string", "description": "Relevant clinical history/symptoms/reason for the study mentioned, else empty string."},
    },
    "required": ["modality", "bodyPart", "studyDate", "clinicalHistory"],
    "additionalProperties": False,
}

_client = anthropic.AsyncAnthropic(api_key=settings.ai_api_key) if settings.ai_api_key else None


async def _call(
    tier: ModelTier,
    system_text: str,
    user_content: list[dict],
    json_schema: dict,
    max_tokens: int = 4096,
) -> dict:
    if _client is None:
        raise AppError("AI provider not configured", 503, "AI_NOT_CONFIGURED")

    model = _MODEL_FOR_TIER[tier]
    output_config: dict = {"format": {"type": "json_schema", "schema": json_schema}}
    if _TIER_SUPPORTS_EFFORT[tier]:
        output_config["effort"] = settings.ai_effort

    try:
        response = await _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
            messages=[{"role": "user", "content": user_content}],
            extra_body={"output_config": output_config},
        )
    except anthropic.RateLimitError as exc:
        raise AppError("The AI service is receiving too many requests right now. Please try again shortly.", 429, "AI_RATE_LIMITED") from exc
    except anthropic.APIConnectionError as exc:
        raise AppError("Could not reach the AI service. Check your connection and try again.", 502, "AI_CONNECTION_ERROR") from exc
    except anthropic.APIError as exc:
        logger.error("Claude API error: status=%s message=%s", getattr(exc, "status_code", None), exc)
        raise AppError("The AI service returned an error while processing this request.", 502, "AI_PROVIDER_ERROR") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise AppError.bad_request("The AI safety system declined to process this request. Please verify the input and try again.", "AI_REFUSAL")

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise AppError("The AI service returned an empty response.", 502, "AI_EMPTY_RESPONSE")

    try:
        return json.loads(text_block.text)
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


def _image_content_blocks(context: StudyContext) -> list[dict]:
    """One image block per viewable image on the study (all views/slices, in upload order),
    skipping anything the vision API can't accept (e.g. a raw DICOM or a video)."""
    import base64

    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": mime_type, "data": base64.b64encode(data).decode("ascii")},
        }
        for data, mime_type in context.all_images()
        if mime_type in _VISION_COMPATIBLE_MIME
    ]


class AnthropicImagingProvider(BaseMedicalImagingProvider):
    async def analyze(self, context: StudyContext, high_accuracy_mode: bool) -> StructuredFindings:
        tier = resolve_generation_tier(high_accuracy_mode)
        system = _safety_preamble("your organization") + (
            " Examine the provided image and return discrete, neutral observations only — do not write a full "
            "report or impression, that happens in a separate step. If the source is not a directly viewable, "
            "interpretable image (e.g. raw DICOM or video not yet extracted to a frame), set analyzable=false "
            "and explain why instead of fabricating visual observations."
        )
        image_blocks = _image_content_blocks(context)
        meta_lines = [l for l in _context_meta_lines(context) if l]
        if not image_blocks:
            meta_lines.append(
                "Note: the source file is not a directly viewable image format — set analyzable=false and "
                "unanalyzableReason accordingly."
            )
        elif len(image_blocks) > 1:
            meta_lines.append(
                f"{len(image_blocks)} images from this same study are attached (different views, series, or slices) — "
                "read them together as one examination and reconcile observations across them."
            )
        content: list[dict] = [*image_blocks, {"type": "text", "text": "\n".join(meta_lines)}]

        data = await _call(tier, system, content, _FINDINGS_JSON_SCHEMA, max_tokens=1024)
        return StructuredFindings(
            observations=data.get("observations", []),
            raw_summary=data.get("rawSummary", ""),
            analyzable=data.get("analyzable", True),
            unanalyzable_reason=data.get("unanalyzableReason"),
        )


def _build_report_system(organization_name: str, sections: list[TemplateSectionSpec]) -> str:
    enabled = sorted([s for s in sections if s.enabled], key=lambda s: s.order)
    section_list = "\n".join(f'- "{s.key}" ({s.title})' + (f" — {s.guidance}" if s.guidance else "") for s in enabled)
    return (
        _safety_preamble(organization_name)
        + "\n\nYou will be given structured findings from a separate image-analysis step (not the image itself). "
        "Write the full structured report body from those findings.\n\n"
        f"Structure the report using exactly these sections, in this order:\n{section_list}\n\n"
        "Write plain prose for each section — no markdown headers or bullet characters; the application applies "
        "the organization's own visual formatting when it renders your structured output. Keep the summary to "
        "1-2 sentences. If clinical history is provided, explicitly reconcile the findings against it. If the "
        "findings indicate the image could not be analyzed, say so plainly in the findings section instead of "
        "fabricating observations."
    )


def _findings_block(findings: StructuredFindings) -> str:
    if not findings.analyzable:
        return f"Image analysis result: NOT ANALYZABLE ({findings.unanalyzable_reason or 'unknown reason'})."
    lines = [f"Image analysis summary: {findings.raw_summary}", "Observations:"]
    lines += [f"- {o}" for o in findings.observations] or ["(none reported)"]
    return "\n".join(lines)


class AnthropicReportProvider(BaseReportGenerationProvider):
    async def generate(
        self,
        organization_name: str,
        sections: list[TemplateSectionSpec],
        context: StudyContext,
        findings: StructuredFindings,
        high_accuracy_mode: bool,
    ) -> GeneratedContent:
        tier = resolve_generation_tier(high_accuracy_mode)
        system = _build_report_system(organization_name, sections)
        meta = "\n".join(l for l in _context_meta_lines(context) if l)
        user_text = f"{meta}\n\n{_findings_block(findings)}\n\nDraft the full report now, in the structured format described above."
        data = await _call(tier, system, [{"type": "text", "text": user_text}], _REPORT_JSON_SCHEMA)
        return self._parse_content(data, _MODEL_FOR_TIER[tier], sections)

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
        # Formatting-only requests never need the higher tier — spec §18/§24: don't spend
        # more than the task requires, and don't re-run analysis that already happened.
        tier: ModelTier = "fast" if classification.formatting_only else resolve_generation_tier(high_accuracy_mode)
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
            "Return a complete, updated report in the same structured format, applying the requested change. "
            "Keep everything else consistent with the previous draft unless the requested change implies otherwise."
        )
        data = await _call(tier, system, [{"type": "text", "text": user_text}], _REPORT_JSON_SCHEMA)
        return self._parse_content(data, _MODEL_FOR_TIER[tier], sections)

    async def classify_change_request(self, instruction: str, sections: list[TemplateSectionSpec]) -> ChangeRequestClassification:
        section_keys = ", ".join(s.key for s in sections)
        system = (
            "Classify a physician's free-text request to modify a medical report draft. Decide which template "
            f"sections it targets (from: {section_keys} — empty array if it affects the whole report) and whether "
            "it is purely a formatting/wording/structure request (formattingOnly=true) versus one that requires "
            "reconsidering medical content or the underlying image (formattingOnly=false). When genuinely "
            "uncertain, prefer formattingOnly=false — it is safer to over-include a content review than to skip one."
        )
        data = await _call("fast", system, [{"type": "text", "text": instruction}], _CLASSIFICATION_JSON_SCHEMA, max_tokens=256)
        return ChangeRequestClassification(
            target_sections=data.get("targetSections", []),
            formatting_only=data.get("formattingOnly", False),
        )

    async def summarize_for_notification(self, modality: str, body_part: str, summary: str) -> str:
        if _client is None:
            return f"AI draft ready for review — {modality} ({body_part})."
        try:
            response = await _client.messages.create(
                model=_MODEL_FOR_TIER["fast"],
                max_tokens=60,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Write one short activity-feed sentence (under 15 words, no quotes) announcing that a new "
                        f"AI-drafted {modality} report is ready for physician review. Context: {summary}"
                    ),
                }],
            )
            block = next((b for b in response.content if b.type == "text"), None)
            return block.text.strip() if block else f"AI draft ready for review — {modality} ({body_part})."
        except Exception:
            logger.warning("summarize_for_notification failed, using fallback text", exc_info=True)
            return f"AI draft ready for review — {modality} ({body_part})."

    async def summarize_findings(
        self,
        organization_name: str,
        context: StudyContext,
        findings: StructuredFindings,
        high_accuracy_mode: bool = False,
    ) -> str:
        """Runs on the fast tier (haiku-4-5) regardless of `high_accuracy_mode` — distilling
        already-computed findings into a few sentences doesn't need the higher tier
        `generate()` uses (same "don't spend more than the task requires" reasoning as
        `classify_change_request`). The param exists for the Gemini provider, which tiers
        this step; see `BaseReportGenerationProvider.summarize_findings`."""
        if _client is None:
            raise AppError("AI provider not configured", 503, "AI_NOT_CONFIGURED")
        if not findings.analyzable:
            return f"Imaging could not be analyzed: {findings.unanalyzable_reason or 'unknown reason'}."
        system = _safety_preamble(organization_name) + (
            " Write a concise (2-4 sentence) plain-language clinical summary of the findings below — the "
            "at-a-glance version a physician reads before the full report. Do not include an impression or "
            "recommendations; those are separate report sections."
        )
        meta = "\n".join(l for l in _context_meta_lines(context) if l)
        user_text = f"{meta}\n\n{_findings_block(findings)}\n\nWrite the summary now."
        try:
            response = await _client.messages.create(
                model=_MODEL_FOR_TIER["fast"],
                max_tokens=300,
                system=[{"type": "text", "text": system}],
                messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
            )
        except anthropic.APIError as exc:
            logger.error("Claude summarize_findings error: %s", exc)
            raise AppError("The AI service returned an error while processing this request.", 502, "AI_PROVIDER_ERROR") from exc
        block = next((b for b in response.content if b.type == "text"), None)
        return block.text.strip() if block else findings.raw_summary

    async def extract_intake(self, kind: Literal["patient", "study"], message: str, known: dict[str, str]) -> dict[str, str]:
        schema = _PATIENT_INTAKE_JSON_SCHEMA if kind == "patient" else _STUDY_INTAKE_JSON_SCHEMA
        known_lines = "\n".join(f"- {k}: {v}" for k, v in known.items() if v) or "(nothing yet)"
        system = (
            f"A physician is describing a {kind} through a conversational intake chat, one message at a time. "
            f"Extract only the fields this specific message states or clearly implies — leave a field as an "
            "empty string if this message doesn't address it. Never guess or invent a value. Already confirmed "
            f"so far (do not re-extract these unless this message changes one of them):\n{known_lines}"
        )
        data = await _call("fast", system, [{"type": "text", "text": message}], schema, max_tokens=256)
        return {k: v for k, v in data.items() if v}

    def _parse_content(self, data: dict, model_used: str, sections: list[TemplateSectionSpec]) -> GeneratedContent:
        """`title` always comes from `sections` (the template), never from the model's
        JSON — see `_REPORT_JSON_SCHEMA`'s comment for why. A key the model returned that
        doesn't match any template section keeps its own key as a fallback title rather
        than raising, since a malformed key here shouldn't fail the entire report."""
        titles_by_key = {s.key: s.title for s in sections}
        return GeneratedContent(
            summary=data.get("summary", ""),
            sections=[
                ReportSectionContent(key=s["key"], title=titles_by_key.get(s["key"], s["key"]), content=s["content"])
                for s in data.get("sections", [])
            ],
            impression=data.get("impression", ""),
            recommendations=data.get("recommendations", ""),
            model_used=model_used,
        )
