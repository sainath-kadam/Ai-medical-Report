# Medo AI — Backend Rebuild Contracts (source of truth)

This document is the single source of truth for the FastAPI rebuild of `server/` and the
corresponding updates to the existing `client/`. Every agent/human working on either side
MUST follow this exactly — it is what keeps the two independently-built halves compatible.

Context: `client/` already exists (React+TS+Vite) and is being extended, not rewritten.
`server/` is being fully rewritten from Node/Express/Mongoose to Python/FastAPI, backed
by PostgreSQL via SQLAlchemy 2.0 async + asyncpg.
The wire format (JSON over HTTP) below is what both sides must agree on.

## 1. Wire format conventions

- All JSON keys are **camelCase**. Backend Pydantic models use `snake_case` Python fields
  internally with `alias_generator` producing camelCase, `populate_by_name=True`, and
  responses are built with `by_alias=True`.
- Every entity's identifier field is `id` (a plain string, never a database-generated key
  — see §1a). Never emit `_id` in API responses (existing frontend used `_id` for some
  types — this is being standardized to `id` across the board as part of this rebuild).
- All timestamps are ISO-8601 strings (UTC), field names end in `At` (e.g. `createdAt`).
- Response envelope (spec section 40), for EVERY endpoint:
  - Success: `{"success": true, "data": <payload>}`  (payload may be `null`)
  - Error: `{"success": false, "error": {"code": "SNAKE_UPPER_CODE", "message": "human readable"}}`
  - Implemented once via `app/core/exceptions.py` (an `AppError` exception + a FastAPI
    exception handler) and `app/utils/response.py` (`ok(data, status_code=200)` helper).
    Individual routers never hand-build the envelope.
- Pagination (lists): query params `page` (default 1), `pageSize` (default 20, max 100),
  optional `search`, and entity-specific filters. Response `data` shape:
  `{"items": [...], "page": 1, "pageSize": 20, "total": 137, "totalPages": 7}`.
- Base path: **`/api/v1`**. Full router is mounted once in `app/main.py`.

### 1a. IMPORTANT — id/storage convention (read this before writing any repository)

Ids are **application-generated plain strings**, never left to the database to assign.
Every id and every foreign-key field (`_id`, `organizationId`, `patientId`, `studyId`,
`templateId`, `userId`, etc.) is a uuid4 hex string from `app/utils/ids.py::new_id()`,
set explicitly at insert time — never a Postgres serial/identity column, never
`gen_random_uuid()`. SQLAlchemy table classes live in `app/database/models.py` (one
class per table, snake_case columns), but routers/services never touch a table row
directly: `app/repositories/base.py::BaseRepository`'s `_to_dict`/`_to_kwargs` translate
every row to/from the same camelCase, `_id`-keyed plain dict shape the app has always
used (via `app/database/casing.py`'s `camel_to_snake`/`snake_to_camel`, which
special-case `_id`/`id` into each other), so a repository call site is unaware anything
but a dict is involved. The one remaining `_id` -> `id` rename for **API responses** is
handled by the single helper `app/utils/ids.py::to_public(doc)` / `to_public_list(docs)`.
Consequences every repository/service/router must follow:

- Repositories insert with an explicit `"_id": new_id()`; the database never generates
  the key. Query filters compare plain strings (`{"_id": some_id}`, `{"organizationId":
  org_id}}`) — the same Mongo-operator-shaped filter dicts (`$in`/`$or`/`$regex`/etc.)
  every service already builds, translated into SQL `WHERE` clauses by
  `BaseRepository._build_conditions`.
- Pydantic `schemas/*.py` classes are used to validate **request bodies only**. API
  **responses** are plain dicts — a repository/service dict run through `to_public()` —
  passed straight to `app/utils/response.py::ok(data)`. Do not build a response Pydantic
  model and call `.model_dump()`; it's unnecessary ceremony given the above.
- `app/database/models.py` is the only place that knows about SQLAlchemy — nothing
  outside `app/repositories/` imports a table class or holds a live ORM row.
  `schemas/` (request validation) + plain dicts (storage/response shape) still fill the
  role an `app/models/` directory of response classes would otherwise play.

## 2. Auth & tokens

- Passwords hashed with `bcrypt` (never stored plain). Field `password_hash`, never
  serialized to any response.
