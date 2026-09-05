"""Gemini-backed image analysis AND report generation — the `gemini` `AI_PROVIDER` option
(the default), via the `google-genai` SDK (`GEMINI_API_KEY`). Four independently
configurable models — `GEMINI_IMAGING_MODEL` (image interpretation, default
`gemini-3.8-flash`), `GEMINI_SUMMARY_MODEL` (the pre-report clinical-summary step, also
`gemini-3.8-flash` by default), `GEMINI_MODEL` (full report text — generate/revise/
classify_change_request/extract_intake, default `gemini-3.6-flash`), and
`GEMINI_HIGH_ACCURACY_MODEL` (default `gemini-3.1-pro-preview`), which stands in for the
imaging and summary models — the two steps where model quality decides what the doctor
reads — whenever the organization's High-Accuracy Mode toggle is on (see `_tiered`).
Report-text drafting stays on `GEMINI_MODEL` either way: it only rewrites findings that
were already computed, so the Pro price buys nothing there. Pro models have zero free-tier
quota (429 "limit: 0", verified live), so on a free key a high-accuracy run falls straight
back to the standard Flash model and logs that it did, instead of failing the analysis.

Every real call goes through the SDK's async surface (`client.aio.models.generate_content`,
awaited) — the sync surface (`client.models.generate_content`) would block this
single-process server's event loop for every organization, not just the caller, for the
duration of the call. Always await from an `async def` here; never add a new call site
using the sync client.

UNVERIFIED AGAINST A LIVE KEY: written to match the documented `google-genai` SDK surface
as accurately as possible, but — unlike `anthropic_provider.py`, which was tested against
real requests during development — no Gemini API key was available to actually exercise
this file. Re-check against current SDK docs if it errors on first real use.
"""

from __future__ import annotations

import asyncio
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
            # No "title" field here on purpose -- the template already provides the
            # authoritative title for every section key (see _parse_content), and asking
            # the model to also echo one back invites it to occasionally write a full
            # sentence into "title" instead of a short label (most likely on revise(),
            # which is shown its own previous JSON as context) -- exactly the bug that
            # produced a duplicated section heading in practice.
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "content": {"type": "string"}},
                "required": ["key", "content"],
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


# HTTP codes worth retrying / failing over on: rate limit, and Google-side capacity errors.
_TRANSIENT_CODES = {429, 500, 502, 503, 504}
_ATTEMPTS_PER_MODEL = 2
_RETRY_DELAYS = (1.0, 2.5)


def _fallback_models() -> list[str]:
    return [m.strip() for m in (settings.gemini_fallback_models or "").split(",") if m.strip()]


def _classify_error(exc: Exception | None, models_tried: list[str]) -> AppError:
    """Turns an SDK error into an AppError whose message says what actually went wrong, so
    the failure a doctor sees on the analysis job ("why is there no report?") is actionable
    instead of a generic 'AI error'. Never echoes request content — only the HTTP status and
    the model names, which are configuration, not patient data."""
    code = getattr(exc, "code", None)
    tried = ", ".join(models_tried)
    if code == 429:
        message = (
            f"The AI provider's quota for this API key is exhausted (Gemini 429; tried {tried}). "
            "Check the Gemini plan/billing, or try again later."
        )
        error_code = "AI_QUOTA_EXCEEDED"
    elif code in (500, 502, 503, 504):
        message = (
            f"The AI model is temporarily overloaded (Gemini {code}; tried {tried}). "
            "Please retry in a minute."
        )
        error_code = "AI_TEMPORARILY_UNAVAILABLE"
    elif code == 404:
        message = (
            f"The configured Gemini model was not found (tried {tried}). "
            "Check GEMINI_MODEL / GEMINI_IMAGING_MODEL / GEMINI_SUMMARY_MODEL / GEMINI_HIGH_ACCURACY_MODEL / "
            "GEMINI_FALLBACK_MODELS."
        )
        error_code = "AI_MODEL_NOT_FOUND"
    elif code in (401, 403):
        message = f"Gemini rejected the API key (HTTP {code}). Check GEMINI_API_KEY."
        error_code = "AI_NOT_CONFIGURED"
    elif code is None and isinstance(exc, (json.JSONDecodeError, ValueError)):
        message = f"The AI model returned an incomplete or malformed answer (tried {tried}). Please retry."
        error_code = "AI_MALFORMED_RESPONSE"
    else:
        message = "The AI service returned an error while processing this request."
        error_code = "AI_PROVIDER_ERROR"
    return AppError(message, 502, error_code)


