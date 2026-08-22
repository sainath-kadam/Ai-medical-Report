# backend-studies

CRUD for the `studies` entity (an imaging study belonging to a patient) plus the combined
`POST /studies/intake` flow that creates a patient (or reuses one), a study, uploads a file,
and optionally runs AI analysis — all in one request. See CONTRACTS.md §4 for the table
shape and §3 for RBAC (`org_admin`/`doctor`, uniformly across every route).

## Key files

- `server/app/api/studies/routes.py` — list/create/get/update/delete, plus
  `POST /studies/intake` (multipart form: file + modality/bodyPart/studyDate/... +
  either `patientId` or new-patient fields). `POST /studies/intake` gates on
  `require_active_subscription` only when `run_analysis` is true — a draft-only submission
  shouldn't be blocked by trial/subscription limits.
- `server/app/services/study_service.py` — the logic, plus `with_signed_urls(study)`, a
  module-level helper (not a private method) that attaches a short-lived `signedUrl` to each
  embedded file. It's shared by three call sites: this module, `ReportService._enrich`, and
  `app/api/uploads/routes.py` — reuse it rather than re-deriving the `{**f, "signedUrl":...}`
  comprehension elsewhere.
- `server/app/repositories/study_repository.py` — `BaseRepository` (table `studies`) plus
  `add_file`, `set_last_findings`, and `find_file_by_storage_key` (CONTRACTS.md §12 names
  these methods exactly — other domains, e.g. uploads, import them by this signature).
- `server/app/schemas/study.py` — `StudyCreate`/`StudyUpdate`. Both coerce `studyDate` from
  either a bare date or a full ISO datetime string down to just the date portion, since
  `Date.prototype.toISOString()` on the frontend produces the latter and pydantic's default
  `date` parsing would otherwise reject it.

## Non-obvious things

- **`status` is never client-settable.** It starts at `"uploaded"` on creation and is only
  ever advanced by the analysis pipeline (`AnalysisService`) — not present on `StudyUpdate`
  at all, so there's no PATCH path that can touch it. If a report ever needs a way to force a
  study's status, that has to go through the analysis/report services, not this one.
- **`files` is a real child table (`StudyFile`/`study_files`), not a JSON/embedded array**,
  even though the wire shape (`study.files: [...]`) looks like one. `StudyRepository`
  re-attaches the current rows onto every returned study dict itself (`_attach_files`,
  called from `find_by_id`, `find_by_id_scoped`, `list_scoped`) — `insert`/`update_scoped`
  both strip any `files` key from the incoming dict before writing, so you cannot set files
  by passing them in a create/update payload; use `add_file` instead.
- **`create_from_intake` doesn't duplicate logic** — it calls straight through to
  `PatientService.create_patient` (or reuses an existing patient id), `self.create_study`,
  `UploadService.upload_file`, then `AnalysisService.start_analysis`, in that order. Exactly
  one of `patient_id`/`new_patient` is expected; the route (not the service) validates that
  invariant before calling in.
- **`assignedDoctorId` is not an access-control field** — it just records who's the
  reviewing clinician of record. Assigning it validates the target user belongs to the same
  org and has role `org_admin`/`doctor` (`_require_assignable_doctor`), but doesn't grant or
  restrict anything by itself. Note it looks up `users` via `find_by_id` (not `_scoped`),
  since `users` isn't organization-scoped in the `*_scoped` sense — the org match is checked
  by hand.