- **Access token**: JWT, 30 min expiry, payload `{sub: user_id, orgId, role, type: "access"}`.
- **Refresh token**: opaque random string (not a JWT), 30 day expiry, stored **hashed**
  (sha256) in the `sessions` table with `{userId, tokenHash, userAgent, createdAt,
  expiresAt, revokedAt}`. Enables real logout/revocation (spec section 5 requires this).
- Endpoints (`/api/v1/auth/...`):
  - `POST /signup` — body `{name, email, password, organizationName}` → creates
    Organization (role `org_admin` for the creator) + default ReportTemplate → returns
    `{accessToken, refreshToken, user, organization}`.
  - `POST /login` — `{email, password}` → same shape.
  - `POST /google` — `{idToken, organizationName?}` → verifies via Google's `google-auth`
    library against `GOOGLE_CLIENT_ID` → find-or-create user/org exactly like signup/login
    → same response shape. (Matches existing `GoogleButton.tsx` which already POSTs
    `{idToken, organizationName}` — no frontend change needed to this flow's shape.)
  - `POST /refresh` — `{refreshToken}` → validates hash+expiry+not-revoked in `sessions`,
    issues new access token (and rotates the refresh token: revoke old, issue new) →
    `{accessToken, refreshToken}`.
  - `POST /logout` — `{refreshToken}` → marks session revoked → `data: null`.
  - `GET /me` — requires auth → `{user, organization}`.
  - `POST /forgot-password` — `{email}` → always `{success:true}` (no email enumeration);
    creates a reset token record; in dev (no SMTP configured) logs the reset link instead
    of sending email (`notification_service` is pluggable — see §8).
  - `POST /reset-password` — `{token, newPassword}`.
  - `POST /change-password` — auth required — `{currentPassword, newPassword}`.
- `User.role` is one of `org_admin` | `doctor` | `system_admin` (spec §8 — no separate
  "owner" tier and no `technician` tier; the signup/first-Google-user creator gets
  `org_admin`). `system_admin` is platform-wide, not created via this flow — see §2b.

## 2a. Trial & billing (subscription gating) — new, not in the original spec

Signup is fully self-serve into a time- and volume-limited free trial. Out of the trial
there are two doors: a real Stripe subscription (below), or an access period a
`system_admin` grants by hand (§2c — e.g. paid by invoice). Neither: the org is read-only.

- On signup/first Google sign-in (`AuthService.provision_org_and_admin_user` — public,
  not underscore-prefixed, since §2b's platform domain reuses it too), the new
  organization is created with `subscriptionStatus: "trial"` and `trialEndsAt = now +
  TRIAL_DAYS` (env-configurable, default 3 days).
- While `subscriptionStatus` is `trial`, generating a new AI report is capped at
  `TRIAL_DAILY_REPORT_LIMIT` (env-configurable, default 100) per UTC calendar day.
- Once the trial window has passed (or a paid subscription lapses/cancels),
  `POST /analysis/studies/{id}/analyze` is blocked with **HTTP 402**
  (`AppError.payment_required`) until the organization pays — error code `TRIAL_EXPIRED`
  (trial over, no active subscription) or `TRIAL_DAILY_LIMIT_REACHED` (still trialing,
  daily cap hit; `ACCESS_EXPIRED` / `ORGANIZATION_SUSPENDED` per §2c). Enforced by
  `app/core/subscription.py::require_active_subscription` on the analyze route (and
  `POST /studies` when it also runs analysis). Every other write route is covered by the
  broader read-only gate of §2c, which uses the same evaluator and the same codes.
- Payment is via Stripe Checkout, new route domain `billing` (§9): `POST
  /billing/checkout` (`org_admin`/`doctor`, creates a Stripe Checkout session for the
  org, returns `{checkoutUrl}`), `GET /billing/status` (any authenticated user, returns
  `{subscriptionStatus, trialEndsAt, accessEndsAt, isSuspended, access, billingConfigured}`
  — `access` per §2c), `POST /billing/webhook` (no
  auth — called by Stripe's own servers, gated only by the Stripe-signed payload verified
  via `STRIPE_WEBHOOK_SECRET`, never a bearer token). The webhook handles
  `checkout.session.completed` (sets `subscriptionStatus: "active"`, stores
  `stripeCustomerId`/`stripeSubscriptionId`) and `customer.subscription.updated` /
  `customer.subscription.deleted` (sets `active`/`expired` from the Stripe subscription
  status).
- `billingConfigured` (in `GET /billing/status`) is `false` whenever `STRIPE_SECRET_KEY`/
  `STRIPE_PRICE_ID` aren't set, so the frontend can hide/disable checkout in an
  environment where billing isn't set up (e.g. local dev) instead of surfacing the 400
  `BILLING_NOT_CONFIGURED` that `/billing/checkout` would otherwise raise.

## 2b. System admin & platform (onboarding new organizations) — new, not in the original spec

`system_admin` is the one role with no `organizationId` (`null`, not a missing/empty
string) — a platform-wide account, not a member of any single tenant. There is no
self-service signup for it (that would let anyone grant themselves platform-wide access);
the first one is created by a one-time CLI script
(`python -m app.scripts.create_system_admin --name ... --email ...`, prompts for a
password), after which more can be invited via the routes below. It logs in through the
normal `POST /auth/login` — the response's `organization` is `null`.

Route domain `platform` (`system_admin`-only, enforced by `require_roles("system_admin")`):
- `POST /platform/organizations` — `{organizationName, adminName, adminEmail}` → creates a
  new Organization AND its first `org_admin` user in one call (reuses
  `AuthService.provision_org_and_admin_user`, the same org+admin+default-template
  provisioning self-signup uses) → `{organization, adminUser, temporaryPassword}`. The new
  org starts a free trial exactly like self-signup (§2a). No SMTP is configured, so the
  temporary password is returned directly, once, for the system_admin to relay
  out-of-band — same pattern as `POST /users` (§9) inviting a doctor.
- `POST /platform/system-admins` — `{name, email}` → creates another platform-wide
  account → `{...user, temporaryPassword}`.

An org_admin can **never** grant `system_admin` through the normal users domain — `POST
/users` and `PATCH /users/{id}` type their `role` field as `InvitableRole`
(`org_admin`/`doctor` only, a narrower type than the full `Role`), so attempting to invite
or promote someone to `system_admin` there is a 422, not just an RBAC check that could be
misconfigured.

No org-scoped audit trail applies to a system_admin's own actions (login/logout, inviting
another system_admin) — there's no organization to log them against, and building a
separate platform-level audit log is a reasonable future addition, not done here.
Creating an organization IS logged (`ORGANIZATION_CREATED_BY_ADMIN`), against the new
org's own id, since one now exists.

Listing and managing existing organizations (access periods, suspension) is §2c.

## 2c. Organization access management & read-only mode — new, not in the original spec

An organization is **writable** when, checked in this order by
`app/core/subscription.py::evaluate_access` (the single source of truth — every response
that carries an organization attaches its result as `access: {writable, reason, source,
endsAt}`):

1. it is not `isSuspended` (a suspended org is never writable, whatever else is true);
2. `subscriptionStatus == "active"` (Stripe) → `source: "subscription"`, no end date;
3. `accessEndsAt` is in the future (a period a `system_admin` granted by hand) → `"manual"`;
4. `subscriptionStatus == "trial"` and `trialEndsAt` is in the future → `"trial"`.

Otherwise `writable: false`, with `reason` = `ORGANIZATION_SUSPENDED` | `ACCESS_EXPIRED`
(a manual period existed and passed) | `TRIAL_EXPIRED`.

**Read-only mode.** While not writable, every `POST`/`PATCH`/`PUT`/`DELETE` under `users`,
`organizations`, `patients`, `studies`, `uploads`, `intake`, `analysis`, `reports`,
`templates` returns **402** with the `reason` as its error code, from one router-level
dependency (`require_writable_organization`, attached in `app/api/router.py`). `GET`s,
`auth/*` (login keeps working), `billing/*` (paying is the way back in), `dashboard`,
`audit-logs`, `notifications` and `platform` are not gated. The frontend explains the state
with `ReadOnlyBanner` (from `organization.access`) and otherwise relies on those 402s.

**Platform routes** (`system_admin` only, alongside §2b's):
- `GET /platform/organizations?page&pageSize&search` → paginated organizations, each with
  `access`, `userCount`, `reportCount` and the platform-only `accessNote`.
- `GET /platform/organizations/{id}` → `{organization (same shape), users[]}` (no hashes).
- `PATCH /platform/organizations/{id}/access` — partial body `{accessEndsAt?: datetime|null,
  isSuspended?: bool, accessNote?: string|null, plan?: free|pro|enterprise}` →
  `{organization}`. Audit-logged against that organization as `ORGANIZATION_ACCESS_UPDATED`
  (metadata: field names + the new access values, never the note), so the org's own admins
  see in their audit trail that the platform changed their access and when.
- `GET /platform/system-admins` → every platform-wide account.

`accessNote` is returned only by `platform/*` routes; `/auth/me`, `/organizations/me` and
the login/signup payloads strip it (`subscription.with_access`).

## 3. RBAC matrix (spec §8), enforced centrally in `app/core/security.py`

`system_admin` sits outside this matrix entirely — see §2b/§2c for its route domain (create
organizations, list/inspect them, grant access periods, suspend). The matrix below also
assumes the organization is writable (§2c): in read-only mode every write row is refused.
For every other role, the matrix collapses to which one of `org_admin`/`doctor` (or both)
an action requires:

| Action | Who |
|---|---|
| Manage org settings/branding/templates | org_admin only |
| Invite/manage/remove users | org_admin only |
| View patients/studies/reports | org_admin/doctor |
| Create patients | org_admin/doctor |
| Create studies / upload files | org_admin/doctor |
| Run AI analysis | org_admin/doctor |
| Review/edit/finalize reports, request AI changes | org_admin/doctor |
| Download reports | org_admin/doctor |
| View audit logs | org_admin only |

Implemented as FastAPI dependencies in `app/core/security.py`:
`get_current_user`, `require_roles(*roles)`, and every organization-scoped repository
method takes `organization_id` as a mandatory filter — there is no code path that queries
a table without it (this is the multi-tenant isolation guarantee, spec §7).

## 4. Tables & entity shapes

All tables have `organizationId` (except `users`/`organizations` themselves, and
`sessions`/`audit_logs` which reference `userId`). Indexes noted per table.

**organizations**: `id, name, logoUrl, address, contactEmail, contactPhone, website,
plan(free|pro|enterprise), highAccuracyMode(bool), reportHeader, reportFooter,
primaryColor, createdBy, subscriptionStatus(trial|active|expired), trialEndsAt,
stripeCustomerId?, stripeSubscriptionId?, accessEndsAt?, isSuspended, accessNote?,
createdAt, updatedAt` (the four subscription/trial fields are new — see §2a; the three
platform-managed access fields are §2c)

**users**: `id, name, email(unique,index), passwordHash?, googleId?, avatarUrl,
role(org_admin|doctor|system_admin), organizationId(index)?, isActive, emailVerifiedAt?,
createdAt, updatedAt` (`organizationId` is `null` only for `role: system_admin` — see §2b;
every other role always has a real one)

**patients** (NEW entity — did not exist in the old Node app): `id, organizationId(index),
mrn (medical record number, unique per org; optional on create — the server assigns a
sequential `MRN-000123` when omitted), name, dateOfBirth, sex(male|female|other|
unspecified), contactPhone?, contactEmail?, createdBy, createdAt, updatedAt`

**studies** (renamed from old `Scan`, now references a Patient instead of an embedded
patient blob): `id, organizationId(index), patientId(index), modality(x_ray|ct|mri|
ultrasound|other), bodyPart, clinicalHistory?, studyDate, status(uploaded|processing|
completed|failed), assignedDoctorId?, files: [{id, fileName, storageKey, mimeType,
sizeBytes, uploadedBy, uploadedAt}] (wire shape unchanged; backed by the `study_files`
table below, not a JSON column), templateId?, lastFindings?: {observations:[string],
rawSummary, analyzable, unanalyzableReason?} (the most recent imaging-analysis result —
read by the change-request flow so a formatting-only revision never re-runs analysis),
studyInstanceUid?, seriesInstanceUid?, sopInstanceUid?, createdBy, createdAt, updatedAt`
(the DICOM UID fields are nullable placeholders per spec §15 — not populated in v1)

**study_files** (NEW child table — `studies.files` was an embedded array before the
Postgres migration; split into its own table because `GET /uploads/file/{key}` must look
up a file by its `storageKey` alone, without knowing the parent study id first):
`id, studyId(index), fileName, storageKey(unique,index), mimeType, sizeBytes, uploadedBy,
uploadedAt`. `StudyRepository` re-attaches these rows onto every study dict it returns as
a `files` list, so callers and API responses see exactly the array shape documented
above — this table is an internal storage detail, not a wire-format change.

**analysis_jobs**: `id, organizationId(index), studyId(index), status(queued|
preprocessing|analyzing|generating_report|ready_for_review|completed|failed),
provider, imagingModel?, reportModel?, inputHash, error?, startedAt?, completedAt?,
createdAt`

**report_templates**: `id, organizationId(index), name, isDefault, header{
organizationName, logoUrl?, tagline?}, doctorInfo{showDoctorName, showSignatureLine,
showRegistrationNo}, sections:[{key,title,order,enabled,guidance?}], footer{text,
disclaimer}, accentColor, createdBy, createdAt, updatedAt`
(kept ~identical to old `ReportTemplate.model.ts` — it already matched spec §26 well)

**reports**: `id, organizationId(index), studyId(index), templateId, versions:[{
versionNumber, content{summary,sections:[{key,title,content}],impression,
recommendations}, author("ai"|userId), generatedAt, changeRequestNote?, reason?,
aiModelUsed?}], currentVersion, status(ai_generated|pending_review|draft|
doctor_modified|finalized|amended), finalizedBy?, finalizedAt?, createdAt, updatedAt`

**audit_logs**: `id, organizationId(index), userId, action, resourceType, resourceId?,
metadata (small, non-PHI dict), ip?, userAgent?, createdAt(index)`
Never store report/finding text or file contents in `metadata` (spec §30/§31).

**notifications**: `id, organizationId(index), userId(index), type, title, body, link?,
readAt?, createdAt`

**sessions**: see §2.

## 5. AI architecture (spec §16–18, §24)

`app/ai/base.py` defines two abstract interfaces (kept separate on purpose, per spec §17):

```python
class BaseMedicalImagingProvider(ABC):
    async def analyze(self, image_bytes: bytes | None, mime_type: str | None,
                       context: StudyContext) -> StructuredFindings: ...

class BaseReportGenerationProvider(ABC):
    async def generate(self, findings: StructuredFindings, sections: list[TemplateSection],
                        context: StudyContext, high_accuracy: bool) -> GeneratedContent: ...
    async def revise(self, findings: StructuredFindings, sections, context, previous: GeneratedContent,
                      instruction: str, target_sections: list[str], high_accuracy: bool) -> GeneratedContent: ...
    async def classify_change_request(self, instruction: str, sections) -> ChangeRequestClassification: ...
    async def summarize_findings(self, organization_name: str, context: StudyContext,
                                  findings: StructuredFindings, high_accuracy_mode: bool = False) -> str: ...
```

**Pre-report summary step (new).** `summarize_findings()` distills `findings` into a
short summary, run concurrently with `generate()` (`asyncio.gather`) — its result always
wins for `GeneratedContent.summary`. Separate method so it can use a different model:
Gemini splits `GEMINI_IMAGING_MODEL`/`GEMINI_SUMMARY_MODEL` (both default `gemini-3.8-flash`)
from `GEMINI_MODEL` (default `gemini-3.6-flash`, used by everything else), and while the
organization's `highAccuracyMode` is on runs image interpretation and this summary on
`GEMINI_HIGH_ACCURACY_MODEL` (default `gemini-3.1-pro-preview`, paid plan; falls back to
the standard model on a free key) — report text is never escalated. `model_used` on both
`StructuredFindings` and `GeneratedContent` names the model that actually answered
(`analysis_jobs.imagingModel` / `reportModel`), fallback included. Anthropic runs the
summary on the `fast` tier regardless. Not used by `apply_change_request`/`revise()` (a change-request
already carries the previous summary forward).

**Gemini calls must use the SDK's async surface** (`client.aio.models.generate_content`,
awaited) — the sync client blocks this single-process server's whole event loop per call.

`app/ai/providers/anthropic_provider.py` implements BOTH interfaces using the `anthropic`
Python SDK, carrying over the existing tiered-model strategy from the old
`ai.service.ts` (fast=haiku-4-5 / default=sonnet-5 / highAccuracy=opus-5 / max=fable-5),
structured JSON output, prompt caching on the system prompt, and the same safety framing
language. `app/ai/providers/mock_provider.py` implements both with deterministic
placeholder content when no `AI_API_KEY` is set (never breaks local dev).

`get_imaging_provider()` / `get_report_provider()` factories in `app/ai/base.py` read
`AI_PROVIDER` env var — this is the seam for dropping in a real specialized radiology
model later without touching services/routers.

Change-request flow (spec §24): `classify_change_request` runs on the **fast** tier and
returns `{targetSections: [...], formattingOnly: bool}`. If `formattingOnly`, `revise()`
must NOT re-run imaging analysis — it rewrites only using existing findings/content.

## 6. Storage (spec §14)

`app/storage/base.py`: `class StorageProvider(ABC): upload(key, data, content_type);
download(key) -> bytes; delete(key); generate_signed_url(key, expires_in=300) -> str;
verify_access(key, token) -> bool`. `local.py` (dev default — writes under
`server/uploads/`, signed URL = a short-lived HMAC token verified by a dedicated
`/api/v1/uploads/file/{key}?token=` route, never a static/public mount). `s3.py`
(boto3, presigned URLs, used for any `STORAGE_PROVIDER=s3|s3_compatible`). Selected via
`STORAGE_PROVIDER` env var in `app/storage/__init__.py::get_storage()`.

## 7. Background jobs — removed; runs synchronously in-request instead (spec §19–20, §43
originally required async; deliberately deviated from, see below)

