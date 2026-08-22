# backend-repositories

`server/app/repositories/` — the persistence layer every service goes through. Nothing
outside this folder (and `app/database/`) should build a SQLAlchemy `select`/`update`
statement directly against a table.

## Key files

- `base.py` — `BaseRepository`, the CRUD scaffolding every domain repository builds on:
  `insert`, `find_by_id`, `find_by_id_scoped`, `list_scoped`, `update_scoped`,
  `delete_scoped`. Also owns `_build_conditions`, the small closed translation of the
  Mongo-operator-shaped filter dicts services already build (`{"status": {"$in": [...]}}`,
  `{"$or": [...]}`, `{"field": {"$regex": ..., "$options": "i"}}`, `$gte`/`$lte`/`$ne`) into
  SQLAlchemy `WHERE` clauses.
- One file per table: `organization_repository.py`, `user_repository.py`,
  `patient_repository.py`, `study_repository.py`, `report_repository.py`,
  `template_repository.py`, `analysis_job_repository.py`, `audit_log_repository.py`,
  `notification_repository.py`, `session_repository.py`, `password_reset_repository.py`.

## The convention

- **Every id is a plain string**, never a DB-generated int/UUID type (see
  `backend-database`). Every repository method returns/accepts the same camelCase,
  `_id`-keyed dict shape the whole app speaks (CONTRACTS.md §1a) — never a raw ORM object.
  `_to_dict` / `_to_kwargs` are the *entire* translation layer, driven generically off each
  model's mapped columns via `app/database/casing.py`, so no per-entity mapping code exists
  anywhere. If you add a column to a model in `database/models.py`, every repository built
  on `BaseRepository` picks it up automatically — no repository changes needed.
- **Multi-tenant isolation is structural, not a per-route check**: `find_by_id_scoped` and
  `list_scoped` require `organization_id` as a real, non-optional argument — there is no
  shortcut method that queries a scoped table without it.
- **Not every table is actually organization-scoped.** `organizations` itself is the tenant
  boundary, not a tenant-scoped resource, so `OrganizationRepository` looks up/updates rows
  by their own `id` only (plain `update`, no `_scoped` variant). `users` is similar:
  `UserRepository` only reuses `BaseRepository.insert`/`find_by_id` and adds its own plain
  (non-scoped) `update`/`delete` — callers (e.g. `user_service.py`) are responsible for
  checking `organizationId` on the returned doc themselves before mutating it. Don't assume
  every repository has `*_scoped` methods; check the specific file.
- **Custom cross-domain methods must keep their exact name/signature** (CONTRACTS.md §12) —
  other modules import them directly. Examples: `StudyRepository.add_file(study_id,
  organization_id, file_dict)` and `set_last_findings(study_id, findings)` (deliberately NOT
  org-scoped — callers already loaded/validated the study earlier in the same flow via
  `find_by_id_scoped`); `UserRepository.find_by_email`/`find_by_google_id`;
  `OrganizationRepository.find_by_stripe_customer_id`.
- **`StudyRepository` overrides every read/write method** to attach the `files` list (a real
  child table, `StudyFile`) onto the returned study dict, so callers see the same shape as
  if `files` were still an embedded array — see `backend-database` for why it's a child
  table instead of JSON.
- Repositories stay thin persistence helpers and don't translate DB errors into HTTP-facing
  error shapes themselves — e.g. `PatientRepository` is literally just `BaseRepository`
  as-is; it's `PatientService`'s job to catch the `IntegrityError` from the
  `(organization_id, mrn)` unique constraint and turn it into `AppError.conflict`.
