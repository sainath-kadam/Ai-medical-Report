"""Multi-tenant isolation is the one guarantee that must never regress (CONTRACTS.md §7).
This test creates two independent organizations and confirms org A can never read,
by id, a resource that belongs to org B — the response must be a plain 404, never a 403
that would confirm the resource exists at all.
"""


async def test_patient_created_in_one_org_is_invisible_to_another(client, signup_and_login):
    org_a = await signup_and_login(email="doctor-a@example.com", organization_name="Clinic A")

    create_response = await client.post(
        "/patients",
        json={"mrn": "MRN-001", "name": "Alice Patient", "dateOfBirth": "1990-01-01", "sex": "female"},
    )
    assert create_response.status_code == 201, create_response.text
    patient_id = create_response.json()["data"]["id"]

    # Second organization, different account entirely.
    client.headers.pop("Authorization", None)
    await signup_and_login(email="doctor-b@example.com", organization_name="Clinic B")

    cross_org_response = await client.get(f"/patients/{patient_id}")
    assert cross_org_response.status_code == 404
    assert cross_org_response.json()["success"] is False

    # Org B's own patient list must be empty — org A's patient must not leak into it.
    list_response = await client.get("/patients")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"] == []


async def test_signup_creates_org_admin_with_default_template(client, signup_and_login):
    data = await signup_and_login(email="owner@example.com", organization_name="Solo Clinic")
    assert data["user"]["role"] == "org_admin"
    assert data["organization"]["name"] == "Solo Clinic"

    templates_response = await client.get("/templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()["data"]["items"]
    assert len(templates) == 1
    assert templates[0]["isDefault"] is True