There is no ARQ/Redis worker process. It was removed to drop an infrastructure
dependency — a deliberate, **temporary** simplification, not a permanent architectural
decision; proper async background-job processing may be reintroduced later.

`POST /api/v1/studies/{id}/analyze` and `POST /api/v1/reports/{id}/change-request` still
create the same `analysis_jobs` doc (`status="queued"`) they always did, but now call
`AnalysisService.run_analysis` / `ReportService.apply_change_request` directly and await
them in-request, returning `200` (not `202`) with `{jobId}` only once the AI work has
actually finished. Both already mark the job/study `failed` and log internally on error,
so the route swallows the exception rather than raising a 500 — the response is always
`200 {jobId}`, whether the AI call succeeded or failed.

Frontend polling is unchanged and required no frontend code changes: `GET
/api/v1/analysis/jobs/{jobId}` (§21 statuses) still works exactly as documented — it just
resolves on the very first poll instead of watching real progress, since the job is
already in a terminal state (`completed`/`failed`) by the time the initiating POST
returns.

Worth flagging for production: with a real (non-mock) AI provider, a slow AI call now
blocks the HTTP request/response cycle for the duration of the analysis — see
`README.md`'s "load-bearing facts" section for this trade-off.

## 8. Notifications / audit / PDF

- `notification_service.create(...)` inserts into `notifications`; email/SMS are a no-op
  logger call for now (`app/services/notification_service.py` has one clearly-marked seam).
