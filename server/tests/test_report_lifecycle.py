"""Exercises the core clinical workflow end to end: patient -> study -> AI analysis ->
report -> doctor edit (new version) -> finalize (immutable) -> PDF download. This is the
one test that would have caught the reports/uploads domains being missing entirely, and
is the main defense against the "report.study isn't actually embedded" mismatch between
the independently-built frontend and backend halves (CONTRACTS.md §1a/§12).

`AnalysisService.run_analysis` is called directly rather than through the
`POST /analysis/studies/{id}/analyze` HTTP route for a simpler reason than it used to be:
that route's response is just `{jobId}`, not the report itself, so going through it would
mean an extra `GET /reports?patientId=...` query just to find the report this test wants
to assert on. (The route runs this exact call inline now anyway — Redis/ARQ were removed,
see CLAUDE.md — so calling the service directly isn't working around anything async
either; it's purely a "the HTTP response shape doesn't hand back what this test needs"
shortcut.)
"""

from app.ai.base import GeneratedContent, ReportSectionContent
from app.services.analysis_service import AnalysisService


class _FakeReportProvider:
    """Duck-typed test double — only the two methods AnalysisService.run_analysis
    actually calls need to exist. Used to prove summarize_findings() genuinely runs as
    its own step BEFORE generate(), and that its result wins over whatever generate()
    independently drafted for GeneratedContent.summary (see
    app/services/analysis_service.py's `generated.summary = clinical_summary` line)."""

    async def summarize_findings(self, organization_name, context, findings, high_accuracy_mode=False):
        return "SENTINEL: distilled clinical summary"

    async def generate(self, organization_name, sections, context, findings, high_accuracy_mode):
        return GeneratedContent(
            summary="this should be overwritten by summarize_findings' result",
            sections=[ReportSectionContent(key=s.key, title=s.title, content="body") for s in sections],
            impression="impression text",
            recommendations="recommendations text",
            model_used="fake-model",
        )


async def test_summary_generated_before_report_and_used_verbatim(client, db, signup_and_login, monkeypatch):
    """New pre-report summary step: summarize_findings() must run before generate(), and
    the report's persisted summary must be exactly what it returned — not a second,
    independently-drafted guess from generate() itself."""
    await signup_and_login(email="doctor2@example.com", organization_name="Summary Test Clinic")

    patient_response = await client.post(
        "/patients", json={"mrn": "MRN-200", "name": "Sam Summary", "dateOfBirth": "1990-01-01", "sex": "other"}
    )
    patient_id = patient_response.json()["data"]["id"]
    study_response = await client.post(
        "/studies", json={"patientId": patient_id, "modality": "x_ray", "bodyPart": "Chest", "studyDate": "2026-08-01"}
    )
    study_id = study_response.json()["data"]["id"]
    organization_id = (await client.get("/organizations/me")).json()["data"]["organization"]["id"]

    monkeypatch.setattr("app.services.analysis_service.get_report_provider", lambda: _FakeReportProvider())

    report = await AnalysisService(db).run_analysis(study_id, organization_id)

    assert report["versions"][0]["content"]["summary"] == "SENTINEL: distilled clinical summary"


