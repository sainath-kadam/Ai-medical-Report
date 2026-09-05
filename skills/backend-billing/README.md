# backend-billing

Trial and paid-subscription gating for AI report generation, plus the Stripe checkout/
webhook flow that flips an organization between the two. New domain, not part of the
original CONTRACTS.md spec — see CONTRACTS.md §2a.

## Key files

- `server/app/core/subscription.py` — `evaluate_access(org) -> OrgAccess` (the ONE answer to
  "can this org write, until when, why": suspended > Stripe active > manual `accessEndsAt`
  > trial), `require_writable_organization` (router-level read-only gate, CONTRACTS.md §2c:
  passes GET, 402s other methods with the reason as code), and
  `require_active_subscription` (analyze route: same rule + the trial daily report cap →
  `TRIAL_DAILY_LIMIT_REACHED`). `with_access(org_doc)` attaches `access` to org responses
  and strips platform-only fields.
- `server/app/services/billing_service.py` — `BillingService`: `create_checkout_session`
  (Stripe-hosted Checkout URL), `get_status` (`subscriptionStatus`, `trialEndsAt`,
  `accessEndsAt`, `isSuspended`, evaluated `access`, `billingConfigured`),
  `handle_webhook_event` (the only writer of `organizations.subscriptionStatus`; the
  platform domain writes the manual-access fields instead — see `backend-platform`).
- `server/app/api/billing/routes.py` — `POST /billing/checkout`, `GET /billing/status`
  (both normal authenticated routes), `POST /billing/webhook` (called by Stripe itself).

## Non-obvious things

- **The webhook route has no bearer-token auth.** `POST /billing/webhook` can't require
  `get_current_user` because Stripe's servers call it directly with no doctor JWT — its only
  gate is `stripe.Webhook.construct_event` verifying the `Stripe-Signature` header inside
  `handle_webhook_event`. This mirrors how `app/api/uploads/routes.py`'s public download
  route is gated by a signed token instead of a bearer token. Never add `get_current_user`
  here and never trust a client-supplied "I paid" signal from anywhere else.
- **Trial dates need timezone normalization before comparing.** SQLite (used in tests, see
  `tests/conftest.py`) silently drops tzinfo on `DateTime(timezone=True)` round-trips,
  unlike Postgres. `subscription.py::_as_aware_utc` re-attaches UTC before any comparison —
  if you add a new datetime comparison against `trial_ends_at` elsewhere, run it through the
  same normalization or it will raise `TypeError` under SQLite but not Postgres.
- **`BillingService` only ever writes `subscriptionStatus`; `subscription.py` only ever
  reads/enforces it.** Every org starts `"trial"` at signup (`AuthService.
  _provision_org_and_admin_user` sets `trialEndsAt = now + settings.trial_days`,
  default `TRIAL_DAYS=3`), capped at `settings.trial_daily_report_limit`
  (`TRIAL_DAILY_REPORT_LIMIT`, default 100/day) while trialing. Stripe events flip it to
  `"active"` on `checkout.session.completed`, or `"active"`/`"expired"` on
  `customer.subscription.updated|deleted` depending on the Stripe subscription status.
  Billing is considered "not configured" (`BILLING_NOT_CONFIGURED`, 400) whenever
  `STRIPE_SECRET_KEY`/`STRIPE_PRICE_ID` aren't both set — checkout and the webhook both
  refuse to run in that state, they don't silently no-op.