def _tiered(standard_model: str, high_accuracy_mode: bool) -> tuple[str, tuple[str, ...]]:
    """Which model to request, plus the models to try *before* GEMINI_FALLBACK_MODELS if it
    can't serve. High-Accuracy Mode asks for GEMINI_HIGH_ACCURACY_MODEL and keeps the
    standard model as the very next fallback, so a key whose plan can't run Pro degrades to
    exactly what standard mode would have used — not to an arbitrary entry of the generic
    chain. Standard mode is just the standard model."""
    if high_accuracy_mode and settings.gemini_high_accuracy_model:
        return settings.gemini_high_accuracy_model, (standard_model,)
    return standard_model, ()


def _quota_permanently_zero(exc: Exception) -> bool:
    """A 429 whose message says `limit: 0` is not a rate limit that clears in a minute — it
    is a model this API key's plan cannot call at all (live example: every Pro model on a
    free-tier key). Waiting and retrying the same model is pure delay; fail over at once."""
    return getattr(exc, "code", None) == 429 and "limit: 0" in str(exc)


async def _generate_with_fallback(
    client, model: str, contents: list, config, *, preferred_fallbacks: tuple[str, ...] = ()
) -> tuple[object, str]:
    """The one place every real Gemini `generate_content` call for the report pipeline goes
    through (JSON steps via `_generate_json_traced`, the plain-text `summarize_findings`
    directly). Returns `(response, served_model)` — callers record `served_model` (e.g.
    `GeneratedContent.model_used`, `StructuredFindings.model_used`) so a report never claims
    a model that actually failed and was substituted.

    Resilience, verified against live failures: the requested model is tried first, with
    short backoff retries on transient errors (503 "high demand", 429, 5xx); if it stays
    unavailable — or doesn't exist at all (404), or its quota is a flat zero on this plan —
    the same request moves on to each `preferred_fallbacks` entry, then each
    GEMINI_FALLBACK_MODELS entry in turn. One upstream hiccup must not fail a doctor's
    whole upload. Auth/bad-request errors are not retried anywhere: they won't get better.
    Raises the classified `AppError` from `_classify_error` once the whole chain is spent."""
    model_chain = [model]
    for m in [*preferred_fallbacks, *_fallback_models()]:
        if m and m not in model_chain:
            model_chain.append(m)
    last_exc: Exception | None = None
    for candidate in model_chain:
        for attempt in range(_ATTEMPTS_PER_MODEL):
            try:
                response = await client.aio.models.generate_content(model=candidate, contents=contents, config=config)
                if candidate != model:
                    logger.warning("Gemini request served by fallback model %s (requested %s)", candidate, model)
                return response, candidate
            except Exception as exc:  # SDK exception hierarchy varies by version — classify by HTTP code
                last_exc = exc
                code = getattr(exc, "code", None)
                if _quota_permanently_zero(exc):
                    logger.warning(
                        "Gemini %s is not available on this API key's plan (429, limit 0) — trying next model in chain",
                        candidate,
                    )
                    break  # next candidate, no retry delay: this never clears on its own
                # Truncated or invalid JSON from the model — the SDK raises while parsing a
                # schema-constrained response, seen live when a "thinking" model spent the
                # output budget before finishing the JSON — is a bad roll, not a bad request:
                # retry, then fail over, exactly like a 503.
                transient = code in _TRANSIENT_CODES or (code is None and isinstance(exc, (json.JSONDecodeError, ValueError)))
                if transient and attempt < _ATTEMPTS_PER_MODEL - 1:
                    delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                    logger.warning("Gemini %s transient error %s — retrying in %.1fs", candidate, code or type(exc).__name__, delay)
                    await asyncio.sleep(delay)
                    continue
                if transient or code == 404:
                    logger.warning("Gemini %s unavailable (%s) — trying next model in chain", candidate, code)
                    break  # next candidate
                logger.error("Gemini API error on %s: %s", candidate, exc)
                raise _classify_error(exc, [candidate]) from exc

    logger.error("Gemini API error after trying %s: %s", model_chain, last_exc)
    raise _classify_error(last_exc, model_chain) from last_exc