async def test_full_report_lifecycle(client, db, signup_and_login):
    await signup_and_login(email="doctor@example.com", organization_name="Riverside Imaging")

    patient_response = await client.post(
        "/patients",
        json={"mrn": "MRN-100", "name": "Jordan Rivera", "dateOfBirth": "1985-06-15", "sex": "male"},
    )
    assert patient_response.status_code == 201, patient_response.text
    patient_id = patient_response.json()["data"]["id"]

    study_response = await client.post(
        "/studies",
        json={
            "patientId": patient_id,
            "modality": "x_ray",
            "bodyPart": "Chest",
            "clinicalHistory": "Persistent cough for two weeks.",
            "studyDate": "2026-08-01",
        },
    )
    assert study_response.status_code == 201, study_response.text
    study = study_response.json()["data"]
    assert study["status"] == "uploaded"
    org_me_response = await client.get("/organizations/me")
    organization_id = org_me_response.json()["data"]["organization"]["id"]

    # Run the AI pipeline directly (see module docstring for why not via the HTTP route).
    report = await AnalysisService(db).run_analysis(study["id"], organization_id)
    assert report["status"] == "ai_generated"
    assert report["currentVersion"] == 1
    assert report["versions"][0]["author"] == "ai"

    report_id = report["id"]

    # GET must embed study (with nested patient) — this is what ReportCard/ReportViewer
    # on the frontend directly render off of.
    get_response = await client.get(f"/reports/{report_id}")
    assert get_response.status_code == 200
    fetched = get_response.json()["data"]
    assert fetched["study"]["id"] == study["id"]
    assert fetched["study"]["patient"]["name"] == "Jordan Rivera"

    # The underlying study must have flipped to completed and recorded findings.
    study_after = (await client.get(f"/studies/{study['id']}")).json()["data"]
    assert study_after["status"] == "completed"
    assert study_after["lastFindings"] is not None

    # Doctor manually edits the impression -> a new version is appended, never overwritten.
    edit_response = await client.patch(f"/reports/{report_id}", json={"impression": "Reviewed and confirmed by Dr. Rivera."})
    assert edit_response.status_code == 200
    edited = edit_response.json()["data"]
    assert edited["currentVersion"] == 2
    assert edited["status"] == "doctor_modified"
    assert len(edited["versions"]) == 2
    assert edited["versions"][0]["content"]["impression"] != "Reviewed and confirmed by Dr. Rivera."

    # Finalize -> immutable from here on.
    finalize_response = await client.post(f"/reports/{report_id}/finalize")
    assert finalize_response.status_code == 200
    finalized = finalize_response.json()["data"]
    assert finalized["status"] == "finalized"
    assert finalized["finalizedBy"]

    second_finalize = await client.post(f"/reports/{report_id}/finalize")
    assert second_finalize.status_code == 409

    edit_after_finalize = await client.patch(f"/reports/{report_id}", json={"summary": "should be rejected"})
    assert edit_after_finalize.status_code == 409

    pdf_response = await client.get(f"/reports/{report_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content[:4] == b"%PDF"


async def test_technician_role_no_longer_accepted(client, signup_and_login):
    """The `technician` role was removed (org_admin/doctor only now) — inviting one should
    be rejected at request validation, not silently accepted."""
    await signup_and_login(email="admin@example.com", organization_name="Role RBAC Clinic")

    invite_response = await client.post(
        "/users", json={"name": "Tina Tech", "email": "tina@example.com", "role": "technician"}
    )
    assert invite_response.status_code == 422


async def test_trial_expired_blocks_new_analysis(client, db, signup_and_login):
    """Once `trialEndsAt` has passed with no active subscription, `POST .../analyze` is
    blocked (402) before it ever enqueues a job — see `app/core/subscription.py`."""
    from datetime import datetime, timedelta, timezone

    from app.repositories.organization_repository import OrganizationRepository

    login_data = await signup_and_login(email="doctor3@example.com", organization_name="Expired Trial Clinic")
    organization_id = login_data["organization"]["id"]

    patient_response = await client.post(
        "/patients", json={"mrn": "MRN-300", "name": "Alex Expired", "dateOfBirth": "1990-01-01", "sex": "other"}
    )
    patient_id = patient_response.json()["data"]["id"]
    study_response = await client.post(
        "/studies",
        json={"patientId": patient_id, "modality": "x_ray", "bodyPart": "Chest", "studyDate": "2026-08-01"},
    )
    study_id = study_response.json()["data"]["id"]

    # Force the trial into the past, as if it had already expired with no payment.
    await OrganizationRepository(db).update(
        organization_id, {"trialEndsAt": datetime.now(timezone.utc) - timedelta(days=1)}
    )

    analyze_response = await client.post(f"/analysis/studies/{study_id}/analyze")
    assert analyze_response.status_code == 402
    assert analyze_response.json()["error"]["code"] == "TRIAL_EXPIRED"


async def test_trial_daily_report_limit_blocks_further_analysis(client, db, signup_and_login):
    """While still trialing, one more report attempt on the same UTC day is blocked (402)
    once `settings.trial_daily_report_limit` reports already exist for the org today."""
    from app.core.config import settings
    from app.repositories.report_repository import ReportRepository

    login_data = await signup_and_login(email="doctor4@example.com", organization_name="Busy Trial Clinic")
    organization_id = login_data["organization"]["id"]

    patient_response = await client.post(
        "/patients", json={"mrn": "MRN-400", "name": "Casey Busy", "dateOfBirth": "1990-01-01", "sex": "other"}
    )
    patient_id = patient_response.json()["data"]["id"]
    study_response = await client.post(
        "/studies",
        json={"patientId": patient_id, "modality": "x_ray", "bodyPart": "Chest", "studyDate": "2026-08-01"},
    )
    study_id = study_response.json()["data"]["id"]

    # Simulate the trial cap's worth of reports already generated today for this org.
    reports = ReportRepository(db)
    for _ in range(settings.trial_daily_report_limit):
        await reports.insert(
            {
                "organizationId": organization_id,
                "studyId": study_id,
                "templateId": None,
                "versions": [],
                "currentVersion": 1,
                "status": "ai_generated",
                "finalizedBy": None,
                "finalizedAt": None,
            }
        )

    analyze_response = await client.post(f"/analysis/studies/{study_id}/analyze")
    assert analyze_response.status_code == 402
    assert analyze_response.json()["error"]["code"] == "TRIAL_DAILY_LIMIT_REACHED"
