"""Exercises `POST /studies/intake` (CONTRACTS.md §9, `app/api/studies/README.md`) — the
combined patient+study+upload+analysis flow that replaces the old client-side chain of four
separate calls. See `StudyService.create_from_intake`.
"""

_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c6360000002000155007ea56e4e0000000049454e44ae426082"
)


async def test_intake_creates_patient_study_file_and_draft_report(client, signup_and_login):
    await signup_and_login(email="intake-doctor@example.com", organization_name="Intake Clinic")

    response = await client.post(
        "/studies/intake",
        data={
            "modality": "x_ray",
            "bodyPart": "Chest",
            "studyDate": "2026-08-01",
            "clinicalHistory": "Shortness of breath.",
            "patientMrn": "MRN-INTAKE-1",
            "patientName": "Riley Intake",
            "patientDateOfBirth": "1990-01-01",
            "patientSex": "other",
            "runAnalysis": "true",
        },
        files={"file": ("chest.png", _TINY_PNG, "image/png")},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]

    study = data["study"]
    assert study["bodyPart"] == "Chest"
    assert len(study["files"]) == 1
    assert study["files"][0]["fileName"] == "chest.png"

    assert data["analysisJobId"]
    report = data["report"]
    assert report is not None
    assert report["status"] == "ai_generated"

    # The new patient must actually have been persisted (not just referenced in-memory).
    patients = await client.get("/patients", params={"search": "MRN-INTAKE-1"})
    assert patients.json()["data"]["total"] == 1


async def test_intake_with_existing_patient_and_no_analysis(client, signup_and_login):
    await signup_and_login(email="intake-doctor2@example.com", organization_name="Intake Clinic 2")

    patient_response = await client.post(
        "/patients", json={"mrn": "MRN-INTAKE-2", "name": "Morgan Existing", "dateOfBirth": "1985-05-05", "sex": "female"}
    )
    patient_id = patient_response.json()["data"]["id"]

    response = await client.post(
        "/studies/intake",
        data={
            "modality": "ct",
            "bodyPart": "Abdomen",
            "studyDate": "2026-08-02",
            "patientId": patient_id,
            "runAnalysis": "false",
        },
        files={"file": ("scan.png", _TINY_PNG, "image/png")},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["study"]["patientId"] == patient_id
    assert data["report"] is None
    assert data["analysisJobId"] is None


async def test_intake_requires_patient_id_or_new_patient_fields(client, signup_and_login):
    await signup_and_login(email="intake-doctor3@example.com", organization_name="Intake Clinic 3")

    response = await client.post(
        "/studies/intake",
        data={"modality": "x_ray", "bodyPart": "Chest", "studyDate": "2026-08-01"},
        files={"file": ("chest.png", _TINY_PNG, "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PATIENT_INFO_REQUIRED"


async def test_new_patient_is_created_with_only_an_age(client, signup_and_login):
    """The app sends `patientAge` (no date of birth); the age is stored as entered and is
    what the report PDF and AI context use."""
    await signup_and_login(email="intake-age@example.com", organization_name="Intake Age Clinic")

    response = await client.post(
        "/studies/intake",
        data={
            "modality": "ct",
            "bodyPart": "Brain",
            "studyDate": "2026-10-20",
            "patientName": "Age Only",
            "patientAge": "58",
            "patientSex": "male",
            "runAnalysis": "false",
        },
        files={"file": ("brain.png", _TINY_PNG, "image/png")},
    )

    assert response.status_code == 201, response.text
    patient_id = response.json()["data"]["study"]["patientId"]
    patient = (await client.get(f"/patients/{patient_id}")).json()["data"]
    assert patient["age"] == 58
    assert patient["dateOfBirth"] == ""


async def test_patient_age_is_editable_and_validated(client, signup_and_login):
    await signup_and_login(email="patient-age@example.com", organization_name="Patient Age Clinic")

    created = await client.post("/patients", json={"name": "Edit Age", "age": 40, "sex": "female"})
    assert created.status_code == 201, created.text
    patient_id = created.json()["data"]["id"]

    updated = await client.patch(f"/patients/{patient_id}", json={"age": 41})
    assert updated.json()["data"]["age"] == 41

    assert (await client.post("/patients", json={"name": "No Age", "sex": "male"})).status_code == 422
    assert (await client.post("/patients", json={"name": "Bad Age", "age": -1, "sex": "male"})).status_code == 422


def test_patient_age_prefers_the_entered_age_over_an_old_date_of_birth():
    from datetime import date

    from app.utils.patient_age import patient_age

    assert patient_age({"age": 58, "dateOfBirth": ""}) == 58
    assert patient_age({"dateOfBirth": f"{date.today().year - 30}-01-01"}) in (29, 30)
    assert patient_age({"dateOfBirth": ""}) is None
    assert patient_age(None) is None
