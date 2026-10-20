"""The clinical instructions sent to the AI (app/ai/prompts.py): a systematic search pattern
per region, every finding including small/incidental ones, and a report that keeps them
all — the fix for physician feedback that small details were being missed."""

from __future__ import annotations

import pytest

from app.ai.base import TemplateSectionSpec
from app.ai.prompts import REPORT_DETAIL_RULES, _checklist, imaging_instructions


@pytest.mark.parametrize(
    ("modality", "body_part", "expected"),
    [
        ("x_ray", "Chest", "costophrenic"),
        ("x_ray", "Ribs", "costophrenic"),
        ("mri", "Brain", "mastoid"),
        ("ct", "Head", "mastoid"),
        ("mri", "Thoracic spine", "neural foramina"),  # not the chest pattern
        ("mri", "Lumbar spine", "neural foramina"),
        ("x_ray", "Left knee", "every cortex"),
        ("x_ray", "Right forearm", "every cortex"),
        ("x_ray", "Femoral head", "every cortex"),  # not the brain pattern
        ("ct", "Abdomen", "hydronephrosis"),
        ("ultrasound", "Kidney", "hydronephrosis"),
        ("ultrasound", "Thyroid", "calipers"),
        ("other", "Neck", "edges and corners"),
        ("x_ray", "", "edges and corners"),
    ],
)
def test_each_region_gets_its_own_search_pattern(modality, body_part, expected):
    assert expected in _checklist(modality, body_part)


def test_imaging_instructions_ask_for_every_finding_with_details_and_tags():
    text = imaging_instructions("x_ray", "Chest")

    assert "costophrenic" in text  # the region's checklist is included
    for required in ("EVERY finding", "incidental", "location and side", "severity", "[Major]", "[Minor]",
                     "[Incidental]", "[Normal]", "[Technique]", "never fabricate"):
        assert required.lower() in text.lower(), required


def test_report_rules_forbid_dropping_small_findings():
    for required in ("EVERY observation", "no finding may be dropped", "[Minor] and [Incidental]",
                     "pertinent normals", "numbered list", "Never call the study normal"):
        assert required in REPORT_DETAIL_RULES, required


@pytest.mark.parametrize("provider", ["gemini", "anthropic"])
def test_both_providers_send_the_detail_rules(provider):
    if provider == "gemini":
        from app.ai.providers.gemini_provider import _build_report_system
    else:
        pytest.importorskip("anthropic")
        from app.ai.providers.anthropic_provider import _build_report_system

    system = _build_report_system("Org", [TemplateSectionSpec(key="findings", title="Findings", order=1, enabled=True)])
    assert REPORT_DETAIL_RULES in system


async def test_gemini_imaging_call_uses_the_systematic_instructions(monkeypatch):
    from app.ai.base import StudyContext
    from app.ai.providers import gemini_provider as gp
    from app.core.config import settings

    captured = {}

    async def _fake(model, system, parts, schema, max_tokens=4096, *, preferred_fallbacks=()):
        captured["system"] = system
        return {"observations": [], "rawSummary": "", "analyzable": True}, model

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(gp, "_generate_json_traced", _fake)
    context = StudyContext(modality="mri", body_part="Brain", images=[(b"\x89PNG", "image/png")])
    await gp.GeminiImagingProvider().analyze(context, high_accuracy_mode=False)

    assert imaging_instructions("mri", "Brain") in captured["system"]