- `audit_service.log(user, action, resource_type, resource_id, metadata={})` is called
  from every service method that mutates state (list of actions = spec §30 list).
- PDF via `reportlab` in `app/services/pdf_service.py`, mirroring the old `pdf.service.ts`
  layout (header/accent color/patient+study meta/sections in template order/impression/
  recommendations/signature block/footer disclaimer). Rendered synchronously (fast, text
  report — no need for a job) and streamed as `application/pdf`.

## 9. Full route list (all under `/api/v1`, all require auth except signup/login/google/
forgot-password/reset-password/refresh/billing webhook)

```
auth:        POST /signup /login /google /refresh /logout /change-password
             POST /forgot-password /reset-password   GET /me
users:       GET /  POST /  GET /{id}  PATCH /{id}  DELETE /{id}          [org_admin]
organizations: GET /me   PATCH /me                                       [org_admin for PATCH]
patients:    GET /  POST /  GET /{id}  PATCH /{id}  DELETE /{id}  GET /{id}/studies
studies:     GET /  POST /  GET /{id}  PATCH /{id}  DELETE /{id}
             POST /intake (multipart) — one-request new-study flow, returns {study,report,analysisJobId}
uploads:     POST /studies/{id}/files (multipart)   GET /file/{key}?token=
intake:      POST /parse [org_admin/doctor] — chat-intake field extraction, no persistence
analysis:    POST /studies/{id}/analyze   GET /jobs/{jobId}   GET /studies/{id}/jobs
reports:     GET /  GET /{id}  GET /{id}/versions  PATCH /{id}
             POST /{id}/change-request  POST /{id}/regenerate
             POST /{id}/finalize  POST /{id}/amend  GET /{id}/pdf
templates:   GET /  POST /  GET /{id}  PATCH /{id}  DELETE /{id}
dashboard:   GET /stats   GET /recent-activity
audit-logs:  GET /                                                       [org_admin]
notifications: GET /   PATCH /{id}/read   PATCH /read-all
billing:     POST /checkout [org_admin/doctor]   GET /status
             POST /webhook [no auth — Stripe-signed payload only]
```