async def _generate_json_traced(
    model: str,
    system_text: str,
    parts: list,
    schema: dict,
    max_tokens: int = 4096,
    *,
    preferred_fallbacks: tuple[str, ...] = (),
) -> tuple[dict, str]:
    """`model` is passed in explicitly (never read from `settings` internally) so callers
    that need different models — imaging (`GEMINI_IMAGING_MODEL`, or the high-accuracy
    model) vs. full report text (`GEMINI_MODEL`) vs. classification/intake (also
    `GEMINI_MODEL`) — can each pass their own. Returns `(parsed_json, served_model)`; see
    `_generate_with_fallback` for why the served model comes back too. Uses the SDK's async
    surface (`client.aio.*`) rather than the sync one — the sync client blocks the calling
    thread for the full round-trip, which would freeze this single-process server's entire
    event loop (every organization's requests) for the duration of any one Gemini call if
    used from an `async def` method without an `await`, as this file used to do."""
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system_text,
        response_mime_type="application/json",
        response_schema=schema,
        max_output_tokens=max_tokens,
    )
    response, served_model = await _generate_with_fallback(
        _client(), model, [types.Content(role="user", parts=parts)], config, preferred_fallbacks=preferred_fallbacks
    )

    if not response.text:
        raise AppError("The AI service returned an empty response.", 502, "AI_EMPTY_RESPONSE")
    try:
        return json.loads(response.text), served_model
    except json.JSONDecodeError as exc:
        raise AppError("The AI service returned a response in an unexpected format.", 502, "AI_MALFORMED_RESPONSE") from exc


async def _generate_json(model: str, system_text: str, parts: list, schema: dict, max_tokens: int = 4096) -> dict:
    """`_generate_json_traced` for call sites that don't record which model served
    (classification, intake)."""
    data, _ = await _generate_json_traced(model, system_text, parts, schema, max_tokens)
    return data


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


