# backend-audit-logs

The audit trail: every state-mutating action across the codebase gets one row here, and
`org_admin`s can list/filter it. CONTRACTS.md §4, §8, §11, §12; spec §30/§31.

## Key files

- `server/app/services/audit_service.py` — `AuditService.log(...)`, the ONE way any row
  ever lands in `audit_logs`, plus `list_logs` (the backing query for the route below).
- `server/app/repositories/audit_log_repository.py` — plain `BaseRepository` subclass for
  the `audit_logs` table; exists mainly so `list_logs` can reuse
  `BaseRepository.list_scoped` unchanged.
- `server/app/api/audit_logs/routes.py` — `GET /audit-logs`, `org_admin` only. Supports
  optional filters (`action`, `userId`, `resourceType`, `dateFrom`/`dateTo`) and standard
  pagination, sorted newest-first.

## Non-obvious things

- **`AuditService.log` has a fixed, keyword-only signature** (`organization_id`, `user_id`,
  `action`, `resource_type`, `resource_id`, `metadata`, `ip`, `user_agent`) specifically so
  every other domain's service can call it after a successful mutation without importing
  anything else about this module. If you change that signature, every call site across the
  codebase (auth, patients, studies, uploads, analysis, reports, templates, users,
  organizations, billing) breaks.
- **`metadata` must stay a small, non-PHI dict — ids, enums, and counts only.** Never put
  report/finding text, patient names, or file contents into it (spec §31). This module
  doesn't enforce that at the type level; it's a convention every caller has to honor.
- **`audit_logs` has no `updatedAt` column**, unlike most tables in this codebase. `insert()`
  from `BaseRepository` only stamps `updatedAt` when the table actually has that column, so
  `AuditService.log` can call it directly without special-casing — don't add an `updatedAt`
  field here without also adding the column, or without checking why it was deliberately
  left off (audit rows are meant to be immutable, write-once records).
- Writes always go through the service (never construct `AuditLogRepository` directly from
  another domain) — the repository itself has no create-time validation.