## 11. Already-built shared infrastructure (do not recreate — import it)

These files already exist and are the foundation every domain module builds on. Read the
actual file for exact signatures before using it; this is just an index:

- `app/core/config.py::settings` — all env-driven config.
- `app/core/exceptions.py::AppError` — raise this for every expected error; never build
  an error response by hand.
- `app/utils/response.py::ok(data, status_code=200)` — every success response.
- `app/utils/ids.py::new_id()`, `to_public(doc)`, `to_public_list(docs)`.
- `app/schemas/common.py::CamelModel`, `PaginationParams`.
- `app/api/deps.py::get_db`, `pagination_params`.
- `app/core/security.py::get_current_user` (FastAPI dependency, returns `CurrentUser`
  with `.id/.organization_id/.role/.email/.name`), `require_roles(*roles)`,
  `require_admin_or_doctor()`, `hash_password`, `verify_password`,
  `create_access_token`, `decode_access_token`, `generate_refresh_token`,
  `hash_refresh_token`, `refresh_token_expiry`.
- `app/core/subscription.py::require_active_subscription` (FastAPI dependency; add as an
  extra `Depends()` on any route that creates a new AI report to enforce the trial/
  billing gate — §2a. Currently used by the analyze route only.)
- `app/repositories/base.py::BaseRepository` — subclass it, set `model` (the SQLAlchemy
  table class from `app/database/models.py`), get
  `insert/find_by_id/find_by_id_scoped/list_scoped/update_scoped/delete_scoped` for free
  (translated to/from plain camelCase dicts per §1a). Note
  `users`/`organizations`/`sessions`/`password_reset_tokens` are NOT
  organization-scoped tables themselves — their repositories subclass
  `BaseRepository` for `insert`/`find_by_id`/`.session` only and add custom methods
  (e.g. `find_by_email`), never the `*_scoped` helpers.