def _parse_content(data: dict, sections: list[TemplateSectionSpec], model_used: str) -> GeneratedContent:
    """`title` always comes from `sections` (the template), never from the model's JSON —
    see `_REPORT_SCHEMA`'s comment for why. A key the model returned that doesn't match any
    template section keeps its own key as a fallback title rather than raising, since a
    malformed key here shouldn't fail the entire report."""
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
        images = context.all_images()
        for data, mime_type in images:
            parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
        if not images:
            meta_lines.append("Note: the source file is not a directly viewable image format.")
        elif len(images) > 1:
            meta_lines.append(
                f"{len(images)} images from this same study are attached (different views, series, or slices) — "
                "read them together as one examination and reconcile observations across them."
            )
        parts.append(types.Part.from_text(text="\n".join(meta_lines)))

        # Generous caps everywhere below: on Gemini 3.x the model's internal "thinking" tokens
        # count against max_output_tokens, and a cap sized for the visible JSON alone (this
        # was 1024) truncated the findings mid-object in live use. A high cap costs nothing
        # unless used.
        model, preferred = _tiered(settings.gemini_imaging_model, high_accuracy_mode)
        data, served_model = await _generate_json_traced(
            model, system, parts, _FINDINGS_SCHEMA, max_tokens=8192, preferred_fallbacks=preferred
        )
        return StructuredFindings(
            observations=data.get("observations", []),
            raw_summary=data.get("rawSummary", ""),
            analyzable=data.get("analyzable", True),
            unanalyzable_reason=data.get("unanalyzableReason"),
            model_used=served_model,
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
        data, served_model = await _generate_json_traced(
            settings.gemini_model, system, [types.Part.from_text(text=user_text)], _REPORT_SCHEMA
        )
        return _parse_content(data, sections, served_model)

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
        data, served_model = await _generate_json_traced(
            settings.gemini_model, system, [types.Part.from_text(text=user_text)], _REPORT_SCHEMA
        )
        return _parse_content(data, sections, served_model)

    async def classify_change_request(self, instruction: str, sections: list[TemplateSectionSpec]) -> ChangeRequestClassification:
        from google.genai import types

        section_keys = ", ".join(s.key for s in sections)
        system = (
            "Classify a physician's free-text request to modify a medical report draft. Decide which template "
            f"sections it targets (from: {section_keys} — empty array if it affects the whole report) and whether "
            "it is purely a formatting/wording/structure request (formattingOnly=true) versus one that requires "
            "reconsidering medical content (formattingOnly=false). When uncertain, prefer formattingOnly=false."
        )
        data = await _generate_json(settings.gemini_model, system, [types.Part.from_text(text=instruction)], _CLASSIFICATION_SCHEMA, max_tokens=2048)
        return ChangeRequestClassification(target_sections=data.get("targetSections", []), formatting_only=data.get("formattingOnly", False))

    async def summarize_for_notification(self, modality: str, body_part: str, summary: str) -> str:
        if not settings.gemini_api_key:
            return f"AI draft ready for review — {modality} ({body_part})."
        from google.genai import types

        try:
            client = _client()
            response = await client.aio.models.generate_content(
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

    async def summarize_findings(
        self,
        organization_name: str,
        context: StudyContext,
        findings: StructuredFindings,
        high_accuracy_mode: bool = False,
    ) -> str:
        """Runs on `GEMINI_SUMMARY_MODEL` (default `gemini-3.8-flash`) — deliberately a
        different model setting than `GEMINI_MODEL` (used by `generate()`/`revise()`
        below), so this step can be tuned/swapped independently of full report drafting.
        With High-Accuracy Mode on it runs on `GEMINI_HIGH_ACCURACY_MODEL` instead, like
        `analyze()`: this summary is the first thing the physician reads."""
        if not findings.analyzable:
            return f"Imaging could not be analyzed: {findings.unanalyzable_reason or 'unknown reason'}."
        from google.genai import types

        system = _safety_preamble(organization_name) + (
            " Write a concise (2-4 sentence) plain-language clinical summary of the findings below — the "
            "at-a-glance version a physician reads before the full report. Do not include an impression or "
            "recommendations; those are separate report sections."
        )
        meta = "\n".join(l for l in _context_meta_lines(context) if l)
        user_text = f"{meta}\n\n{_findings_block(findings)}\n\nWrite the summary now."
        # Same retry + model-fallback path as every other pipeline call — this step failing
        # on a transient 503 used to sink the whole analysis after imaging had succeeded.
        model, preferred = _tiered(settings.gemini_summary_model, high_accuracy_mode)
        response, _ = await _generate_with_fallback(
            _client(),
            model,
            [types.Content(role="user", parts=[types.Part.from_text(text=user_text)])],
            types.GenerateContentConfig(system_instruction=system, max_output_tokens=2048),
            preferred_fallbacks=preferred,
        )
        return (response.text or "").strip() or findings.raw_summary

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
        data = await _generate_json(settings.gemini_model, system, [types.Part.from_text(text=message)], schema, max_tokens=2048)
        return {k: v for k, v in data.items() if v}
