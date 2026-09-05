# backend-core

Cross-cutting infrastructure every domain sits on top of: environment config, the
`AppError`/exception-handler contract, logging setup, the trial/subscription gate, and
request-level middleware (rate limiting, request-id/IP capture).

## Key files

- `server/app/core/config.py` — the single `Settings` (pydantic-settings) instance every
  module reads via `from app.core.config import settings`; nothing should call
  `os.environ` directly. Backs `.env` in dev, real env vars elsewhere.
- `server/app/core/exceptions.py` — `AppError` (with `.bad_request`/`.unauthorized`/
  `.forbidden`/`.not_found`/`.conflict`/`.too_many_requests`/`.payment_required` factory
  classmethods) plus `register_exception_handlers(app)`, which guarantees every error
  response — expected `AppError`, validation error, HTTP error, or unhandled exception —
  comes back shaped `{"success": false, "error": {"code", "message"}}` and never leaks a
  stack trace.
- `server/app/core/logging.py` — `configure_logging()` / `get_logger(name)`. Plain
  text format in dev, single-line JSON in production; quiets noisy third-party loggers
  (`uvicorn.access`, `sqlalchemy.engine`, `botocore`, `urllib3`) to WARNING.
- `server/app/core/subscription.py` — `require_active_subscription`, a `Depends()` gate
  used only on the route that creates new AI reports
  (`POST /analysis/studies/{id}/analyze`). Not part of the original CONTRACTS.md spec — a
  later addition.
- `server/app/middleware/rate_limit.py` — `RateLimitMiddleware`: in-process sliding-window
  limiter, dict-based, single-process only.
- `server/app/middleware/request_context.py` — `RequestContextMiddleware`: stamps a
  request id, captures client IP/User-Agent onto `request.state` for audit logging, and
  logs one line per request with status/duration.

## Non-obvious things

- **Logging has a hard content rule, not just a formatting one** (spec §31/§33): nothing
  that touches patient/report/clinical content may ever be logged, at any call site. This
  module only controls format/routing — enforcing *what* gets logged is a per-call-site
  discipline, e.g. `auth_service.py` logs a password-reset link but explicitly never the
  password itself.
- **The rate limiter has two buckets, not one, and mixing them up breaks real users.**
  `_BRUTE_FORCE_PRONE_PATHS` (login/signup/google/forgot-password/reset-password) gets the
  tight `rate_limit_auth_per_15min` cap; every other `/api/` path — including authenticated
  auth-utility routes like `/auth/me`, `/auth/refresh`, `/auth/logout`,
  `/auth/change-password` — gets the much looser `rate_limit_api_per_15min` cap. This split
  exists because of a real incident: those utility routes are called on routine page loads/
  navigation (see the frontend's `AuthContext.tsx` `refreshProfile`), and sharing the tight
  auth budget eventually 429'd normal browsing, which the frontend then misread as "not
  authenticated." Don't add a new credential-guessing-sensitive route without adding it to
  `_BRUTE_FORCE_PRONE_PATHS`, and don't move an authenticated utility route into that tuple.
- **`require_active_subscription` normalizes timezone-naive datetimes before comparing**
  (`_as_aware_utc`) because SQLite (used in tests, aiosqlite) silently drops tzinfo on
  `DateTime(timezone=True)` round-trips, unlike Postgres — without this, trial-expiry
  comparisons would raise `TypeError` under the test suite but work fine against real
  Postgres. If you touch this file, keep that normalization or tests will break in a way
  that doesn't reproduce in dev/prod.
- Trial gating logic: `subscriptionStatus == "active"` always passes; otherwise it must be
  `"trial"` with `trial_ends_at` in the future, and even then daily report count (UTC
  calendar day) is capped at `settings.trial_daily_report_limit` — both failure paths raise
  `402 Payment Required` (`TRIAL_EXPIRED` / `TRIAL_DAILY_LIMIT_REACHED`), enforced only at
  the one report-creation route, not globally.
- **Read-only mode is one router-level dependency, not per-route checks** (CONTRACTS.md
  §2c). `app/api/router.py` attaches `subscription.require_writable_organization` to every
  org-scoped router with write routes; it resolves the org from the JWT's `orgId` claim
  itself (router deps run before the route's `get_current_user`, and the uploads router has a
  token-less public GET that must keep working), lets safe methods through, and 402s the rest
  with `evaluate_access(org).reason` as the code. `auth`/`billing`/`dashboard`/`audit_logs`/
  `notifications`/`platform` are deliberately not gated. Adding a new org-scoped domain with
  writes? Include it with `dependencies=_READ_ONLY_GATE` there.
