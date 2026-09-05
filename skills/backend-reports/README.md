# backend-reports

Owns the `reports` table: reading/listing reports (with study/patient/template context
attached), manual doctor edits, AI change-requests, regeneration, finalization, and PDF
rendering/download. See CONTRACTS.md §4 (table shapes), §9 (route list), §12
(cross-domain entry points).

## Key files

- `server/app/api/reports/routes.py` — list/get/versions/patch/change-request/regenerate/
  finalize/pdf-download routes, all `org_admin`/`doctor` only.
- `server/app/services/report_service.py` — the business logic: `update_report` (manual
  edit), `request_changes`/`apply_change_request` (AI revision), `regenerate_report`
  (text-only re-draft from existing findings), `finalize_report`, `amend_report` (the only
  way out of `finalized`: sets status `amended` so edit/revise/regenerate work again, then
  `finalize_report` re-locks it; audit action `REPORT_AMENDED`), `get_pdf_bytes`
  (renders-and-caches).
- `server/app/repositories/report_repository.py` — `BaseRepository` CRUD plus
  `append_version`, the one method every version-producing action goes through.
- `server/app/schemas/report.py` — request bodies only; responses are always plain dicts.
- `server/app/services/pdf_service.py` — `build_report_pdf`, a pure function (reportlab
  Platypus) rendering one report version to PDF bytes using the org's template styling.

## Non-obvious things

- **A report's content only ever grows a new version — never mutates in place.**
  `ReportRepository.append_version` reassigns `row.versions = [*row.versions, version]`
  (not `.append(...)`) so SQLAlchemy's JSON-column change tracking notices the mutation.
  Every mutating method (`update_report`, `apply_change_request`, `regenerate_report`)
  goes through this; a `finalized` report fails fast (`AppError.conflict`,
  `REPORT_FINALIZED`) before ever reaching it.
- **`request_changes`/`apply_change_request` also run synchronously in-request** (no
  background worker, same as `backend-analysis`) but still create a row in the shared
  `analysis_jobs` table and return `{jobId}`, so the frontend's existing
  `GET /analysis/jobs/{jobId}` polling keeps working — it just sees the job already
  `completed`/`failed` on the first poll. `apply_change_request` has no try/except of its
  own; `request_changes` wraps the call and marks the job `failed` on any exception.
- `regenerate_report` deliberately does NOT re-run image analysis — it re-drafts report
  text only from the study's stored `lastFindings` (fails with `STUDY_NOT_ANALYZED` if
  there are none). Re-running image analysis is `AnalysisService.run_analysis`'s job, which
  appends the new AI draft as the next version of the study's existing report (or refuses
  with `REPORT_FINALIZED` until it's amended) — see `skills/backend-ai/README.md`. Like
  `AnalysisService.run_analysis`, it runs `summarize_findings()` + `generate()` concurrently
  and overwrites `generated.summary` — see `skills/backend-ai/README.md`.
- `get_pdf_bytes` caches under a key of just `{reportId}_v{currentVersion}` — no status
  suffix, since `build_report_pdf` renders identically regardless of status (no AI/draft
  banner or wording in the document at all — see `pdf_service.py`'s docstring). A report
  changing status at the same version does not need a fresh render.
- Every read is run through `ReportService._enrich`, which nests `study` (with signed-URL
  `files` and `patient`) and `template` onto the report dict — the frontend renders off
  `report.study`/`report.template` directly, so don't skip `_enrich` in a new read path.
