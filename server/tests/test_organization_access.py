"""Organization access management (CONTRACTS.md §2c): the read-only mode an organization
falls into when its trial / paid / granted access lapses or a system_admin suspends it, and
the platform routes a system_admin uses to grant an access period, suspend, and inspect.

What matters here:
- `evaluate_access` precedence: suspended > Stripe active > manual period > trial > nothing.
- The router-level gate (`require_writable_organization`) refuses every write with 402
  (code = the reason: TRIAL_EXPIRED / ACCESS_EXPIRED / ORGANIZATION_SUSPENDED) while an org
  isn't writable, but reads, login, and billing keep working — people can always see their
  data and pay their way back in.
- A system_admin's grant flips an expired org back to writable without any Stripe event,
  and every such change lands in the org's own audit trail.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.subscription import evaluate_access
from app.repositories.organization_repository import OrganizationRepository
from tests.test_platform import _create_system_admin

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _org(**overrides):
    base = {
        "subscriptionStatus": "trial",
        "trialEndsAt": (NOW + timedelta(days=1)).isoformat(),
        "accessEndsAt": None,
        "isSuspended": False,
    }
    return {**base, **overrides}


def test_evaluate_access_precedence():
    trial = evaluate_access(_org(), NOW)
    assert trial.writable and trial.source == "trial" and trial.reason is None

    expired_trial = _org(trialEndsAt=(NOW - timedelta(days=1)).isoformat())
    lapsed = evaluate_access(expired_trial, NOW)
    assert not lapsed.writable and lapsed.reason == "TRIAL_EXPIRED" and lapsed.source == "none"

    granted = evaluate_access({**expired_trial, "accessEndsAt": (NOW + timedelta(days=30)).isoformat()}, NOW)
    assert granted.writable and granted.source == "manual"
    assert granted.ends_at == NOW + timedelta(days=30)

    grant_over = evaluate_access({**expired_trial, "accessEndsAt": (NOW - timedelta(hours=1)).isoformat()}, NOW)
    assert not grant_over.writable and grant_over.reason == "ACCESS_EXPIRED"

    paid = evaluate_access({**expired_trial, "subscriptionStatus": "active"}, NOW)
    assert paid.writable and paid.source == "subscription" and paid.ends_at is None

    suspended = evaluate_access({**expired_trial, "subscriptionStatus": "active", "isSuspended": True}, NOW)
    assert not suspended.writable and suspended.reason == "ORGANIZATION_SUSPENDED"

    # SQLite hands back naive datetimes; a naive ISO string must compare as UTC, not raise.
    naive = evaluate_access(_org(trialEndsAt=(NOW + timedelta(days=1)).replace(tzinfo=None).isoformat()), NOW)
    assert naive.writable

    public = granted.to_public()
    assert set(public) == {"writable", "reason", "source", "endsAt"}
    assert public["endsAt"].startswith("2026-10-05")


def _patient(mrn: str) -> dict:
    return {"mrn": mrn, "name": "Pat Example", "dateOfBirth": "1990-01-01", "sex": "other"}


async def test_expired_org_is_read_only_until_platform_grants_access(client, db, signup_and_login):
    login = await signup_and_login(email="ro.admin@example.com", organization_name="Read Only Clinic")
    org_id = login["organization"]["id"]
    assert login["organization"]["access"]["writable"] is True
    org_admin_auth = client.headers["Authorization"]

    assert (await client.post("/patients", json=_patient("MRN-RO-1"))).status_code == 201

    # --- Trial lapses: writes refused, everything else keeps working ---
    await OrganizationRepository(db).update(org_id, {"trialEndsAt": datetime.now(timezone.utc) - timedelta(days=1)})

    blocked = await client.post("/patients", json=_patient("MRN-RO-2"))
    assert blocked.status_code == 402, blocked.text
    assert blocked.json()["error"]["code"] == "TRIAL_EXPIRED"  # same code the analyze route always used

    assert (await client.get("/patients")).status_code == 200
    me = await client.get("/auth/me")
    access = me.json()["data"]["organization"]["access"]
    assert access["writable"] is False and access["reason"] == "TRIAL_EXPIRED"

    relogin = await client.post("/auth/login", json={"email": "ro.admin@example.com", "password": "testpass123"})
    assert relogin.status_code == 200
    assert relogin.json()["data"]["organization"]["access"]["writable"] is False

    # Billing is the way back in, so it is not behind the read-only gate (400 = Stripe not
    # configured in tests, which is the route's own answer, not a 402 from the gate).
    checkout = await client.post("/billing/checkout")
    assert checkout.status_code == 400 and checkout.json()["error"]["code"] == "BILLING_NOT_CONFIGURED"
    status = (await client.get("/billing/status")).json()["data"]
    assert status["access"]["writable"] is False and status["isSuspended"] is False

    # --- A system_admin grants an access period by hand ---
    _, sys_password = await _create_system_admin(db, email="owner@example.com")
    sys_login = await client.post("/auth/login", json={"email": "owner@example.com", "password": sys_password})
    sys_auth = f"Bearer {sys_login.json()['data']['accessToken']}"
    client.headers["Authorization"] = sys_auth

    listing = (await client.get("/platform/organizations")).json()["data"]
    row = next(o for o in listing["items"] if o["id"] == org_id)
    assert row["access"]["writable"] is False
    assert row["userCount"] == 1 and row["reportCount"] == 0

    until = datetime.now(timezone.utc) + timedelta(days=30)
    granted = await client.patch(
        f"/platform/organizations/{org_id}/access",
        json={"accessEndsAt": until.isoformat(), "accessNote": "Invoice #42, 1 month", "plan": "pro"},
    )
    assert granted.status_code == 200, granted.text
    granted_org = granted.json()["data"]["organization"]
    assert granted_org["access"]["writable"] is True and granted_org["access"]["source"] == "manual"
    assert granted_org["plan"] == "pro" and granted_org["accessNote"] == "Invoice #42, 1 month"

    detail = (await client.get(f"/platform/organizations/{org_id}")).json()["data"]
    assert [u["email"] for u in detail["users"]] == ["ro.admin@example.com"]
    assert "passwordHash" not in detail["users"][0]

    # --- The org can write again, and sees what happened in its own audit trail ---
    client.headers["Authorization"] = org_admin_auth
    assert (await client.post("/patients", json=_patient("MRN-RO-3"))).status_code == 201
    status = (await client.get("/billing/status")).json()["data"]
    assert status["access"]["source"] == "manual" and status["accessEndsAt"] is not None
    # The note is for the platform team only — never in what the org itself receives.
    assert "accessNote" not in (await client.get("/organizations/me")).json()["data"]["organization"]

    actions = [entry["action"] for entry in (await client.get("/audit-logs")).json()["data"]["items"]]
    assert "ORGANIZATION_ACCESS_UPDATED" in actions

    # --- Suspension overrides the grant; lifting it restores the grant ---
    client.headers["Authorization"] = sys_auth
    suspended = await client.patch(f"/platform/organizations/{org_id}/access", json={"isSuspended": True})
    assert suspended.json()["data"]["organization"]["access"]["reason"] == "ORGANIZATION_SUSPENDED"

    client.headers["Authorization"] = org_admin_auth
    blocked = await client.post("/patients", json=_patient("MRN-RO-4"))
    assert blocked.status_code == 402 and blocked.json()["error"]["code"] == "ORGANIZATION_SUSPENDED"
    assert "suspended" in blocked.json()["error"]["message"].lower()
    assert (await client.get("/patients")).status_code == 200
    # org_admin-only writes are read-only too: no inviting users while suspended.
    invite = await client.post("/users", json={"name": "New Doc", "email": "newdoc@example.com", "role": "doctor"})
    assert invite.status_code == 402

    client.headers["Authorization"] = sys_auth
    lifted = await client.patch(f"/platform/organizations/{org_id}/access", json={"isSuspended": False})
    assert lifted.json()["data"]["organization"]["access"]["source"] == "manual"

    client.headers["Authorization"] = org_admin_auth
    assert (await client.post("/patients", json=_patient("MRN-RO-5"))).status_code == 201


async def test_org_admin_cannot_reach_organization_management(client, signup_and_login):
    await signup_and_login(email="plain.admin@example.com", organization_name="Plain Clinic")
    assert (await client.get("/platform/organizations")).status_code == 403
    assert (await client.get("/platform/organizations/whatever")).status_code == 403
    assert (await client.patch("/platform/organizations/whatever/access", json={"isSuspended": True})).status_code == 403
    assert (await client.get("/platform/system-admins")).status_code == 403


async def test_system_admin_lists_and_adds_platform_admins(client, db):
    _, password = await _create_system_admin(db, email="first.owner@example.com")
    login = await client.post("/auth/login", json={"email": "first.owner@example.com", "password": password})
    client.headers["Authorization"] = f"Bearer {login.json()['data']['accessToken']}"

    before = (await client.get("/platform/system-admins")).json()["data"]
    assert [a["email"] for a in before] == ["first.owner@example.com"]
    assert "passwordHash" not in before[0]

    invited = await client.post("/platform/system-admins", json={"name": "Second Owner", "email": "second.owner@example.com"})
    assert invited.status_code == 201 and invited.json()["data"]["temporaryPassword"]

    after = (await client.get("/platform/system-admins")).json()["data"]
    assert [a["email"] for a in after] == ["first.owner@example.com", "second.owner@example.com"]

    empty = await client.patch("/platform/organizations/whatever/access", json={})
    assert empty.status_code == 400 and empty.json()["error"]["code"] == "EMPTY_UPDATE"