- `app/ai/base.py::get_imaging_provider()`, `get_report_provider()`, plus the dataclasses
  `StudyContext`, `StructuredFindings`, `GeneratedContent`, `ReportSectionContent`,
  `ChangeRequestClassification`, `TemplateSectionSpec`, `resolve_generation_tier`.
- `app/storage/__init__.py::get_storage()` → `StorageProvider` with
  `upload/download/delete/generate_signed_url`.
- `app/services/pdf_service.py::build_report_pdf(content, patient, study, template,
  doctor_name, report_status, report_id, version_number) -> bytes`.
- `app/api/router.py` — already wires up every domain router by import; you do NOT need
  to (and should not) edit this file. Just create `app/api/<domain>/routes.py` exporting
  `router = APIRouter(prefix="/<domain>", tags=["<domain>"])` with the exact routes from
  §9, and the matching `__init__.py`.

## 12. Cross-domain repository/service methods other modules will call

Implement these EXACT names/signatures (async) so other domains' code — written in
parallel — imports successfully:

- `app.repositories.organization_repository.OrganizationRepository(db)`:
  `insert(doc)`, `find_by_id(id) -> dict|None`, `update(id, update: dict) -> dict|None`.
- `app.repositories.user_repository.UserRepository(db)`:
  `insert(doc)`, `find_by_id(id)`, `find_by_email(email)`, `find_by_google_id(gid)`,
  `list_by_organization(organization_id, skip, limit) -> tuple[list, int]`.
