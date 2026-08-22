# backend-dashboard

Read-only rollup endpoints for the landing dashboard: headline counters plus small
"recent studies"/"recent reports"/"recent activity" widgets. CONTRACTS.md §9.

## Key files

- `server/app/api/dashboard/routes.py` — `GET /dashboard/stats`, `GET /dashboard/recent-
  activity` (`limit` query param, 1-50, default 10). Both just call `DashboardService` and
  `ok(...)` the result.
- `server/app/services/dashboard_service.py` — `DashboardService.get_stats` and
  `get_recent_activity`, the only logic in this module.

## Non-obvious things

- **No dedicated repository class.** Per the build note at the top of
  `dashboard_service.py`, this domain just runs `count()`/`select()` queries straight
  against `app.database.models` (`Study`, `Report`, `AnalysisJob`, `AuditLog`) instead of
  going through a `BaseRepository` subclass — there's nothing here beyond simple rollups, so
  don't add a `dashboard_repository.py` out of habit; follow the existing pattern.
- **Every query filters by `organization_id == current_user.organization_id`** — there is no
  route parameter for organization, so isolation is automatic as long as you keep using
  `current_user.organization_id` and never accept one from the client.
- **Any authenticated role can call these routes** — the RBAC matrix (CONTRACTS.md §3)
  doesn't restrict the dashboard itself, since it only surfaces counts and lean summaries of
  data the org already has. Don't add `require_roles` here without a reason; it would be a
  behavior change, not a fix.
- **`get_recent_activity` reads directly from `audit_logs`** and returns rows close to
  verbatim (ids, enums, small metadata dict). That's safe only because `AuditService.log`
  already guarantees `audit_logs.metadata` never contains PHI/report text (spec §31) — if
  that invariant ever changes, this endpoint would need to start filtering fields itself.
