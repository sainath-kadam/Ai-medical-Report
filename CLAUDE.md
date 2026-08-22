# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Working on a specific module? Go to `skills/` first** — `skills/README.md` (or the
> machine-readable `skills/index.json`) catalogs one short skill per backend domain /
> frontend area. Read the matching skill before the rest of the codebase — that's the
> fast path and avoids burning context re-deriving what's already documented there.
>
> For the whole system: `README.md` — structure, and how a request flows frontend to
> backend (read this first). `CONTRACTS.md` — the exact wire contract: every route,
> entity shape, RBAC matrix. This file is deliberately short — commands plus the handful
> of facts that don't fit any of those.

## Commands

### Backend (`server/`)

```bash
# Setup (Windows: .venv\Scripts\activate instead of source .venv/bin/activate)
cd server && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Run the API (needs Postgres reachable; see docker-compose.yml for a local instance.
# Tables are created automatically at startup — no separate migration step)
uvicorn app.main:app --reload --port 8000
# API docs auto-generated at /docs (Swagger) and /redoc once running.

# AI analysis (POST /analysis/studies/{id}/analyze) and report change-requests
# (POST /reports/{id}/change-request) run synchronously, in-request — there is no
# background worker process to run separately (see README.md's "load-bearing facts"
# for the trade-off this implies in production).

# Tests (in-memory SQLite via aiosqlite — no real Postgres needed; JWT_SECRET/
# SIGNED_URL_SECRET/AI_PROVIDER=mock only need to be *set to something*, not real values)
JWT_SECRET=x SIGNED_URL_SECRET=x AI_PROVIDER=mock python -m pytest -q
# Single test file:
JWT_SECRET=x SIGNED_URL_SECRET=x AI_PROVIDER=mock python -m pytest tests/test_report_lifecycle.py -q
# Single test:
JWT_SECRET=x SIGNED_URL_SECRET=x AI_PROVIDER=mock python -m pytest tests/test_report_lifecycle.py::test_full_report_lifecycle -q

# No linter/formatter is configured yet (no ruff/mypy/black config exists) — don't
# assume one and don't invent commands for it.
```

### Frontend (`client/`)

```bash
npm install
npm run dev         # Vite dev server, :5173, proxies /api to 127.0.0.1:8000 (see
                     # vite.config.ts's comment on why 127.0.0.1 and not "localhost")
npm run build        # tsc -b && vite build
npm run typecheck    # tsc --noEmit, no build output — run this after any non-trivial change
npm run test          # vitest run (one-shot)
npm run test:watch    # vitest, watch mode
npx vitest run src/path/to/File.test.ts   # single test file
```

### Whole stack

```bash
docker compose up --build   # postgres + api + client, wired together
```

## Architecture map

This is a multi-tenant medical-imaging AI reporting platform: FastAPI/SQLAlchemy(async)/
PostgreSQL backend, React/Vite frontend, AI analysis and report change-requests run
synchronously in-request (no background job queue — a deliberate, temporary
simplification, see `README.md`), pluggable AI provider (Gemini by default, or Anthropic
or a zero-cost mock)
and storage provider (local disk or S3). Full structure/flow detail: `README.md`. Exact
wire contract: `CONTRACTS.md`.

Every doctor-facing account (`org_admin`/`doctor` — there is no patient login/portal) gets
a free trial at signup (`TRIAL_DAYS`, default 3 days, capped at `TRIAL_DAILY_REPORT_LIMIT`
AI reports/day, default 100 — see `.env.example`). Generating a report after the trial ends requires an
active Stripe subscription; `server/app/core/subscription.py` enforces this,
`server/app/api/billing/` handles checkout + the Stripe webhook.

## The one thing every file assumes you already know

Every id is a **plain string** (a `uuid4().hex`, generated in application code), never a
database-generated integer/UUID type. Every API response is
`{"success": true, "data": ...}` or `{"success": false, "error": {"code", "message"}}`.
Multi-tenant isolation is structural (repository methods require `organization_id`, there
is no method that queries without it), not something re-checked per route.
