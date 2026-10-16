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

- **Analysis runs as an in-process background task** (`settings.analysis_in_background`,
  default true). `start_analysis` creates the `queued` job, schedules
  `_run_analysis_in_background` (`app/core/background.schedule`, its own DB session) and
  returns `{jobId, report: None}` at once; the frontend polls `GET /analysis/jobs/{id}`
  (Dashboard after intake, StudyDetail for re-runs). A failure is recorded on the job by
  `run_analysis` itself. Startup runs `fail_interrupted_analyses`: jobs still in flight
  from a previous process become `failed` / `ANALYSIS_INTERRUPTED`, otherwise the
  "already in progress" guard would block that study forever. `ANALYSIS_IN_BACKGROUND=
  false` restores the old inline behavior (report in the response) — tests use it via
  conftest; `tests/test_background_analysis.py` covers the background mode.
- **Gemini failover is immediate on 503/429** (`_SWITCH_MODEL_CODES` in
  gemini_provider.py): a busy or rate-limited model hands the request to the next model
  in the chain without a same-model retry (each 503 takes 4-8s to come back); only the
  last model in the chain retries.
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
