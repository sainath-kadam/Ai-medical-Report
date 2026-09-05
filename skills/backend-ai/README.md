# backend-ai

The pluggable AI provider abstraction: two narrow interfaces (image interpretation,
report-text generation) plus factory functions that pick a concrete implementation from
`AI_PROVIDER`. See CONTRACTS.md §5 (AI architecture, spec §16-18/§24).

## Key files

- `server/app/ai/base.py` — `BaseMedicalImagingProvider` (`analyze` -> `StructuredFindings`)
  and `BaseReportGenerationProvider` (`generate`/`revise`/`classify_change_request`/
  `summarize_for_notification`/`extract_intake`/`summarize_findings`), the shared
  dataclasses, and `get_imaging_provider()`/`get_report_provider()` — the only place
  deciding which concrete provider class actually runs.
- `server/app/ai/providers/anthropic_provider.py` — Claude-backed implementation of both
  interfaces, tiered by model (`fast`/`default`/`highAccuracy`/`max`).
- `server/app/ai/providers/gemini_provider.py` — Gemini-backed implementation. Flash by
  default; the org's High-Accuracy Mode toggle swaps `GEMINI_HIGH_ACCURACY_MODEL` (Pro) in
  for image interpretation + the clinical summary only (`_tiered`).
- `server/app/ai/providers/mock_provider.py` — zero-cost fallback used whenever no
  provider is configured; returns clearly-labeled placeholder content (except
  `extract_intake`, see below).

## Non-obvious things

- **`generate()` and `summarize_findings()` run concurrently** (`asyncio.gather` in
  `AnalysisService.run_analysis`/`ReportService.regenerate_report` — safe since neither
  depends on the other's output), and the caller always overwrites `generated.summary`
  with `summarize_findings()`'s result. Gemini uses four independent model settings —
  `GEMINI_IMAGING_MODEL`/`GEMINI_SUMMARY_MODEL` (both default `gemini-3.8-flash`; Pro
  models 404 or hit zero free-tier quota — verified live, see `config.py`),
  `GEMINI_HIGH_ACCURACY_MODEL` (default `gemini-3.1-pro-preview`, replaces those two while
  the org's `highAccuracyMode` is on — never `GEMINI_MODEL`, report text only rewrites
  computed findings; on a free key its flat `429 limit: 0` skips the retry delay and falls
  back to the standard model first, so the toggle is safe to leave on before billing exists),
  vs.
  Every Gemini call goes through `_generate_json`, which retries transient errors
  (429/5xx, incl. the real-world 503 "high demand") with short backoff and then fails over
  through `GEMINI_FALLBACK_MODELS` (default `gemini-3.6-flash,gemini-3.5-flash-lite` — not
  `gemini-flash-latest`, which aliases the current Flash and shares its free-tier quota of
  20 requests/day/model, so it 429s at the same moment); a
  404 model skips straight to the next. The raised `AppError` message names the HTTP status
  and models tried (`AI_QUOTA_EXCEEDED` / `AI_TEMPORARILY_UNAVAILABLE` /
  `AI_MODEL_NOT_FOUND`), so the analysis job's `error` tells the doctor what happened.
  `_generate_with_fallback` returns `(response, served_model)`: `GeneratedContent.model_used`
  and `StructuredFindings.model_used` (-> `analysis_jobs.imagingModel`) name the model that
  actually answered, including a fallback — never the one that was merely requested.
  `summarize_findings()` takes `high_accuracy_mode` (default False) on every provider for
  this; Anthropic/mock ignore it. Tests: `tests/test_gemini_model_routing.py` (fake SDK
  client, no network).
  `GEMINI_MODEL` (default `gemini-3.6-flash`, everything else) — don't assume
  `GEMINI_MODEL` alone controls Gemini. Not wired into `apply_change_request`/`revise()`
  (that path already carries the previous summary forward).
- **Every real Gemini call goes through the async SDK surface**
  (`client.aio.models.generate_content`, awaited) — the sync client would block this
  single-process server's whole event loop per call. `_generate_json` takes `model` as an
  explicit param for this reason (imaging/summary/report each pass their own) — copy that
  pattern for any new Gemini call site, don't reintroduce the sync client.
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
