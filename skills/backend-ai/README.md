# backend-ai

The pluggable AI provider abstraction: two narrow interfaces (image interpretation,
report-text generation) plus factory functions that pick a concrete implementation from
`AI_PROVIDER`. See CONTRACTS.md §5 (AI architecture, spec §16-18/§24).

## Key files

- `server/app/ai/base.py` — `BaseMedicalImagingProvider` (`analyze` -> `StructuredFindings`)
  and `BaseReportGenerationProvider` (`generate`/`revise`/`classify_change_request`/
  `summarize_for_notification`/`extract_intake`), the shared dataclasses, and
  `get_imaging_provider()`/`get_report_provider()` — the only place deciding which
  concrete provider class actually runs.
- `server/app/ai/providers/anthropic_provider.py` — Claude-backed implementation of both
  interfaces, tiered by model (`fast`/`default`/`highAccuracy`/`max`).
- `server/app/ai/providers/gemini_provider.py` — Gemini-backed implementation, one model
  for everything (no tiers).
- `server/app/ai/providers/mock_provider.py` — zero-cost fallback used whenever no
  provider is configured; returns clearly-labeled placeholder content (except
  `extract_intake`, see below).

## Non-obvious things

- **There are three providers, and the default is Gemini, not Anthropic or mock.**
  `AI_PROVIDER` (`server/app/core/config.py`) defaults to `"gemini"`.
  `get_imaging_provider()`/`get_report_provider()` check `ai_provider == "anthropic" and
  ai_api_key` first, then `ai_provider == "gemini" and gemini_api_key`, and fall back to
  mock otherwise — setting `AI_PROVIDER=anthropic` without also setting `AI_API_KEY`
  silently lands on mock. `gemini_provider.py`'s own docstring flags itself as
  **unverified against a live key** (written to match documented SDK surface only) —
  re-check it against current `google-genai` docs if it errors on first real use.
- **The two provider interfaces stay separate on purpose**, even though today's Anthropic
  and Gemini implementations both answer them from the same client. Dropping in a real
  specialized radiology model later means writing one new class implementing only
  `BaseMedicalImagingProvider`, without touching `BaseReportGenerationProvider` or
  `services`/`api`. Two real API calls happen per analysis (image interpretation, then a
  separate text-only report-writing call) — the report call never re-sends the image.
- **Safety is prompt-level, not a hard guarantee** (spec §53): every implementation's
  system prompt is written to never claim certainty the input doesn't support, never
  fabricate findings/history not present in the input, and set `analyzable=false` with a
  reason rather than guess. The real safety control is downstream — the caller (not the
  provider) always stores generated reports as `status="ai_generated"`/`author="ai"`,
  and only an explicit clinician finalize action can move a report past that.
- `MockReportProvider`/`MockImagingProvider` return an identical, clearly-labeled note for
  every field so it's never ambiguous the content isn't real. `extract_intake` is the one
  exception: since the chat-style study-intake flow is unusable with pure placeholders,
  the mock provider runs a real (if crude) regex/keyword heuristic there instead of an
  LLM call — it still never claims to be AI-generated.
