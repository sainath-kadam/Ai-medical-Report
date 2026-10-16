"""Background AI analysis (`settings.analysis_in_background`, on in production): intake and
analyze return the job id at once and the analysis finishes on its own DB session; the
job row carries progress/failure for the frontend to poll; a restart's leftovers are
failed at startup (`fail_interrupted_analyses`).

The background run is held behind an event until the request has returned: the test
database shares one SQLite connection between sessions, so a background write landing
mid-request would be rolled back with the request's session (Postgres gives each session
its own connection, so production has no such ordering concern).
"""

from __future__ import annotations

import asyncio

import pytest

import app.services.analysis_service as analysis_service
from app.core.background import wait_for_background_jobs
from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories.analysis_job_repository import AnalysisJobRepository
from app.services.analysis_service import fail_interrupted_analyses

_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c6360000002000155007ea56e4e0000000049454e44ae426082"
)

_INTAKE = {
    "modality": "x_ray",
    "bodyPart": "Chest",
    "studyDate": "2026-09-01",
    "patientName": "Bg Patient",
    "patientDateOfBirth": "1980-01-01",
    "patientSex": "female",
    "runAnalysis": "true",
}


@pytest.fixture
def background(monkeypatch):
    """Background mode on, with the run held until `release` is set."""
    monkeypatch.setattr(settings, "analysis_in_background", True)
    release = asyncio.Event()
    real = analysis_service._run_analysis_in_background

    async def _held(*args, **kwargs):
        await release.wait()
        await real(*args, **kwargs)

    monkeypatch.setattr(analysis_service, "_run_analysis_in_background", _held)
    return release


async def _job(client, job_id: str) -> dict:
    return (await client.get(f"/analysis/jobs/{job_id}")).json()["data"]


async def test_intake_returns_before_the_ai_runs_then_the_job_completes(client, signup_and_login, background):
    await signup_and_login(email="bg-intake@example.com", organization_name="Bg Intake")

    response = await client.post("/studies/intake", data=_INTAKE, files={"file": ("chest.png", _TINY_PNG, "image/png")})

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["report"] is None  # not waited for
    job_id = data["analysisJobId"]
    assert (await _job(client, job_id))["status"] == "queued"

    background.set()
    await wait_for_background_jobs()

    job = await _job(client, job_id)
    assert job["status"] == "completed"
    reports = (await client.get("/reports", params={"pageSize": 50})).json()["data"]["items"]
    assert [r["studyId"] for r in reports] == [data["study"]["id"]]
    assert reports[0]["status"] == "ai_generated"


async def test_reanalyze_returns_a_job_id_immediately(client, signup_and_login, background):
    await signup_and_login(email="bg-rerun@example.com", organization_name="Bg Rerun")
    created = (
        await client.post("/studies/intake", data={**_INTAKE, "runAnalysis": "false"}, files={"file": ("c.png", _TINY_PNG, "image/png")})
    ).json()["data"]
    study_id = created["study"]["id"]

    response = await client.post(f"/analysis/studies/{study_id}/analyze")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["report"] is None
    job_id = response.json()["data"]["jobId"]

    # A second click while it's still running is refused, not run twice.
    again = await client.post(f"/analysis/studies/{study_id}/analyze")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ANALYSIS_ALREADY_IN_PROGRESS"

    background.set()
    await wait_for_background_jobs()
    assert (await _job(client, job_id))["status"] == "completed"


async def test_background_failure_is_recorded_on_the_job(client, signup_and_login, background, monkeypatch):
    class _Down:
        async def analyze(self, context, high_accuracy_mode):
            raise AppError("The AI model is temporarily overloaded.", 503, "AI_TEMPORARILY_UNAVAILABLE")

    monkeypatch.setattr(analysis_service, "get_imaging_provider", lambda: _Down())
    await signup_and_login(email="bg-fail@example.com", organization_name="Bg Fail")

    data = (
        await client.post("/studies/intake", data=_INTAKE, files={"file": ("c.png", _TINY_PNG, "image/png")})
    ).json()["data"]
    background.set()
    await wait_for_background_jobs()

    job = await _job(client, data["analysisJobId"])
    assert job["status"] == "failed"
    assert job["errorCode"] == "AI_TEMPORARILY_UNAVAILABLE"
    assert "overloaded" in job["error"]


async def test_jobs_interrupted_by_a_restart_are_failed_and_can_be_rerun(client, signup_and_login, db):
    await signup_and_login(email="bg-restart@example.com", organization_name="Bg Restart")
    created = (
        await client.post("/studies/intake", data={**_INTAKE, "runAnalysis": "false"}, files={"file": ("c.png", _TINY_PNG, "image/png")})
    ).json()["data"]
    study = created["study"]
    organization_id = (await client.get("/auth/me")).json()["data"]["organization"]["id"]
    # A job the previous process was still running when it stopped.
    stuck = await AnalysisJobRepository(db).insert(
        {"organizationId": organization_id, "studyId": study["id"], "status": "analyzing", "provider": "mock"}
    )

    assert await fail_interrupted_analyses(db) == 1

    job = await _job(client, stuck["_id"])
    assert job["status"] == "failed"
    assert job["errorCode"] == "ANALYSIS_INTERRUPTED"
    # No longer "in progress", so the study can be analyzed again (inline mode here).
    rerun = await client.post(f"/analysis/studies/{study['id']}/analyze")
    assert rerun.status_code == 200
    assert rerun.json()["data"]["report"]["status"] == "ai_generated"


def test_background_mode_is_the_default():
    from app.core.config import Settings

    assert Settings.model_fields["analysis_in_background"].default is True
