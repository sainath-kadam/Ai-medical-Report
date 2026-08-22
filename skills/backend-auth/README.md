# backend-auth

Signup/login/Google-OAuth/refresh/logout/password-reset, plus the JWT + RBAC primitives
every other domain depends on. See CONTRACTS.md §2 (auth & tokens) and §3 (RBAC matrix).

## Key files

- `server/app/api/auth/routes.py` — thin routes: parse request, call `AuthService`, `ok(...)`.
  No auth required on signup/login/google/refresh/forgot-password/reset-password; auth
  required on logout/me/change-password.
- `server/app/services/auth_service.py` — all the actual logic: account creation
  (`provision_org_and_admin_user`), credential checks, Google ID-token verification, token
  issuance/rotation, password reset flow.
- `server/app/core/security.py` — password hashing (bcrypt), JWT access tokens, opaque
  refresh tokens, the `CurrentUser` model, `get_current_user`/`require_roles` dependencies,
  and signed-URL helpers for local file storage (unrelated to auth but lives here).

## Non-obvious things

- **Refresh tokens are opaque, not JWTs.** `generate_refresh_token()` is a random string;
  only its sha256 (`hash_refresh_token()`) is ever persisted, in `sessions`. Every
  `POST /auth/refresh` call rotates it — revokes the old hash, issues a new token — so a
  stolen-but-unused old refresh token stops working the instant the legitimate client
  refreshes.
- **`system_admin` has no `organization_id`.** It's a platform-wide role (see
  `CurrentUser.organization_id: str | None`), not a member of any tenant. Every login/logout/
  audit call in `auth_service.py` branches on `organization_id is not None` before writing an
  audit log row, because `audit_logs.organizationId` is NOT NULL — a system_admin login is
  deliberately not audited per-org (no per-org audit trail makes sense for it).
  `get_current_user`'s org-scoped guarantee therefore isn't "organization_id is always
  present," it's "every route that needs one enforces that itself" — system_admin simply
  can't reach organization-scoped routes.
  - `InvitableRole` (`org_admin`/`doctor`) is deliberately narrower than the full `Role`
  Literal (`org_admin`/`doctor`/`system_admin`) — used by `app/schemas/user.py` for invite/
  update payloads so an org_admin can never grant `system_admin` to someone in their own org
  (privilege escalation).
- **New-org bootstrap does three things atomically in application code** (no DB transaction
  spanning them, just sequential awaits): creates the org doc with `subscriptionStatus:
  "trial"` / `trialEndsAt: now + settings.trial_days`, creates the `org_admin` user, and
  calls `TemplateService.ensure_default_template` (idempotent) so every org always has at
  least one report template. Both `signup` and first-time `google_auth` share this via
  `provision_org_and_admin_user`.
- No account enumeration: `login` and `forgot_password` return the same generic response/
  error whether or not the email exists.
