"""Gemini model routing — which model each pipeline step asks for, and what happens when
that model can't serve. No network: `gemini_provider._client` is replaced with a fake whose
`aio.models.generate_content` is scripted per model name, so these run under the same
`AI_PROVIDER=mock` env as every other test.

Why these exist: High-Accuracy Mode (Organization Settings) is the one lever a clinic has
over report quality, and on a free-tier Gemini key the Pro model it asks for returns a
flat `429 ... limit: 0`. The provider must (a) escalate exactly the image-reading and
summary steps, never the report-text one, (b) fall back to the *standard* model, without
a retry delay, when Pro isn't available on the plan, and (c) record the model that
actually served, so `reportModel`/`imagingModel` never name a model that 429'd.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.base import StructuredFindings, StudyContext, TemplateSectionSpec
from app.ai.providers import gemini_provider as gp
from app.core.config import settings

_FINDINGS_JSON = '{"observations": ["clear lungs"], "rawSummary": "normal study", "analyzable": true}'
_REPORT_JSON = (
    '{"summary": "s", "sections": [{"key": "findings", "content": "c"}], "impression": "i", "recommendations": "r"}'
)


class _SdkError(Exception):
    """Stands in for the google-genai error classes, which expose the HTTP status as `.code`."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class _FakeModels:
    def __init__(self, script) -> None:
        self.script = script  # model name -> str response text | Exception | list of those (per attempt)
        self.calls: list[str] = []

    async def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        outcome = self.script(model, config)
        if isinstance(outcome, list):
            outcome = outcome.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


def _answer_for(config) -> str:
    """Pick a well-formed answer for whichever JSON schema the call asked for. The SDK's
    `GenerateContentConfig` may keep `response_schema` as the dict we passed or convert it
    to its own `Schema` model, so look at the property names rather than object identity."""
    schema = getattr(config, "response_schema", None)
    props = schema.get("properties") if isinstance(schema, dict) else getattr(schema, "properties", None)
    keys = set(props or {})
    if "observations" in keys:
        return _FINDINGS_JSON
    if "impression" in keys:
        return _REPORT_JSON
    return "plain summary text"


@pytest.fixture
def gemini(monkeypatch):
    """Configured Gemini provider pair with distinct model names per setting, a scripted
    fake SDK client, and `asyncio.sleep` recorded instead of slept."""
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_imaging_model", "std-imaging")
    monkeypatch.setattr(settings, "gemini_summary_model", "std-summary")
    monkeypatch.setattr(settings, "gemini_model", "std-text")
    monkeypatch.setattr(settings, "gemini_high_accuracy_model", "pro")
    monkeypatch.setattr(settings, "gemini_fallback_models", "generic-fallback")
    sleeps: list[float] = []

    async def _no_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(gp.asyncio, "sleep", _no_sleep)

    def _install(failures: dict[str, object] | None = None):
        failures = failures or {}

        def script(model, config):
            if model in failures:
                return failures[model]
            return _answer_for(config)

        models = _FakeModels(script)
        monkeypatch.setattr(gp, "_client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
        return models

    return SimpleNamespace(install=_install, sleeps=sleeps)


def _ctx() -> StudyContext:
    return StudyContext(modality="X-ray", body_part="Chest", images=[(b"not-a-real-png", "image/png")])


def _sections() -> list[TemplateSectionSpec]:
    return [TemplateSectionSpec(key="findings", title="Findings", order=1, enabled=True)]


@pytest.mark.asyncio
async def test_standard_mode_uses_the_three_standard_models(gemini):
    models = gemini.install()
    findings = await gp.GeminiImagingProvider().analyze(_ctx(), high_accuracy_mode=False)
    report = gp.GeminiReportProvider()
    await report.summarize_findings("Org", _ctx(), findings, high_accuracy_mode=False)
    generated = await report.generate("Org", _sections(), _ctx(), findings, high_accuracy_mode=False)

    assert models.calls == ["std-imaging", "std-summary", "std-text"]
    assert findings.model_used == "std-imaging"
    assert generated.model_used == "std-text"
    assert gemini.sleeps == []


@pytest.mark.asyncio
async def test_high_accuracy_escalates_imaging_and_summary_but_not_report_text(gemini):
    models = gemini.install()
    findings = await gp.GeminiImagingProvider().analyze(_ctx(), high_accuracy_mode=True)
    report = gp.GeminiReportProvider()
    await report.summarize_findings("Org", _ctx(), findings, high_accuracy_mode=True)
    generated = await report.generate("Org", _sections(), _ctx(), findings, high_accuracy_mode=True)

    # Pro for the two steps that decide what the doctor reads; report text stays cheap.
    assert models.calls == ["pro", "pro", "std-text"]
    assert findings.model_used == "pro"
    assert generated.model_used == "std-text"


@pytest.mark.asyncio
async def test_pro_with_zero_quota_falls_back_to_the_standard_model_with_no_retry_delay(gemini):
    # The literal shape of the live free-tier response for every Pro model.
    zero_quota = _SdkError(
        429,
        "429 RESOURCE_EXHAUSTED. You exceeded your current quota ... "
        "Quota exceeded for metric: generate_content_free_tier_requests, limit: 0, model: gemini-3.1-pro",
    )
    models = gemini.install({"pro": zero_quota})
    findings = await gp.GeminiImagingProvider().analyze(_ctx(), high_accuracy_mode=True)
    summary = await gp.GeminiReportProvider().summarize_findings("Org", _ctx(), findings, high_accuracy_mode=True)

    # Straight to the standard model (not the generic chain), one attempt at Pro each, no backoff.
    assert models.calls == ["pro", "std-imaging", "pro", "std-summary"]
    assert findings.model_used == "std-imaging"
    assert summary == "plain summary text"
    assert gemini.sleeps == []


@pytest.mark.asyncio
async def test_transient_error_retries_once_then_fails_over_and_records_the_server(gemini):
    busy = _SdkError(503, "503 UNAVAILABLE. This model is currently experiencing high demand.")
    models = gemini.install({"std-text": [busy, busy]})
    generated = await gp.GeminiReportProvider().generate("Org", _sections(), _ctx(), StructuredFindings(), False)

    assert models.calls == ["std-text", "std-text", "generic-fallback"]
    assert gemini.sleeps == [1.0]
    assert generated.model_used == "generic-fallback"  # never the model that 503'd


@pytest.mark.asyncio
async def test_whole_chain_exhausted_raises_actionable_quota_error(gemini):
    zero_quota = _SdkError(429, "quota ... limit: 0, model: x")
    gemini.install({"pro": zero_quota, "std-imaging": zero_quota, "generic-fallback": zero_quota})
    with pytest.raises(gp.AppError) as excinfo:
        await gp.GeminiImagingProvider().analyze(_ctx(), high_accuracy_mode=True)
    assert excinfo.value.code == "AI_QUOTA_EXCEEDED"
    assert "pro, std-imaging, generic-fallback" in excinfo.value.message
