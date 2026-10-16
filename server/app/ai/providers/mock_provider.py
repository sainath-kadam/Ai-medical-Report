"""No-API-key fallback. Every method returns clearly-labeled placeholder content so local
development and CI never require a real Anthropic key, and so it's never ambiguous to a
reader (or, critically, to a doctor in a demo environment) that this is not a real AI
analysis (spec §53 — never let AI output look more authoritative than it is)."""

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

    async def classify_change_request(self, instruction: str) -> ChangeRequestClassification:
        return ChangeRequestClassification(formatting_only=False)

    async def summarize_findings(self, organization_name, context, findings, high_accuracy_mode=False) -> str:
        return _MOCK_NOTE

    def _mock_content(self, sections: list[TemplateSectionSpec]) -> GeneratedContent:
        enabled = sorted([s for s in sections if s.enabled], key=lambda s: s.order)
        return GeneratedContent(
            summary=_MOCK_NOTE,
            sections=[ReportSectionContent(key=s.key, title=s.title, content=_MOCK_NOTE) for s in enabled],
            impression=_MOCK_NOTE,
            recommendations=_MOCK_NOTE,
            model_used="mock (no AI_API_KEY configured)",
        )
