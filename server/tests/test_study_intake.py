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
