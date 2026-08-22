# backend-users

Managing the user roster within one organization: list, invite, fetch, update (role/name/
active status), delete. See CONTRACTS.md §9 (route list) and §12 (cross-domain repository
signatures).

## Key files

- `server/app/api/users/routes.py` — thin routes: parse request, call `UserService`,
  `ok(...)`. Every route requires auth and is `org_admin`-only except `GET /{user_id}`.
- `server/app/services/user_service.py` — list/invite/get/update/delete logic, including the
  self-fetch carve-out and the "generate a temp password" invite flow.
- `server/app/repositories/user_repository.py` — persistence: `find_by_email`,
  `find_by_google_id`, `list_by_organization` (paginated, optional name/email search),
  `update`, `delete`.
- `server/app/schemas/user.py` — `UserInviteRequest` / `UserUpdateRequest` request bodies.

## Non-obvious things

- **`UserRepository` is NOT organization-scoped** in the `BaseRepository.*_scoped` sense —
  `users.id` is its own primary key, not nested under a parent org resource, so `update`/
  `delete` take a bare `user_id` and do *not* filter by `organizationId` themselves. Every
  caller (see `get_user`/`update_user`/`delete_user` in `user_service.py`) must fetch the doc
  first and compare `doc["organizationId"] != current_user.organization_id` — treating a
  mismatch as `404 Not Found` (never `403`, to avoid revealing another org's user exists) —
  before calling `update`/`delete`. If you add a new method here, don't assume org isolation
  is automatic like it is for org-scoped repositories.
- **`GET /users/{user_id}` is the one route with mixed RBAC**: the route dependency is a
  plain `get_current_user` (not `require_roles("org_admin")`) because a non-admin caller is
  allowed to fetch their own record. The org_admin-or-self check happens inside
  `UserService.get_user`, not the router — don't "simplify" the route by adding
  `require_roles` there, it would break self-fetch for doctors.
- **Invite doesn't send email — there's no SMTP configured in v1.** `invite_user` generates a
  temp password server-side (`generate_temp_password()`) and returns it once, directly in the
  201 response body (`public["temporaryPassword"]`), for the inviting org_admin to relay
  out-of-band. This is documented v1 behavior, not a TODO to silently "fix" by wiring email
  without updating the contract/frontend.
- A user can't delete their own account (`CANNOT_REMOVE_SELF`); role changes are audited
  (`PERMISSION_CHANGED`) only when the role actually changes.
