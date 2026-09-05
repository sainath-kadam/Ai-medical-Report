# Medo AI

A multi-tenant medical imaging AI reporting platform: doctors and clinical staff upload
medical images (X-ray/CT/MRI/ultrasound), get an AI-drafted preliminary structured report,
and review/edit/finalize it before it's treated as a real report.

> **AI-generated content is always preliminary decision-support.** It requires review and
> approval by a qualified medical professional before being treated as a final report —
> the application enforces this in its data model (report status, immutable finalized
> versions, mutating endpoints gated on status). The report document itself (in-app and
> its PDF export) renders identically regardless of status, by request — draft/finalized
> status is only ever shown in the surrounding app UI (`ReportViewer`'s toolbar), never in
> the document, and a PDF downloaded before finalization carries no indication of that once
> it leaves the app. Nothing here is a diagnostic device or a substitute for clinical
> judgment.

📄 Exact wire contract (every route, entity shape, RBAC matrix): **`CONTRACTS.md`**.
🧩 Working on one specific module? Check **`skills/<name>/README.md`** first — see
`skills/README.md` for the full catalog. This file is the big-picture map; those are
the fast path once you know where you're going.

## Contents

- [Stack](#stack)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Deploying](#deploying)
- [How the system works, end to end](#how-the-system-works-end-to-end)
- [Backend layout](#backend-layout-serverapp)
- [Frontend layout](#frontend-layout-clientsrc)
- [Load-bearing facts](#multi-tenancy-ai-and-billing--the-load-bearing-facts)
- [What to add next, and why](#what-to-add-next-and-why)

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Vite + React Router, plain CSS per component. No Next.js, no Tailwind. |
| Backend | Python + FastAPI + SQLAlchemy 2.0 (async) + asyncpg, Pydantic, JWT + Google OAuth. |
| Database | PostgreSQL. |
| Storage | Pluggable — local disk for dev; Cloudinary, Firebase, or S3/S3-compatible for production, optionally chained primary → fallback. |
| AI | Pluggable two-layer abstraction (imaging analysis + report-generation LLM). Three providers — **Gemini** (default), Anthropic, and a zero-cost mock — selected via `AI_PROVIDER`. Gemini runs four independently configurable models: `GEMINI_IMAGING_MODEL` (image interpretation, default `gemini-3.8-flash`), `GEMINI_SUMMARY_MODEL` (the pre-report clinical-summary step, also `gemini-3.8-flash` by default), `GEMINI_MODEL` (the rest of the report's text, default `gemini-3.6-flash`), and `GEMINI_HIGH_ACCURACY_MODEL` (default `gemini-3.1-pro-preview`; replaces the first two while an organization's High-Accuracy Mode is on — needs a paid Gemini plan, falls back to the standard model on a free key). All real Gemini calls go through the SDK's async surface so one slow call doesn't stall the whole server. |
| Billing | Stripe Checkout + webhooks. Every signup starts a free trial, then needs an active subscription to keep generating AI reports. |

## Repository layout

```
medscan-ai/
├── client/          React frontend      (client/src/App.tsx, routes/AppRoutes.tsx)
├── server/          FastAPI backend     (server/app/main.py)
├── skills/          one README.md + skill.json per module — the fast path for AI/humans
├── CONTRACTS.md     the frontend<->backend wire contract (source of truth)
└── docker-compose.yml
```

## Quick start

```bash
cp server/.env.example server/.env   # set JWT_SECRET and SIGNED_URL_SECRET at minimum
cp client/.env.example client/.env
docker compose up --build
```

| | |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000/api/v1 (interactive docs at `/docs`) |

No `AI_API_KEY` is required to try the full workflow — every AI call runs in a clearly
labeled mock mode until one is configured.

**Run the tests:**

```bash
# Backend (in-memory SQLite, no real Postgres needed)
cd server && JWT_SECRET=x SIGNED_URL_SECRET=x AI_PROVIDER=mock python -m pytest -q

# Frontend
cd client && npm run test
```

## Deploying

Frontend on **Netlify** (the static `client/dist` bundle), backend on **Render** (Docker,
from `server/Dockerfile`) with Render Postgres. `netlify.toml` and `render.yaml` at the
repo root drive both platforms; **`DEPLOY.md`** walks through it step by step with every
environment variable and the gotchas this split has — relative signed file URLs need
Netlify's `/api/*` proxy rule, CORS is single-origin, Render's disk is ephemeral (never
`STORAGE_PROVIDER=local` there), and the per-IP rate limiter needs `FORWARDED_ALLOW_IPS=*`
to see real client IPs behind Render's proxy.

## How the system works, end to end

Read this section start to finish if you're new here — it walks through every real
request the app makes, in order, from a click in the browser to a row in Postgres and
back.

```
React (Vite, TS)  ---HTTP/JSON--->  FastAPI (/api/v1/*)  --->  PostgreSQL (SQLAlchemy
                                          |                     async, asyncpg)
                                          |--> Storage abstraction --> local disk | S3
                                          |--> AI abstraction --> Gemini | Anthropic | mock
                                          |--> Billing abstraction --> Stripe (Checkout +
                                                                        signed webhook)
```

Every response is an **envelope** — no route or component ever hand-builds either shape:

```json
// success
{ "success": true, "data": { ... } }
// error
{ "success": false, "error": { "code": "...", "message": "..." } }
```

### 1. Auth — signup → session → refresh

1. `POST /auth/signup {name, email, password, organizationName}` creates the
   Organization (the signer-upper becomes `org_admin`) plus a default report template,
   and returns an access token (JWT, 30 min) and a refresh token (opaque, 30 days,
   stored hashed in `sessions`).
2. Every request after that sends `Authorization: Bearer <accessToken>`.
3. When the access token expires, the frontend's axios interceptor
   (`client/src/api/axiosInstance.ts`) catches the 401, calls `POST /auth/refresh`,
   gets a new token pair (refresh tokens rotate on every use), and retries the original
   request once. Only if *that* fails does it clear tokens and redirect to `/login`.

Google sign-in (`POST /auth/google`) follows the identical find-or-create-then-issue-
tokens path, just with a Google `idToken` verified server-side instead of a password.
On the frontend, `routes/ProtectedRoute.tsx` sends anyone without a valid session to the
public `Landing` page at `/` — nothing under `/dashboard` (or any other authenticated
route) renders without a session first.

### 2. The core clinical flow — the product's entire reason to exist

1. `POST /patients` — create (or reuse) a patient record.
2. `POST /studies {patientId, modality}` — create a study, `status="uploaded"`.
3. `POST /uploads/studies/{id}/files` — upload via the active `StorageProvider` (local
   disk in dev, S3 in prod); the key is appended to `study.files[]`.
4. `POST /analysis/studies/{id}/analyze` — gated by `require_active_subscription`
   (see [Trial & billing](#5-trial--billing--gating-ai-report-generation)). Creates an
   `analysis_job`, then runs the AI pipeline **directly, in-request**:
   1. loads the study + patient + template
   2. downloads the file bytes from storage
   3. `BaseMedicalImagingProvider.analyze(...)` → `StructuredFindings` (observations, a
      short summary, an analyzable/not flag — never fabricated)
   4. saves those findings onto `study.lastFindings`
   5. `BaseReportGenerationProvider.summarize_findings(...)` and `.generate(...)` run
      **concurrently** (`asyncio.gather` — neither depends on the other's output): the
      former produces a short clinical summary (possibly a different model — see "AI" in
      the Stack table), the latter the rest of the report prose. The summary call's result
      always wins for the report's `summary` field.
   6. creates the Report (`version 1`, `author: "ai"`, `status: "ai_generated"`), marks
      the study `"completed"`, creates a Notification, writes an audit log entry

   Returns `200 {jobId}` only once **all** of the above has actually finished — there is
   no background worker (see [load-bearing facts](#multi-tenancy-ai-and-billing--the-load-bearing-facts)).
5. The frontend polls `GET /analysis/jobs/{jobId}` every ~2s until a terminal status,
   then opens the report. Since the job is already done by the time step 4's `POST`
   returns, the very first poll already sees a terminal status instead of watching real
   progress.

### 3. Doctor review — edit, request AI changes, regenerate, finalize

- **`PATCH /reports/{id}`** — a doctor's manual text edit. Appends a new version
  (`author: <doctor's userId>`, `status: "doctor_modified"`). The study's Report tab
  offers both ways to change a report side by side: an **Edit** button on `ReportViewer`
  toggles inline editable fields (summary/sections/impression/recommendations) that save
  straight to this endpoint, alongside `RequestChangesPanel` for the AI-mediated flow below.
- **`POST /reports/{id}/change-request {instruction}`** — runs synchronously, in-request:
  1. `classify_change_request(instruction)` — is this formatting-only, or does it need
     re-analysis?
  2. If **not** formatting-only: re-run imaging analysis (the doctor said "look again at X").
  3. If formatting-only: reuse `study.lastFindings` — never re-run analysis for a wording tweak.
  4. `revise()` → a new version, `status: "pending_review"`.
- **`POST /reports/{id}/regenerate`** — synchronous re-generation from the study's
  *existing* findings (no new image analysis) → a new version.
- **`POST /reports/{id}/finalize`** — `status: "finalized"`, immutable from this point
  on; every other mutating endpoint now returns `409`.

The report document (in-app view and PDF export) does not carry any status/AI-disclosure
banner or wording — it renders identically regardless of `status`. Status is only ever
surfaced in the surrounding UI (`ReportViewer`'s toolbar `StatusBadge`), which a downloaded
PDF has none of.

### 4. Multi-tenant isolation, concretely

Every read that returns a specific resource by id goes through
`find_by_id_scoped(id, organization_id)`. If the id exists but belongs to a different
org, the query returns nothing and the route raises a plain **404** — never 403, which
would confirm the resource exists at all. Exercised directly in
`server/app/tests/test_org_isolation.py`.

### 5. Trial & billing — gating AI report generation

On signup, `organizations.subscriptionStatus = "trial"` and
`trialEndsAt = now + TRIAL_DAYS` (3 days by default). From there,
`POST /analysis/studies/{id}/analyze` is gated by `require_active_subscription`:

| Org state | Result |
|---|---|
| `subscriptionStatus == "active"` | Allowed, no further checks |
| Still trialing, `trialEndsAt` not reached | Allowed, capped at `TRIAL_DAILY_REPORT_LIMIT` (100/day) — past that, `402 TRIAL_DAILY_LIMIT_REACHED` |
| Trial ended, no active subscription | `402 TRIAL_EXPIRED` |

- `POST /billing/checkout` creates a Stripe Checkout session, returns `{checkoutUrl}`.
- `POST /billing/webhook` is called **only** by Stripe's own servers (verified via
  `STRIPE_WEBHOOK_SECRET`, no user auth) — the *only* thing that can ever flip
  `subscriptionStatus` to `active`/`expired`.
- `GET /billing/status` returns `{subscriptionStatus, trialEndsAt, billingConfigured}`.

`settings.billing_configured` (`STRIPE_SECRET_KEY` + `STRIPE_PRICE_ID` both set) gates
whether checkout/the webhook can do anything — the trial gate itself works with zero
Stripe keys configured, since it's pure date/count logic.

## Backend layout (`server/app/`)

| Folder | What's in it |
|---|---|
| `core/` | Settings, JWT/password/RBAC primitives, centralized exception handling, logging config, the trial/subscription gate (`subscription.py`). |
| `database/` | The single async SQLAlchemy engine/session factory, one declarative model class per table. Tables are created automatically at startup, and `schema_sync.py` adds any column a model gained since (nullable/defaulted only) — no migration tool yet. |
| `schemas/` | Pydantic models for **request body validation only**; responses are plain dicts. |
| `repositories/` | One per table, all built on `BaseRepository` (insert/find/list/update/delete, organization-scoped except `users`/`organizations`/`sessions`). |
| `services/` | Business logic; routers stay thin (parse → call service → `ok(data)`). |
| `api/<domain>/routes.py` | One FastAPI router per domain, aggregated in `api/router.py`. |
| `ai/` | The two-layer AI abstraction — a mock provider and real model-backed ones. |
| `storage/` | Local-disk and S3(-compatible) providers behind one interface. |

Every id (`_id` included) is a **plain string** (a uuid4 hex, `utils/ids.py::new_id()`),
generated in application code — never a database-generated identity/UUID column. Table
columns are the snake_case form of the same camelCase field the API returns
(`app/database/casing.py` converts between the two generically at the repository
boundary), so a repository's return value is already a valid API response after one
key rename (`_id` → `id`).

## Frontend layout (`client/src/`)

React + TypeScript + Vite + React Router, plain CSS per component.

- **`context/AuthContext.tsx`** — the current user/organization and token-refresh logic.
- **`api/*.api.ts`** — one module per backend domain, wrapping the shared axios instance
  (`api/axiosInstance.ts`: access-token attachment + one silent refresh-then-retry on 401).
- **`components/ui/`** — generic primitives (Table, Pagination, Select, Toast, Modal,
  Button, …) every page composes.
- **`routes/RoleRoute.tsx`** — gates an entire route subtree by role, so individual
  pages don't need to re-check.

## Multi-tenancy, AI, and billing — the load-bearing facts

- **Multi-tenant isolation is structural.** Every organization-scoped repository method
  requires `organization_id` — there is no code path that queries a table without it. A
  resource belonging to another org 404s (not 403), so existence is never leaked.
- **AI is two independent interfaces** (`app/ai/base.py`): `BaseMedicalImagingProvider`
  looks at the image and returns structured findings; `BaseReportGenerationProvider`
  turns findings + a template into report prose. Swapping providers is one env var
  (`AI_PROVIDER`) — nothing in `services/`/`api/` changes. The real provider(s) use a
  tiered model strategy (fast/default/highAccuracy) so imaging interpretation gets a
  capable model while formatting-only revisions route to the cheapest tier.
- **No background job queue (deliberate, temporary).** Redis/ARQ were removed to drop an
  infra dependency — analysis and change-requests now run synchronously in-request and
  return `200 {jobId}` only once the AI work finishes. In production, with a real
  (non-mock) AI provider, a slow call blocks the request for its full duration —
  highest-priority item to fix before real load (see below).
- **Trial & billing.** Every org starts on a free trial (`TRIAL_DAYS`, capped at
  `TRIAL_DAILY_REPORT_LIMIT` reports/day). `require_active_subscription` gates
  `POST /analysis/studies/{id}/analyze`; only a Stripe-signed webhook
  (`POST /billing/webhook`) can ever flip `subscriptionStatus` to `active` — the app
  never trusts a client-supplied "I paid" signal.

## What to add next, and why

| # | Add | Why |
|---|---|---|
| 1 | A real background job queue | Highest priority — see above. |
| 2 | Database migrations (Alembic) | Tables come from `Base.metadata.create_all` at startup plus `schema_sync.py`, which can only *add* nullable/defaulted columns — renames, type changes, and NOT NULL backfills still have no data-preserving path. |
| 3 | Real email/SMS delivery | Password-reset links and invite passwords are only logged today — blocks any real multi-user rollout. |
| 4 | A Redis-backed rate limiter | The current one is in-process; each additional API replica gets its own counter, silently weakening the intended global limit. |
| 5 | DICOM/PACS/DICOMweb/HL7/FHIR integration | `Study` only has placeholder UID fields today. |
| 6 | ~~A manual rich-text report editor UI~~ | Done — `ReportViewer`'s Edit mode now covers this; `PATCH /reports/{id}` was already there. |
| 7 | A CI pipeline | Tests exist and pass locally but nothing runs them on push. |
| 8 | A persisted per-part model attribution | A report version's `aiModelUsed` is one string, but a version can now be produced by two calls (a summary model and a report model) — worth a schema field once there's a concrete need to show/audit that split. |
