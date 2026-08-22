# backend-billing

Trial and paid-subscription gating for AI report generation, plus the Stripe checkout/
webhook flow that flips an organization between the two. New domain, not part of the
original CONTRACTS.md spec — see CONTRACTS.md §2a.

## Key files

- `server/app/core/subscription.py` — `require_active_subscription`, the `Depends()` gate
  applied to `POST /analysis/studies/{id}/analyze` (and nowhere else). Raises 402
  (`TRIAL_EXPIRED` / `TRIAL_DAILY_LIMIT_REACHED`) when the org has no active paid
  subscription and the trial window/day-limit is exhausted; otherwise a no-op pass-through.
- `server/app/services/billing_service.py` — `BillingService`: `create_checkout_session`
  (Stripe-hosted Checkout URL), `get_status` (current `subscriptionStatus`/`trialEndsAt`),
  `handle_webhook_event` (the only writer of `organizations.subscriptionStatus`).
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
