# backend-patients

CRUD for the `patients` entity plus its nested `GET /{id}/studies` listing. Patients are a
NEW entity (didn't exist in the old Node app) — see CONTRACTS.md §4 for the table shape and
§3 for RBAC (`org_admin`/`doctor`, uniformly across every route here; there's no
reduced-permission role left to carve out now that `technician` is gone).

## Key files

- `server/app/api/patients/routes.py` — thin routes: list/create/get/update/delete, plus
  `GET /{patient_id}/studies`. Every route requires `require_admin_or_doctor()`.
- `server/app/services/patient_service.py` — all the logic. `list_patients` supports a
  `search` param matched against `name`/`mrn`. `get_patient_studies` delegates straight to
  `StudyRepository.list_scoped` filtered by `patientId` rather than duplicating any
  study-listing logic.
- `server/app/repositories/patient_repository.py` — a bare `BaseRepository` subclass, no
  extra methods (CONTRACTS.md §12 spells this out verbatim: "standard `BaseRepository`
  (table `patients`)").
- `server/app/schemas/patient.py` — `PatientCreateRequest` (all fields required except
  `contactPhone`/`contactEmail`) and `PatientUpdateRequest` (everything optional, PATCH
  semantics — only supplied fields are applied).

## Non-obvious things

- **MRN uniqueness is enforced at the database level, not pre-checked.** `(organizationId,
  mrn)` has a unique constraint (`app/database/models.py::Patient`). `create_patient`/
  `update_patient` just attempt the write and catch `sqlalchemy.exc.IntegrityError`,
  translating it to `AppError.conflict("PATIENT_MRN_TAKEN")` — deliberately avoiding a
  check-then-insert race. If you add a new field with its own uniqueness rule, follow this
  same pattern (constraint + catch) rather than a separate existence query.
- **On an `IntegrityError`, the service explicitly calls `await self.db.rollback()`** before
  raising `AppError.conflict` — needed so the session isn't left in a failed-transaction
  state for whatever runs next in the same request/test.
- The service methods take `CurrentUser` and only ever read `current_user.organization_id`
  off it — a client can never supply its own `organization_id`, it's always derived from the
  authenticated caller. Every repository call is one of the `*_scoped` methods, so
  cross-tenant access is structurally impossible, not something re-checked per route.
