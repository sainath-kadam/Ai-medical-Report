# backend-analysis

Triggers and tracks the AI-analysis pipeline for a study: image interpretation -> report
drafting -> a new `reports` row, plus the `analysis_jobs` rows the frontend polls for
progress. See CONTRACTS.md §7 (background jobs — removed) and §9 (route list) for the
wire contract this domain implements.

## Key files

- `server/app/api/analysis/routes.py` — `POST /analysis/studies/{id}/analyze` (kicks off
  a run) and two read-only routes: `GET /analysis/jobs/{jobId}` and
  `GET /analysis/studies/{id}/jobs` (list, paginated).
- `server/app/services/analysis_service.py` — `AnalysisService.start_analysis` (creates
  the `queued` job row) and `AnalysisService.run_analysis` (does the actual work: loads
  study/patient/org/template, calls the imaging provider then the report provider,
  inserts the `reports` row, flips the job to `completed`/`failed`).
- `server/app/repositories/analysis_job_repository.py` — thin `BaseRepository` over the
  `analysis_jobs` table; no custom methods, just inherited `list_scoped`/`update_scoped`.

## Non-obvious things

- **There is no background worker.** `start_analysis` creates the job row and then calls
  `run_analysis` inline, in the same request — the whole imaging + report-generation
  round trip happens before the HTTP response returns. Redis/ARQ were removed; the two
  GET routes still exist purely so the frontend's existing polling UI keeps working (it
  just sees the job already `completed`/`failed` on its very first poll instead of
  watching it progress). Don't "fix" this by adding an early return — CLAUDE.md and this
  module's docstrings both call it out as a deliberate, temporary simplification.
- `run_analysis(study_id, organization_id)` takes no `job_id` — that's a leftover of the
  worker-based signature. It re-finds "the most recently created `queued` job for this
  study" itself (`_acquire_job`), and falls back to creating one if none exists (so it
  also works if called directly, e.g. from a test, without going through the route
  first). If you ever see two jobs racing for the same study, this lookup is why.
- `start_analysis` swallows any exception from `run_analysis` (catches it, sets
  `report = None`) so the route can still return a `jobId` to poll even on failure — the
  actual error is only visible via the job's `error` field, never re-raised to the
  caller. `_IN_FLIGHT_STATUSES` (`queued`/`preprocessing`/`analyzing`/
  `generating_report`) is what makes a second `analyze` call on the same study fail with
  `ANALYSIS_ALREADY_IN_PROGRESS` instead of racing the first one on `study.status`.
- `start_analysis` is also called from `POST /studies/intake` (a different domain,
  `app/api/studies/routes.py`) — it's the shared entry point for both flows, not
  analysis-domain-private.
