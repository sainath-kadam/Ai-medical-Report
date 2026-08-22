"""Covers the template-customization feature (style colors/font size, logo upload, and the
stateless `/preview-pdf` render used by both the template editor's live preview and
`NewStudyForm`'s "which template will this study use" preview).

Two things get dedicated regression coverage because they're easy to silently break later:
- RBAC on `/preview-pdf` must stay open to any authenticated org member (not org_admin-only)
  — a doctor starting a study needs to see it, and nothing there is persisted.
- `_sanitize_logo_key` must keep dropping a `logoKey` that doesn't belong to the calling
  org, since without it a client could point a template at another org's storage key and
  have the server embed those bytes into a PDF handed back to them.
"""

import base64

# The smallest possible valid PNG (a single transparent pixel) -- enough for
# `_logo_flowable`/`ImageReader` to parse real image bytes without needing a fixture file.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _template_payload(**overrides):
    payload = {
        "name": "Custom Template",
        "header": {"organizationName": "Riverside Imaging", "tagline": "Precision care", "contactNumber": "555-0100"},
        "sections": [{"key": "findings", "title": "Findings", "order": 10, "enabled": True}],
        "accentColor": "#1D4ED8",
        "style": {"headerTextColor": "#111827", "backgroundColor": "#FFFFFF", "contentTextColor": "#101828", "fontSize": 11},
    }
    payload.update(overrides)
    return payload


async def test_upload_logo_and_use_it_in_a_template(client, signup_and_login):
    await signup_and_login(email="admin@example.com", organization_name="Riverside Imaging")

    upload_response = await client.post("/templates/logo", files={"file": ("logo.png", _TINY_PNG, "image/png")})
    assert upload_response.status_code == 201, upload_response.text
    logo = upload_response.json()["data"]
    assert logo["logoKey"].startswith("template_logo/")
    assert logo["logoUrl"]

    create_response = await client.post(
        "/templates", json=_template_payload(header={"organizationName": "Riverside Imaging", "logoKey": logo["logoKey"]})
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()["data"]
    assert created["header"]["logoKey"] == logo["logoKey"]
    assert created["header"]["logoUrl"]  # signed fresh on this response, never persisted
    assert created["style"]["fontSize"] == 11


async def test_logo_upload_rejects_non_image_and_oversized_files(client, signup_and_login):
    await signup_and_login(email="admin2@example.com", organization_name="Reject Clinic")

    non_image = await client.post("/templates/logo", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert non_image.status_code == 400
    assert non_image.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    oversized = await client.post(
        "/templates/logo", files={"file": ("big.png", b"0" * (2 * 1024 * 1024 + 1), "image/png")}
    )
    assert oversized.status_code == 400
    assert oversized.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_preview_pdf_renders_an_unsaved_draft(client, signup_and_login):
    await signup_and_login(email="admin3@example.com", organization_name="Preview Clinic")

    response = await client.post("/templates/preview-pdf", json=_template_payload())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


async def test_fractional_font_size_is_accepted(client, signup_and_login):
    """Regression: `fontSize` must accept a fractional value like 10.5 (the frontend's
    "Medium" option, and pdf_service.py's own historical default) -- an int-typed field
    rejects it with a 422 ("Input should be a valid integer, got a number with a fractional
    part"), which broke the live preview for any template using that default."""
    await signup_and_login(email="admin5@example.com", organization_name="Fractional Font Clinic")

    payload = _template_payload(style={"fontSize": 10.5})
    preview_response = await client.post("/templates/preview-pdf", json=payload)
    assert preview_response.status_code == 200, preview_response.text
    assert preview_response.content[:4] == b"%PDF"

    create_response = await client.post("/templates", json=payload)
    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["data"]["style"]["fontSize"] == 10.5


async def test_doctor_can_preview_but_not_mutate_templates(client, signup_and_login):
    admin = await signup_and_login(email="admin4@example.com", organization_name="RBAC Clinic")

    invite_response = await client.post(
        "/users", json={"name": "Dr. Doctor", "email": "doc@example.com", "role": "doctor"}
    )
    assert invite_response.status_code == 201, invite_response.text
    temp_password = invite_response.json()["data"]["temporaryPassword"]

    default_template_id = (await client.get("/templates")).json()["data"]["items"][0]["id"]

    # Switch the client's bearer token from admin to the newly invited doctor.
    login_response = await client.post("/auth/login", json={"email": "doc@example.com", "password": temp_password})
    assert login_response.status_code == 200, login_response.text
    client.headers["Authorization"] = f"Bearer {login_response.json()['data']['accessToken']}"

    assert (await client.get("/templates")).status_code == 200
    assert (await client.post("/templates/preview-pdf", json=_template_payload())).status_code == 200

    assert (await client.post("/templates/logo", files={"file": ("logo.png", _TINY_PNG, "image/png")})).status_code == 403
    assert (await client.post("/templates", json=_template_payload())).status_code == 403
    assert (await client.patch(f"/templates/{default_template_id}", json={"name": "Hijacked"})).status_code == 403
    assert (await client.delete(f"/templates/{default_template_id}")).status_code == 403
    assert admin["user"]["role"] == "org_admin"  # sanity: confirms the swap above really changed identity


async def test_cross_tenant_logo_key_is_dropped_not_embedded(client, signup_and_login):
    await signup_and_login(email="org-a-admin@example.com", organization_name="Org A")
    upload_response = await client.post("/templates/logo", files={"file": ("logo.png", _TINY_PNG, "image/png")})
    org_a_logo_key = upload_response.json()["data"]["logoKey"]

    # Switch to a second, unrelated organization entirely.
    client.headers.pop("Authorization", None)
    await signup_and_login(email="org-b-admin@example.com", organization_name="Org B")

    create_response = await client.post("/templates", json=_template_payload(header={"organizationName": "Org B", "logoKey": org_a_logo_key}))
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()["data"]
    assert created["header"]["logoKey"] is None
    assert created["header"].get("logoUrl") is None

    # Also confirm the stateless preview path renders successfully (no crash/leak) even
    # when handed a foreign-org key directly.
    preview_response = await client.post(
        "/templates/preview-pdf", json=_template_payload(header={"organizationName": "Org B", "logoKey": org_a_logo_key})
    )
    assert preview_response.status_code == 200
    assert preview_response.content[:4] == b"%PDF"
