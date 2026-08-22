# backend-platform

`server/app/api/platform/`, `server/app/services/platform_service.py`, and
`server/app/scripts/create_system_admin.py` — the `system_admin` role and how new
organizations get onboarded onto the platform (CONTRACTS.md §2b). This is the one domain
that operates *across* organizations instead of within one.

## Key files

- `api/platform/routes.py` — `POST /platform/organizations` and `POST
  /platform/system-admins`, both gated by `require_roles("system_admin")`. Every route in
  this file is system_admin-only.
- `services/platform_service.py` — `PlatformService`:
  - `create_organization(payload, actor_user_id)` — creates a new `Organization` AND its
    first `org_admin` user in one call, by reusing `AuthService.provision_org_and_admin_user`
    (the exact same org+admin-user+default-report-template provisioning `POST /auth/signup`
    uses). The new org starts a free trial just like self-signup. Logs
    `ORGANIZATION_CREATED_BY_ADMIN` against the new org's own id.
  - `invite_system_admin(payload)` — creates another platform-wide account (`organizationId:
    null`, `role: "system_admin"`). Not audit-logged — there's no organization to log it
    against.
  - Both return the generated `temporaryPassword` directly in the response body, once —
    same pattern `POST /users` uses to invite a doctor (no SMTP is configured anywhere in
    this app, so out-of-band relay by whoever ran the request is the only delivery
    mechanism).
- `scripts/create_system_admin.py` — one-time CLI bootstrap for the *very first*
  system_admin (`python -m app.scripts.create_system_admin --name ... --email ...`, run
  from `server/` with the venv active). Prompts for a password via `getpass` if `--password`
  isn't passed, specifically so it never sits in shell history. Once one system_admin
  exists, create further ones through `POST /platform/system-admins` instead of this script.

## Non-obvious things

- **`system_admin` is the one role with `organizationId = null`** (a real `null`, not a
  missing/empty string) — see `User.organization_id` in `app/database/models.py`, which is
  nullable *only* for this role. It logs in through the normal `POST /auth/login` like
  everyone else; the response's `organization` field is simply `null`. It sits entirely
  outside the org_admin/doctor RBAC matrix (CONTRACTS.md §3).
- **There is deliberately no self-service signup path to this role.** `POST /auth/signup`
  always creates a brand-new organization + `org_admin` — letting anyone grant themselves
  platform-wide access would be a security hole. The CLI script is the only way to create
  the first one; an org_admin can never promote a user to `system_admin` through the normal
  users domain either — `POST /users`/`PATCH /users/{id}` type `role` as `InvitableRole`
  (`org_admin`/`doctor` only), so attempting it is a 422 at the schema level, not just an
  RBAC check that could be misconfigured.
- **There is currently no route to list or manage existing organizations** — only to create
  new ones. This is a deliberate v1 scope limit per CONTRACTS.md §2b, not an oversight; don't
  assume a missing `GET /platform/organizations` is a bug to fix without checking with
  whoever's driving the roadmap.
