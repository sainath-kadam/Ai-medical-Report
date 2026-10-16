"""The AI provider abstraction (spec §16-18, CONTRACTS.md §5).

Two interfaces, kept deliberately separate even though the v1 Anthropic implementation
answers both from the same model family:

  BaseMedicalImagingProvider  — looks at the actual pixels, produces StructuredFindings.
  BaseReportGenerationProvider — turns findings + a template into report prose.

This is the seam: dropping in a real specialized radiology model later means writing one
new class that implements `BaseMedicalImagingProvider` and pointing `AI_PROVIDER` (or a
new dedicated `IMAGING_PROVIDER` env var, added when that day comes) at it. Nothing in
`services/` or `api/` changes.

SAFETY (spec §53): every implementation of these interfaces must —
  - never claim certainty the source data does not support,
  - never invent findings, measurements, or clinical history not present in the input,
  - explicitly say so when it could not analyze the image (unsupported format, unreadable
    file, etc.) instead of fabricating an observation,
  - return content that is always labeled AI-generated/preliminary by the caller (the
    provider itself doesn't stamp report status — `report_service.py` does).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings

ModelTier = Literal["fast", "default", "highAccuracy", "max"]


@dataclass
class StudyContext:
    modality: str
    body_part: str
    patient_age: int | None = None
    patient_sex: str | None = None
    clinical_history: str | None = None
    # The study's primary image (first upload). Kept for backward compatibility — every
    # provider should read `all_images()` instead, which also covers the rest of the files.
    image_bytes: bytes | None = None
    image_mime_type: str | None = None
    # Every viewable image on the study, in upload order, as (bytes, mime_type). A study is
    # routinely more than one file (AP + lateral view, several CT slices, a follow-up added
    # later), and the model must read them together as one examination — so a re-run after
    # a new upload genuinely takes the new image into account in the next version.
    images: list[tuple[bytes, str]] = field(default_factory=list)

    def all_images(self) -> list[tuple[bytes, str]]:
        if self.images:
            return self.images
        if self.image_bytes and self.image_mime_type:
            return [(self.image_bytes, self.image_mime_type)]
        return []


@dataclass
class StructuredFindings:
    observations: list[str] = field(default_factory=list)
    raw_summary: str = ""
    analyzable: bool = True
    unanalyzable_reason: str | None = None
    # The model that actually produced these findings, when the provider knows (Gemini
    # sets it — including when a fallback model served, see gemini_provider). Recorded on
    # `analysis_jobs.imagingModel`; `None` means "use the provider's configured name".
    model_used: str | None = None


@dataclass
class ReportSectionContent:
    key: str
    title: str
    content: str


@dataclass
class GeneratedContent:
    summary: str
    sections: list[ReportSectionContent]
    impression: str
    recommendations: str
    model_used: str


@dataclass
class ChangeRequestClassification:
    formatting_only: bool


@dataclass
class TemplateSectionSpec:
    key: str
    title: str
    order: int
    enabled: bool
    guidance: str | None = None


def resolve_generation_tier(high_accuracy_mode: bool) -> ModelTier:
    return "highAccuracy" if high_accuracy_mode else "default"


class BaseMedicalImagingProvider(ABC):
    @abstractmethod
    async def analyze(self, context: StudyContext, high_accuracy_mode: bool) -> StructuredFindings: ...


class BaseReportGenerationProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        organization_name: str,
        sections: list[TemplateSectionSpec],
        context: StudyContext,
        findings: StructuredFindings,
        high_accuracy_mode: bool,
    ) -> GeneratedContent: ...

    @abstractmethod
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
    ) -> GeneratedContent: ...

    @abstractmethod
    async def classify_change_request(self, instruction: str) -> ChangeRequestClassification: ...

    @abstractmethod
    async def summarize_findings(
        self,
        organization_name: str,
        context: StudyContext,
        findings: StructuredFindings,
        high_accuracy_mode: bool = False,
    ) -> str:
        """Distills `findings` into a short (2-4 sentence), physician-facing clinical
        summary as its own call. Only used with High-Accuracy Mode
        (`analysis_service.generate_report_content`): there it runs on the stronger model
        (Gemini: GEMINI_HIGH_ACCURACY_MODEL) concurrently with `generate()`, and its result
        replaces `generate()`'s own summary. In standard mode `generate()`'s summary is used
        and this isn't called. Same safety rule as `generate()`: never invent content
        beyond `findings`."""
        ...



def is_ai_configured() -> bool:
    return settings.ai_configured


def get_imaging_provider() -> BaseMedicalImagingProvider:
    from app.ai.providers.mock_provider import MockImagingProvider

    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        from app.ai.providers.anthropic_provider import AnthropicImagingProvider

        return AnthropicImagingProvider()
    if settings.ai_provider == "gemini" and settings.gemini_api_key:
        from app.ai.providers.gemini_provider import GeminiImagingProvider

        return GeminiImagingProvider()
    return MockImagingProvider()


def get_report_provider() -> BaseReportGenerationProvider:
    from app.ai.providers.mock_provider import MockReportProvider

    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        from app.ai.providers.anthropic_provider import AnthropicReportProvider

        return AnthropicReportProvider()
    if settings.ai_provider == "gemini" and settings.gemini_api_key:
        from app.ai.providers.gemini_provider import GeminiReportProvider

        return GeminiReportProvider()
    return MockReportProvider()
