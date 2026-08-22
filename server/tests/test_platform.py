"""Covers the platform domain (CONTRACTS.md §2a) — the one place a `system_admin` account
(no organization of its own) acts across organizations instead of within one. The core
thing worth verifying here is the privilege boundary: a regular org_admin must never be
able to reach these routes or grant themselves/anyone else `system_admin` via the normal
invite endpoint.
"""

from app.core.security import hash_password
from app.repositories.user_repository import UserRepository


async def _create_system_admin(db, email="sys.admin@example.com", password="sysadminpass123"):
    created = await UserRepository(db).insert(
        {
            "name": "Sys Admin",
            "email": email,
            "passwordHash": hash_password(password),
            "googleId": None,
            "avatarUrl": None,
            "role": "system_admin",
            "organizationId": None,
            "isActive": True,
            "emailVerifiedAt": None,
        }
    )
    return created, password


async def test_system_admin_creates_organization_and_its_first_admin_can_log_in(client, db):
    _, password = await _create_system_admin(db)
    login = await client.post("/auth/login", json={"email": "sys.admin@example.com", "password": password})
    assert login.status_code == 200, login.text
    assert login.json()["data"]["organization"] is None  # system_admin has no org

    client.headers["Authorization"] = f"Bearer {login.json()['data']['accessToken']}"
    create_response = await client.post(
        "/platform/organizations",
        json={
            "organizationName": "Lakeside Family Clinic",
            "adminName": "Dr. Priya Nair",
            "adminEmail": "priya@example.com",
        },
    )
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()["data"]
    assert body["organization"]["name"] == "Lakeside Family Clinic"
    assert body["adminUser"]["role"] == "org_admin"
    temp_password = body["temporaryPassword"]

    # The new org's first admin can actually log in with the returned temp password.
    client.headers.pop("Authorization", None)
    new_admin_login = await client.post("/auth/login", json={"email": "priya@example.com", "password": temp_password})
    assert new_admin_login.status_code == 200
    assert new_admin_login.json()["data"]["organization"]["name"] == "Lakeside Family Clinic"


async def test_regular_org_admin_cannot_reach_platform_routes_or_self_escalate(client, signup_and_login):
    await signup_and_login(email="regular.admin@example.com", organization_name="Regular Clinic")

    blocked = await client.post(
        "/platform/organizations",
        json={"organizationName": "Sneaky Org", "adminName": "Eve", "adminEmail": "eve@example.com"},
    )
    assert blocked.status_code == 403

    escalation_attempt = await client.post(
        "/users", json={"name": "Eve", "email": "eve2@example.com", "role": "system_admin"}
    )
    assert escalation_attempt.status_code == 422
