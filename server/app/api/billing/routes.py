"""Billing routes (new domain, not part of the original CONTRACTS.md spec).

`POST /checkout` and `GET /status` are normal authenticated routes. `POST /webhook` is
deliberately NOT behind `get_current_user` — it's called by Stripe's own servers, which
can't attach a doctor's JWT — its only gate is the Stripe-signed payload verified inside
`BillingService.handle_webhook_event`, mirroring how `app/api/uploads/routes.py`'s public
download route is gated by a signed token instead of a bearer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import CurrentUser, get_current_user, require_admin_or_doctor
from app.services.billing_service import BillingService
from app.utils.response import ok

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def create_checkout(
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    checkout_url = await BillingService(db).create_checkout_session(current_user.organization_id, current_user.email)
    return ok({"checkoutUrl": checkout_url})


@router.get("/status")
async def get_billing_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await BillingService(db).get_status(current_user.organization_id))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    await BillingService(db).handle_webhook_event(payload, signature)
    return ok({"received": True})