- `app.services.template_service.TemplateService(db)`:
  `ensure_default_template(organization_id, organization_name, created_by) -> dict`
  (idempotent — returns the existing default if one exists).
  `app.repositories.template_repository.TemplateRepository(db)`: standard
  `BaseRepository` (table `report_templates`) plus `get_default(organization_id) ->
  dict|None`.
- `app.repositories.patient_repository.PatientRepository(db)`: standard `BaseRepository`
  (table `patients`).
- `app.repositories.study_repository.StudyRepository(db)`: standard `BaseRepository`
  (table `studies`) plus `add_file(study_id, organization_id, file_dict) -> dict|None`,
  `set_last_findings(study_id, findings: dict) -> None`, and
  `find_file_by_storage_key(storage_key) -> dict|None` (looks up a `study_files` row by
  its unique `storageKey` alone — used by the public signed-URL download route in
  `app/api/uploads/routes.py`, which doesn't know the parent study id).
- `app.repositories.report_repository.ReportRepository(db)`: standard `BaseRepository`
  (table `reports`) plus `append_version(report_id, organization_id, version: dict,
  new_status: str) -> dict|None`.
- `app.repositories.analysis_job_repository.AnalysisJobRepository(db)`: standard
  `BaseRepository` (table `analysis_jobs`).
- `app.services.audit_service.AuditService(db)`:
  `async def log(self, *, organization_id, user_id, action, resource_type,
  resource_id=None, metadata=None, ip=None, user_agent=None) -> None`. Call this from
  every service method that mutates state (spec §30's action list). Never put clinical
  text into `metadata`.
- `app.services.notification_service.NotificationService(db)`:
  `async def create(self, *, organization_id, user_id, type, title, body, link=None) ->
  dict`. Email/SMS sending is a single clearly-marked `logger.info(...)` no-op seam.
- `app.repositories.session_repository.SessionRepository(db)`: standard
  `BaseRepository` (table `sessions`, NOT org-scoped — scoped by `userId`) plus
  `create_session(user_id, token_hash, expires_at, user_agent) -> dict`,
  `find_valid(token_hash) -> dict|None`, `revoke(token_hash) -> None`.
- `app.services.analysis_service.AnalysisService(db)`:
  `async def run_analysis(self, study_id, organization_id) -> dict` (the report doc) —
  loads study+patient+template, downloads the file via `get_storage()`, calls
  `get_imaging_provider().analyze(...)`, stores the result on the study via
  `set_last_findings`, calls `get_report_provider().generate(...)`, creates the report
  (version 1, status `ai_generated`), updates study status, creates a notification, audit
  logs `AI_ANALYSIS_COMPLETED`. This is the function `POST /analysis/studies/{id}/analyze`
  calls directly and awaits in-request — see §7 (there is no longer a worker to call it).
- `app.services.report_service.ReportChangeService(db)` (or a method on the main
  `report_service.py` — implementer's choice, just keep the name importable as
  `apply_change_request`): `async def apply_change_request(self, report_id,
  organization_id, instruction, actor_user_id) -> dict` — classify via
  `get_report_provider().classify_change_request(...)`; if NOT `formatting_only`, re-run
  `get_imaging_provider().analyze(...)` and update `study.lastFindings`; else reuse
  `study.lastFindings` as-is. Then `get_report_provider().revise(...)`, append a new
  version (status `pending_review`), audit log `REPORT_REGENERATED`.

## 10. Frontend alignment work required (tracked separately, see TodoWrite)

- Rename `Scan` → `Study` throughout `client/src` (types, api client, pages, routes,
  nav) and introduce the `Patient` entity end-to-end (new pages + api + types) since it
  did not exist before.
- `types/index.ts`: switch every `_id` to `id`; add `Patient`, `Study`, `AnalysisJob`,
  `AuditLog`, `Notification` types; update `Report`/`ReportVersion`/`User` fields to
  match §4 exactly (role enum, version `author` instead of `generatedBy`, report status
  enum expanded to 6 values).
  Env-driven config: `VITE_API_URL` now defaults to `http://localhost:8000/api/v1`.
- `api/axiosInstance.ts`: store `medscan_access_token` + `medscan_refresh_token`; on 401,
  attempt one silent refresh via `/auth/refresh` before redirecting to `/login`.
- New pages: Patients (list/detail/create/edit), Users (org_admin), Audit Logs
  (org_admin), a generic Settings shell. Studies list/detail replace Upload-only flow
  (a Study can now have multiple files/patient history).
- Nav items gain Patients, Studies, Users, Audit Logs entries per spec §10.
