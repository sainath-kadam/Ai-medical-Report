"""Stripe billing (new — not part of the original CONTRACTS.md spec).

Two entry points: `create_checkout_session` (`POST /billing/checkout`) hands the frontend a
Stripe-hosted Checkout URL to redirect the doctor to; `handle_webhook_event`
(`POST /billing/webhook`, called by Stripe itself, never the frontend) is what actually
flips `organizations.subscriptionStatus` to `active` once payment succeeds, and to
`expired` if the subscription later lapses/cancels — nothing here ever trusts a
client-supplied "I paid" signal, only Stripe's own signed webhook event.

`app/core/subscription.py::require_active_subscription` is what actually enforces the
resulting status on report-generation routes; this module only ever writes it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.subscription import evaluate_access
from app.core.logging import get_logger
from app.repositories.organization_repository import OrganizationRepository

logger = get_logger(__name__)

# Subscription states that mean "no longer paying" on the Stripe object itself.
_STRIPE_INACTIVE_STATUSES = ("canceled", "unpaid", "incomplete_expired")


class BillingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.orgs = OrganizationRepository(db)

    def _require_configured(self) -> None:
        if not settings.billing_configured:
            raise AppError.bad_request("Billing is not configured on this server yet.", "BILLING_NOT_CONFIGURED")

    async def create_checkout_session(self, organization_id: str, user_email: str) -> str:
        """Returns a Stripe-hosted Checkout URL for the frontend to redirect the doctor to."""
        self._require_configured()
        org = await self.orgs.find_by_id(organization_id)
        if org is None:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")

        stripe.api_key = settings.stripe_secret_key
        existing_customer_id = org.get("stripeCustomerId")
        # The blocking Stripe SDK does a real network call — offload it so it never blocks
        # the event loop (same pattern `AuthService._verify_google_id_token` already uses).
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
            customer=existing_customer_id or None,
            customer_email=None if existing_customer_id else user_email,
            client_reference_id=organization_id,
            success_url=f"{settings.client_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.client_url}/billing/cancel",
            metadata={"organizationId": organization_id},
        )
        return session.url

    async def get_status(self, organization_id: str) -> dict[str, Any]:
        org = await self.orgs.find_by_id(organization_id)
        if org is None:
            raise AppError.not_found("Organization not found", "ORGANIZATION_NOT_FOUND")
        # `access` is the single evaluated answer to "can this org write right now, until
        # when, and why" (app/core/subscription.py::evaluate_access) — the billing page
        # renders from it instead of re-deriving the trial/Stripe/manual-period precedence.
        return {
            "subscriptionStatus": org["subscriptionStatus"],
            "trialEndsAt": org.get("trialEndsAt"),
            "accessEndsAt": org.get("accessEndsAt"),
            "isSuspended": bool(org.get("isSuspended")),
            "access": evaluate_access(org).to_public(),
            "billingConfigured": settings.billing_configured,
        }

    async def handle_webhook_event(self, payload: bytes, signature: str | None) -> None:
        self._require_configured()
        try:
            event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
        except Exception as exc:  # signature mismatch, malformed payload, etc. — always a 400
            raise AppError.bad_request("Invalid Stripe webhook payload", "INVALID_WEBHOOK") from exc

        event_type = event["type"]
        data = event["data"]["object"]

        if event_type == "checkout.session.completed":
            organization_id = data.get("client_reference_id") or (data.get("metadata") or {}).get("organizationId")
            if not organization_id:
                logger.error("Stripe checkout.session.completed with no organization reference")
                return
            await self.orgs.update(
                organization_id,
                {
                    "subscriptionStatus": "active",
                    "stripeCustomerId": data.get("customer"),
                    "stripeSubscriptionId": data.get("subscription"),
                },
            )
            logger.info("Subscription activated via checkout: organizationId=%s", organization_id)

        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            customer_id = data.get("customer")
            stripe_status = data.get("status")
            if not customer_id:
                return
            org = await self.orgs.find_by_stripe_customer_id(customer_id)
            if org is None:
                logger.error("Stripe subscription event for unknown customerId=%s", customer_id)
                return
            new_status = "active" if stripe_status == "active" else "expired" if stripe_status in _STRIPE_INACTIVE_STATUSES else None
            if new_status:
                await self.orgs.update(org["_id"], {"subscriptionStatus": new_status})
                logger.info("Subscription %s: organizationId=%s", new_status, org["_id"])
