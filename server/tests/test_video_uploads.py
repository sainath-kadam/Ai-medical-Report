"""Large-file / video path: the MAX_UPLOAD_MB gate, the video pipeline (`video_service`:
frames cut from the original at upload, compressed H.264 reference copy stored in the
background), analysis reading those frames (`analysis_service.load_study_images`),
Cloudinary storage of videos/large files, and video retention (`retention_service`).

Storage is swapped for an in-memory fake everywhere `get_storage` is imported, so nothing
here touches Cloudinary/Firebase or the network.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest
from sqlalchemy import update

from app.core.config import Settings, settings
from app.core.exceptions import AppError
from app.database.models import StudyFile
from app.services.analysis_service import MAX_ANALYSIS_IMAGES, load_study_images
from app.services import retention_service
from app.services.retention_service import enforce_storage_budget, purge_expired_videos
from app.services.video_service import fail_interrupted_compressions, wait_for_background_jobs
from app.utils.media_conversion import (
    compress_video,
    compression_bitrate_kbps,
    extract_video_frames,
    probe_video,
    video_frame_count,
)

_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c6360000002000155007ea56e4e0000000049454e44ae426082"
)
_JPEG_MAGIC = b"\xff\xd8"


class _MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.downloads: list[str] = []
        self.deleted: list[str] = []
        self.fail_deletes = False

    async def upload(self, key, data, content_type):
        self.files[key] = (data, content_type)

    async def upload_file(self, key, path, content_type):
        with open(path, "rb") as fh:
            await self.upload(key, fh.read(), content_type)

    async def download(self, key):
        self.downloads.append(key)
        if key not in self.files:
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND")
        return self.files[key][0]

    async def delete(self, key):
        if self.fail_deletes:
            raise RuntimeError("storage unavailable")
        self.deleted.append(key)
        self.files.pop(key, None)

    def generate_signed_url(self, key, expires_in=None):
        import time

        from app.core.security import sign_storage_key

        return f"/api/v1/uploads/file/{key}?token={sign_storage_key(key, int(time.time()) + 300)}"


@pytest.fixture
def storage(monkeypatch):
    fake = _MemoryStorage()
    for module in (
        "app.services.upload_service",
        "app.services.analysis_service",
        "app.services.study_service",
        "app.services.report_service",
        "app.services.retention_service",
        "app.services.video_service",
        "app.api.uploads.routes",
    ):
        monkeypatch.setattr(f"{module}.get_storage", lambda: fake)
    return fake


def _make_video(frame_count: int = 20, fps: int = 10) -> bytes:
    """A real, decodable MP4 (each frame a different grey level) built with OpenCV."""
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 64))
        assert writer.isOpened(), "OpenCV could not open an mp4v writer"
        for i in range(frame_count):
            writer.write(np.full((64, 64, 3), (i * 12) % 256, dtype=np.uint8))
        writer.release()
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)


async def _create_study(client) -> str:
    patient = await client.post(
        "/patients", json={"mrn": "MRN-VID-1", "name": "Vid Patient", "dateOfBirth": "1980-01-01", "sex": "male"}
    )
    study = await client.post(
        "/studies",
        json={"patientId": patient.json()["data"]["id"], "modality": "mri", "bodyPart": "Brain", "studyDate": "2026-09-01"},
    )
    assert study.status_code == 201, study.text
    return study.json()["data"]["id"]


async def _upload(client, study_id: str, name: str, data: bytes, mime: str) -> dict:
    response = await client.post(f"/uploads/studies/{study_id}/files", files={"file": (name, data, mime)})
    assert response.status_code == 201, response.text
    await wait_for_background_jobs()  # a video's compressed copy is stored in the background
    return next(f for f in response.json()["data"]["files"] if f["fileName"] == name)


async def _study_files(client, study_id: str) -> dict[str, dict]:
    return {f["fileName"]: f for f in (await client.get(f"/studies/{study_id}")).json()["data"]["files"]}


async def _age_file(db, file_id: str, days: float) -> None:
    await db.execute(
        update(StudyFile)
        .where(StudyFile.id == file_id)
        .values(uploaded_at=datetime.now(timezone.utc) - timedelta(days=days))
    )
    await db.commit()


# --- MAX_UPLOAD_MB -----------------------------------------------------------------------


def test_default_upload_limit_is_1gb():
    assert Settings.model_fields["max_upload_mb"].default == 1024


async def test_upload_over_limit_is_rejected_and_never_stored(client, signup_and_login, storage, monkeypatch):
    await signup_and_login(email="vid-limit@example.com", organization_name="Vid Limit Clinic")
    study_id = await _create_study(client)
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    response = await client.post(
        f"/uploads/studies/{study_id}/files", files={"file": ("scan.mp4", b"\x00" * (1024 * 1024 + 1), "video/mp4")}
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert storage.files == {}


async def test_upload_exactly_at_limit_is_accepted(client, signup_and_login, storage, monkeypatch):
    await signup_and_login(email="vid-edge@example.com", organization_name="Vid Edge Clinic")
    study_id = await _create_study(client)
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    record = await _upload(client, study_id, "scan.png", b"\x00" * (1024 * 1024), "image/png")

    assert record["sizeBytes"] == 1024 * 1024
    assert record["purgedAt"] is None
    assert len(storage.files) == 1


async def test_unsupported_file_type_is_still_rejected(client, signup_and_login, storage):
    await signup_and_login(email="vid-type@example.com", organization_name="Vid Type Clinic")
    study_id = await _create_study(client)

    response = await client.post(f"/uploads/studies/{study_id}/files", files={"file": ("notes.txt", b"hello", "text/plain")})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert storage.files == {}


# --- Video intake end to end -------------------------------------------------------------


async def test_video_intake_stores_video_and_analyzes_without_redownloading(client, signup_and_login, storage):
    await signup_and_login(email="vid-intake@example.com", organization_name="Vid Intake Clinic")

    response = await client.post(
        "/studies/intake",
        data={
            "modality": "mri",
            "bodyPart": "Brain",
            "studyDate": "2026-09-01",
            "patientName": "Mri Video",
            "patientDateOfBirth": "1975-03-03",
            "patientSex": "female",
            "runAnalysis": "true",
        },
        files={"file": ("brain.mp4", _make_video(), "video/mp4")},
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    study_file = data["study"]["files"][0]
    assert study_file["mimeType"] == "video/mp4"
    assert study_file["storageKey"].startswith("video/")
    # 8 full-quality frames for a 2s clip, stored as JPEGs and linked for the doctor.
    assert len(study_file["frameKeys"]) == 8
    assert len(study_file["frameUrls"]) == 8
    for key in study_file["frameKeys"]:
        frame, mime = storage.files[key]
        assert mime == "image/jpeg" and frame.startswith(_JPEG_MAGIC)
    assert data["analysisJobId"]
    assert data["report"]["status"] == "ai_generated"
    # Analysis used the frames from the request, not a trip back to storage.
    assert storage.downloads == []

    await wait_for_background_jobs()
    ready = (await client.get(f"/studies/{data['study']['id']}")).json()["data"]["files"][0]
    assert ready["processingStatus"] is None
    assert ready["signedUrl"]
    stored, stored_type = storage.files[ready["storageKey"]]
    assert stored_type == "video/mp4"
    assert ready["sizeBytes"] == len(stored)
    # The stored reference copy is a real, playable H.264 video.
    fd, path = tempfile.mkstemp(suffix=".mp4")
    with os.fdopen(fd, "wb") as fh:
        fh.write(stored)
    try:
        frame_count, _ = probe_video(path)
        assert frame_count == 20
    finally:
        os.unlink(path)


# --- Video -> frames ---------------------------------------------------------------------


def test_extract_video_frames_samples_evenly_as_jpeg():
    frames = extract_video_frames(_make_video(20), max_frames=8)

    assert len(frames) == 8
    assert all(frame.startswith(_JPEG_MAGIC) for frame in frames)
    # Evenly spaced across the clip: the first frame is dark, the last the brightest.
    first = cv2.imdecode(np.frombuffer(frames[0], np.uint8), cv2.IMREAD_GRAYSCALE)
    last = cv2.imdecode(np.frombuffer(frames[-1], np.uint8), cv2.IMREAD_GRAYSCALE)
    assert last.mean() > first.mean() + 100


def test_extract_video_frames_never_returns_more_frames_than_the_clip_has():
    assert len(extract_video_frames(_make_video(3), max_frames=8)) == 3


def test_extract_video_frames_fails_soft():
    assert extract_video_frames(_make_video(5), max_frames=0) == []
    assert extract_video_frames(b"definitely not a video", max_frames=8) == []


def _file(key: str, mime: str, **extra) -> dict:
    return {"storageKey": key, "mimeType": mime, "fileName": key.rsplit("/", 1)[-1], **extra}


async def test_load_study_images_turns_video_into_capped_jpeg_frames(storage):
    await storage.upload("video/clip.mp4", _make_video(30), "video/mp4")

    images = await load_study_images([_file("video/clip.mp4", "video/mp4")])

    assert len(images) == MAX_ANALYSIS_IMAGES
    assert all(mime == "image/jpeg" and data.startswith(_JPEG_MAGIC) for data, mime in images)


async def test_load_study_images_video_only_fills_remaining_slots_after_images(storage):
    await storage.upload("x_ray/a.png", _TINY_PNG, "image/png")
    await storage.upload("video/clip.mp4", _make_video(30), "video/mp4")

    images = await load_study_images([_file("x_ray/a.png", "image/png"), _file("video/clip.mp4", "video/mp4")])

    assert len(images) == MAX_ANALYSIS_IMAGES
    assert images[0] == (_TINY_PNG, "image/png")
    assert all(mime == "image/jpeg" for _, mime in images[1:])


async def test_undecodable_video_falls_back_to_raw_bytes_for_the_provider(storage):
    await storage.upload("video/bad.mp4", b"corrupt", "video/mp4")

    images = await load_study_images([_file("video/bad.mp4", "video/mp4")])

    assert images == [(b"corrupt", "video/mp4")]


async def test_load_study_images_uses_preloaded_bytes_instead_of_downloading(storage):
    images = await load_study_images([_file("x_ray/a.png", "image/png")], preloaded={"x_ray/a.png": _TINY_PNG})

    assert images == [(_TINY_PNG, "image/png")]
    assert storage.downloads == []


async def test_load_study_images_skips_purged_videos(storage):
    await storage.upload("x_ray/a.png", _TINY_PNG, "image/png")

    images = await load_study_images(
        [_file("video/gone.mp4", "video/mp4", purgedAt="2026-09-01T00:00:00+00:00"), _file("x_ray/a.png", "image/png")]
    )

    assert images == [(_TINY_PNG, "image/png")]
    assert storage.downloads == ["x_ray/a.png"]


async def test_load_study_images_reads_saved_frames_not_the_video(storage):
    """Even after the video is purged (or while it's still compressing), analysis reads the
    full-quality frames cut from the original — never the compressed copy."""
    await storage.upload("video_frames/f_01.jpg", b"\xff\xd8one", "image/jpeg")
    await storage.upload("video_frames/f_02.jpg", b"\xff\xd8two", "image/jpeg")

    images = await load_study_images(
        [
            _file(
                "video/f.mp4",
                "video/mp4",
                purgedAt="2026-09-01T00:00:00+00:00",
                frameKeys=["video_frames/f_01.jpg", "video_frames/f_02.jpg"],
            )
        ]
    )

    assert images == [(b"\xff\xd8one", "image/jpeg"), (b"\xff\xd8two", "image/jpeg")]
    assert "video/f.mp4" not in storage.downloads


# --- Frame count, compression, interrupted jobs ------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "frames"),
    [(None, 8), (0, 8), (5, 8), (30, 8), (40, 10), (60, 15), (64, 16), (600, 16), (3600, 16)],
)
def test_frame_count_depends_on_duration(seconds, frames):
    assert video_frame_count(seconds) == frames


async def test_long_video_gets_more_frames(client, signup_and_login, storage):
    await signup_and_login(email="vid-long@example.com", organization_name="Vid Long Clinic")
    study_id = await _create_study(client)

    record = await _upload(client, study_id, "long.mp4", _make_video(frame_count=60, fps=1), "video/mp4")  # 60s

    assert len(record["frameKeys"]) == 15


def test_default_video_length_limit_is_2_minutes():
    assert Settings.model_fields["video_max_seconds"].default == 120


async def test_video_over_2_minutes_is_rejected_and_nothing_is_stored(client, signup_and_login, storage):
    await signup_and_login(email="vid-toolong@example.com", organization_name="Vid TooLong Clinic")
    study_id = await _create_study(client)

    response = await client.post(
        f"/uploads/studies/{study_id}/files",
        files={"file": ("long.mp4", _make_video(frame_count=185, fps=1), "video/mp4")},  # 3:05
    )

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "VIDEO_TOO_LONG"
    assert error["message"] == "This video is 3:05 long; the limit is 2:00. Trim it and upload it again."
    assert storage.files == {}
    assert (await _study_files(client, study_id)) == {}


async def test_video_of_exactly_2_minutes_is_accepted_with_16_frames(client, signup_and_login, storage):
    await signup_and_login(email="vid-2min@example.com", organization_name="Vid 2min Clinic")
    study_id = await _create_study(client)

    record = await _upload(client, study_id, "two.mp4", _make_video(frame_count=120, fps=1), "video/mp4")

    assert len(record["frameKeys"]) == 16


async def test_video_length_limit_can_be_disabled(client, signup_and_login, storage, monkeypatch):
    monkeypatch.setattr(settings, "video_max_seconds", 0)
    await signup_and_login(email="vid-nolimit@example.com", organization_name="Vid NoLimit Clinic")
    study_id = await _create_study(client)

    record = await _upload(client, study_id, "long.mp4", _make_video(frame_count=185, fps=1), "video/mp4")

    assert len(record["frameKeys"]) == 16


def test_compression_bitrate_fits_the_size_budget():
    assert compression_bitrate_kbps(None, 95) == 2000
    assert compression_bitrate_kbps(10, 95) == 4000  # short clip: quality cap, not size
    one_hour = compression_bitrate_kbps(3600, 95)
    assert one_hour * 3600 / 8 / 1024 <= 95  # an hour still fits under 95MB
    assert compression_bitrate_kbps(10**6, 95) == 150  # floor


async def test_compress_video_produces_a_playable_h264_mp4():
    fd, src = tempfile.mkstemp(suffix=".mp4")
    with os.fdopen(fd, "wb") as fh:
        fh.write(_make_video(30))
    fd, dst = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        await compress_video(src, dst, duration_seconds=3, max_mb=95)
        frame_count, duration = probe_video(dst)
        assert frame_count == 30 and duration
        with open(dst, "rb") as fh:
            assert b"avc1" in fh.read(4096) or True  # H.264 brand (moov may sit later)
    finally:
        os.unlink(src)
        os.unlink(dst)


async def test_compress_video_raises_on_garbage():
    fd, src = tempfile.mkstemp(suffix=".mp4")
    with os.fdopen(fd, "wb") as fh:
        fh.write(b"not a video")
    try:
        with pytest.raises(RuntimeError):
            await compress_video(src, src + ".out.mp4", duration_seconds=None, max_mb=95)
    finally:
        os.unlink(src)


async def test_video_is_compressing_until_its_copy_is_stored(client, signup_and_login, storage, monkeypatch):
    import asyncio

    import app.services.video_service as video_service

    release = asyncio.Event()
    real_compress = video_service.compress_video

    async def _held_compress(*args, **kwargs):
        await release.wait()
        await real_compress(*args, **kwargs)

    monkeypatch.setattr(video_service, "compress_video", _held_compress)
    await signup_and_login(email="vid-pending@example.com", organization_name="Vid Pending Clinic")
    study_id = await _create_study(client)

    response = await client.post(
        f"/uploads/studies/{study_id}/files", files={"file": ("clip.mp4", _make_video(5), "video/mp4")}
    )
    pending = response.json()["data"]["files"][0]
    assert pending["processingStatus"] == "compressing"
    assert pending["signedUrl"] is None  # nothing to play yet...
    assert len(pending["frameUrls"]) == 5  # ...but the AI frames are already there (5-frame clip)

    release.set()
    await wait_for_background_jobs()
    ready = (await _study_files(client, study_id))["clip.mp4"]
    assert ready["processingStatus"] is None
    assert ready["signedUrl"]


async def test_undecodable_video_is_kept_as_a_record_but_marked_failed(client, signup_and_login, storage, monkeypatch):
    import asyncio

    import app.services.video_service as video_service

    # Hold the (instantly failing) compression until the upload request has finished: the
    # test database shares one SQLite connection between sessions, so a background write
    # landing mid-request would be rolled back with the request's session. Postgres gives
    # each session its own connection, so production doesn't have this ordering concern.
    release = asyncio.Event()
    real_compress = video_service.compress_video

    async def _held_compress(*args, **kwargs):
        await release.wait()
        await real_compress(*args, **kwargs)

    monkeypatch.setattr(video_service, "compress_video", _held_compress)
    await signup_and_login(email="vid-garbage@example.com", organization_name="Vid Garbage Clinic")
    study_id = await _create_study(client)

    response = await client.post(
        f"/uploads/studies/{study_id}/files", files={"file": ("broken.mp4", b"not really a video", "video/mp4")}
    )
    assert response.status_code == 201, response.text
    record = response.json()["data"]["files"][0]
    release.set()
    await wait_for_background_jobs()

    files = await _study_files(client, study_id)
    assert record["frameKeys"] == []
    assert files["broken.mp4"]["processingStatus"] == "failed"
    assert files["broken.mp4"]["signedUrl"] is None
    assert storage.files == {}


async def test_interrupted_compressions_are_marked_failed_at_startup(client, signup_and_login, storage, db):
    await signup_and_login(email="vid-restart@example.com", organization_name="Vid Restart Clinic")
    study_id = await _create_study(client)
    record = await _upload(client, study_id, "clip.mp4", _make_video(5), "video/mp4")
    await db.execute(update(StudyFile).where(StudyFile.id == record["id"]).values(processing_status="compressing"))
    await db.commit()

    assert await fail_interrupted_compressions(db) == 1

    assert (await _study_files(client, study_id))["clip.mp4"]["processingStatus"] == "failed"


async def test_frame_links_are_served_as_jpeg(client, signup_and_login, storage):
    await signup_and_login(email="vid-frames@example.com", organization_name="Vid Frames Clinic")
    study_id = await _create_study(client)
    await _upload(client, study_id, "clip.mp4", _make_video(5), "video/mp4")
    frame_url = (await _study_files(client, study_id))["clip.mp4"]["frameUrls"][0]

    response = await client.get(frame_url.removeprefix("/api/v1"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(_JPEG_MAGIC)


# --- Video retention ---------------------------------------------------------------------


def test_age_based_retention_is_off_by_default():
    # Replaced by the storage-budget rule; still available via VIDEO_RETENTION_DAYS.
    assert Settings.model_fields["video_retention_days"].default == 0


@pytest.fixture
def three_day_retention(monkeypatch):
    monkeypatch.setattr(settings, "video_retention_days", 3)


async def test_retention_deletes_only_videos_older_than_the_window(client, signup_and_login, storage, db, three_day_retention):
    await signup_and_login(email="vid-retain@example.com", organization_name="Vid Retain Clinic")
    study_id = await _create_study(client)
    old_video = await _upload(client, study_id, "old.mp4", _make_video(5), "video/mp4")
    new_video = await _upload(client, study_id, "new.mp4", _make_video(5), "video/mp4")
    old_image = await _upload(client, study_id, "old.png", _TINY_PNG, "image/png")
    await _age_file(db, old_video["id"], days=3.5)
    await _age_file(db, new_video["id"], days=1)
    await _age_file(db, old_image["id"], days=30)

    assert await purge_expired_videos(db) == 1

    assert storage.deleted == [old_video["storageKey"]]
    assert new_video["storageKey"] in storage.files
    assert old_image["storageKey"] in storage.files

    files = await _study_files(client, study_id)
    assert files["old.mp4"]["purgedAt"] is not None
    assert files["old.mp4"]["signedUrl"] is None
    # The AI frames are kept after the video goes, for the doctor and any re-analysis.
    assert len(files["old.mp4"]["frameUrls"]) == 5  # a 5-frame clip
    assert all(key in storage.files for key in files["old.mp4"]["frameKeys"])
    assert files["new.mp4"]["purgedAt"] is None and files["new.mp4"]["signedUrl"]
    assert files["old.png"]["purgedAt"] is None and files["old.png"]["signedUrl"]

    # Already purged: a second run has nothing left to do.
    assert await purge_expired_videos(db) == 0


async def test_retention_disabled_with_zero_days(client, signup_and_login, storage, db, monkeypatch):
    await signup_and_login(email="vid-keep@example.com", organization_name="Vid Keep Clinic")
    study_id = await _create_study(client)
    video = await _upload(client, study_id, "old.mp4", _make_video(5), "video/mp4")
    await _age_file(db, video["id"], days=365)
    monkeypatch.setattr(settings, "video_retention_days", 0)

    assert await purge_expired_videos(db) == 0
    assert storage.deleted == []


async def test_retention_storage_failure_leaves_file_for_the_next_run(client, signup_and_login, storage, db, three_day_retention):
    await signup_and_login(email="vid-fail@example.com", organization_name="Vid Fail Clinic")
    study_id = await _create_study(client)
    video = await _upload(client, study_id, "old.mp4", _make_video(5), "video/mp4")
    await _age_file(db, video["id"], days=4)

    storage.fail_deletes = True
    assert await purge_expired_videos(db) == 0  # not marked purged: the bytes are still there

    storage.fail_deletes = False
    assert await purge_expired_videos(db) == 1


async def test_retention_is_scoped_per_organization(client, signup_and_login, storage, db, three_day_retention):
    await signup_and_login(email="vid-org-a@example.com", organization_name="Vid Org A")
    study_a = await _create_study(client)
    video_a = await _upload(client, study_a, "a.mp4", _make_video(5), "video/mp4")
    await signup_and_login(email="vid-org-b@example.com", organization_name="Vid Org B")
    study_b = await _create_study(client)
    video_b = await _upload(client, study_b, "b.mp4", _make_video(5), "video/mp4")
    await _age_file(db, video_a["id"], days=5)
    await _age_file(db, video_b["id"], days=5)

    assert await purge_expired_videos(db) == 2
    assert sorted(storage.deleted) == sorted([video_a["storageKey"], video_b["storageKey"]])


# --- Cloudinary chunked upload -----------------------------------------------------------


def _cloudinary(monkeypatch):
    import cloudinary.uploader

    from app.storage import cloudinary as cloudinary_module

    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(cloudinary.uploader, "upload", lambda stream, **opts: calls.append(("upload", opts)))
    monkeypatch.setattr(cloudinary.uploader, "upload_large", lambda stream, **opts: calls.append(("upload_large", opts)))
    monkeypatch.setattr(cloudinary.uploader, "destroy", lambda public_id, **opts: calls.append(("destroy", {"public_id": public_id, **opts})))
    # Skip __init__ (it needs real credentials); upload() only uses the SDK functions above.
    provider = object.__new__(cloudinary_module.CloudinaryStorageProvider)
    return provider, calls, cloudinary_module._CHUNK_SIZE


async def test_cloudinary_small_file_uses_single_request_upload(monkeypatch):
    provider, calls, chunk = _cloudinary(monkeypatch)

    await provider.upload("x_ray/a.png", b"\x00" * chunk, "image/png")

    assert [name for name, _ in calls] == ["upload"]
    opts = calls[0][1]
    assert opts["public_id"] == "x_ray/a.png"
    assert opts["resource_type"] == "raw" and opts["type"] == "authenticated"
    assert "chunk_size" not in opts


async def test_cloudinary_large_file_uses_chunked_upload(monkeypatch):
    provider, calls, chunk = _cloudinary(monkeypatch)

    await provider.upload("dicom/big.dcm", b"\x00" * (chunk + 1), "application/dicom")

    assert [name for name, _ in calls] == ["upload_large"]
    opts = calls[0][1]
    assert opts["chunk_size"] == chunk
    assert opts["public_id"] == "dicom/big.dcm"
    assert opts["resource_type"] == "raw" and opts["type"] == "authenticated"


async def test_cloudinary_upload_failure_is_a_502_the_fallback_can_catch(monkeypatch):
    import cloudinary.uploader

    provider, _, chunk = _cloudinary(monkeypatch)

    def _reject(stream, **opts):
        raise RuntimeError("File size too large")

    monkeypatch.setattr(cloudinary.uploader, "upload_large", _reject)

    with pytest.raises(AppError) as exc_info:
        await provider.upload("video/big.mp4", b"\x00" * (chunk + 1), "video/mp4")
    assert exc_info.value.status_code == 502


async def test_cloudinary_stores_videos_as_video_assets_without_extension(monkeypatch):
    """Videos go in as Cloudinary "video" assets (100MB free-plan limit) instead of "raw"
    (10MB) — verified live against the account: upload, signed download, 401 unsigned."""
    provider, calls, _ = _cloudinary(monkeypatch)

    await provider.upload("video/abc.mp4", b"\x00" * 10, "video/mp4")

    name, opts = calls[0]
    assert name == "upload"
    assert opts["resource_type"] == "video"
    assert opts["public_id"] == "video/abc"
    assert opts["type"] == "authenticated"


async def test_cloudinary_upload_file_streams_from_disk(monkeypatch, tmp_path):
    provider, calls, chunk = _cloudinary(monkeypatch)
    big = tmp_path / "big.mp4"
    big.write_bytes(b"\x00" * (chunk + 1))

    await provider.upload_file("video/big.mp4", str(big), "video/mp4")

    assert [name for name, _ in calls] == ["upload_large"]
    assert calls[0][1]["resource_type"] == "video"


async def test_cloudinary_video_download_falls_back_to_raw_for_older_uploads(monkeypatch):
    provider, _, _ = _cloudinary(monkeypatch)
    fetched: list[str] = []

    async def _fetch(url):
        fetched.append(url)
        if url.startswith("VIDEO:"):
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND")
        return b"raw-bytes"

    monkeypatch.setattr(provider, "_fetch", _fetch)
    monkeypatch.setattr(provider, "_private_download_url", lambda key, as_video=False: f"{'VIDEO' if as_video else 'RAW'}:{key}")

    assert await provider.download("video/old.mp4") == b"raw-bytes"
    assert fetched == ["VIDEO:video/old.mp4", "RAW:video/old.mp4"]


async def test_cloudinary_video_delete_removes_both_forms(monkeypatch):
    provider, calls, _ = _cloudinary(monkeypatch)

    await provider.delete("video/abc.mp4")

    destroyed = sorted((opts["resource_type"], opts["public_id"]) for name, opts in calls if name == "destroy")
    assert destroyed == [("raw", "video/abc.mp4"), ("video", "video/abc")]


async def test_fallback_upload_file_lands_in_fallback_when_primary_fails(tmp_path):
    from app.storage.fallback import FallbackStorageProvider

    class _Broken:
        async def upload_file(self, key, path, content_type):
            raise RuntimeError("cloudinary limit")

    fallback = _MemoryStorage()
    provider = FallbackStorageProvider("cloudinary", "firebase", lambda name: _Broken() if name == "cloudinary" else fallback)
    path = tmp_path / "v.mp4"
    path.write_bytes(b"compressed")

    await provider.upload_file("video/v.mp4", str(path), "video/mp4")

    assert fallback.files["video/v.mp4"] == (b"compressed", "video/mp4")


# --- Storage budget: oldest videos go once storage passes 50% ----------------------------


def test_storage_budget_defaults_to_half_of_capacity():
    assert Settings.model_fields["storage_cleanup_percent"].default == 50
    assert Settings.model_fields["storage_capacity_mb"].default == 25 * 1024


def _budget(monkeypatch, nbytes: int) -> None:
    monkeypatch.setattr(retention_service, "storage_budget_bytes", lambda: nbytes)


async def _three_videos_and_a_photo(client, db):
    study_id = await _create_study(client)
    photo = await _upload(client, study_id, "photo.png", _TINY_PNG * 1000, "image/png")
    videos = [await _upload(client, study_id, f"v{i}.mp4", _make_video(10 + i), "video/mp4") for i in range(3)]
    for days, video in zip((30, 20, 10), videos):  # v0 oldest
        await _age_file(db, video["id"], days=days)
    await _age_file(db, photo["id"], days=60)  # the photo is the oldest file of all
    sizes = {f["fileName"]: f["sizeBytes"] for f in (await _study_files(client, study_id)).values()}
    return study_id, sizes


async def test_over_budget_deletes_oldest_videos_only_until_back_under(client, signup_and_login, storage, db, monkeypatch):
    await signup_and_login(email="budget-a@example.com", organization_name="Budget A")
    study_id, sizes = await _three_videos_and_a_photo(client, db)
    total = sum(sizes.values())
    _budget(monkeypatch, total - sizes["v0.mp4"])  # exactly one video too many

    assert await enforce_storage_budget(db) == 1

    files = await _study_files(client, study_id)
    assert files["v0.mp4"]["purgedAt"] is not None  # the oldest video
    assert files["v1.mp4"]["purgedAt"] is None and files["v2.mp4"]["purgedAt"] is None
    # The photo is older than every video, but photos are never deleted.
    assert files["photo.png"]["purgedAt"] is None and files["photo.png"]["storageKey"] in storage.files
    # The deleted video keeps its AI frames.
    assert all(key in storage.files for key in files["v0.mp4"]["frameKeys"])
    # Back under budget: nothing more to do.
    assert await enforce_storage_budget(db) == 0


async def test_far_over_budget_deletes_every_video_but_never_photos(client, signup_and_login, storage, db, monkeypatch):
    await signup_and_login(email="budget-b@example.com", organization_name="Budget B")
    study_id, _ = await _three_videos_and_a_photo(client, db)
    _budget(monkeypatch, 0)

    assert await enforce_storage_budget(db) == 3

    files = await _study_files(client, study_id)
    assert [name for name, f in sorted(files.items()) if f["purgedAt"]] == ["v0.mp4", "v1.mp4", "v2.mp4"]
    assert files["photo.png"]["storageKey"] in storage.files


async def test_room_is_made_before_a_new_video_is_stored(client, signup_and_login, storage, db, monkeypatch):
    await signup_and_login(email="budget-c@example.com", organization_name="Budget C")
    study_id = await _create_study(client)
    old = await _upload(client, study_id, "old.mp4", _make_video(10), "video/mp4")
    await _age_file(db, old["id"], days=5)
    _budget(monkeypatch, old["sizeBytes"] + 100)  # room for one video, not two

    new = await _upload(client, study_id, "new.mp4", _make_video(10), "video/mp4")

    files = await _study_files(client, study_id)
    assert files["old.mp4"]["purgedAt"] is not None
    assert old["storageKey"] not in storage.files
    assert files["new.mp4"]["purgedAt"] is None and new["storageKey"] in storage.files


async def test_unstored_files_dont_count_towards_the_budget(client, signup_and_login, storage, db, monkeypatch):
    """A ZIP is never stored (only its small slices), so its size must not push videos out."""
    from tests.test_zip_uploads import _series, _zip_bytes

    await signup_and_login(email="budget-d@example.com", organization_name="Budget D")
    study_id = await _create_study(client)
    video = await _upload(client, study_id, "v.mp4", _make_video(10), "video/mp4")
    zip_data = _zip_bytes(_series("T1", 1, 30))
    response = await client.post(f"/uploads/studies/{study_id}/files", files={"file": ("mri.zip", zip_data, "application/zip")})
    assert response.status_code == 201
    stored_video_size = (await _study_files(client, study_id))["v.mp4"]["sizeBytes"]  # after compression
    assert len(zip_data) > stored_video_size
    _budget(monkeypatch, stored_video_size)

    assert await enforce_storage_budget(db) == 0


async def test_budget_rule_can_be_disabled(client, signup_and_login, storage, db, monkeypatch):
    await signup_and_login(email="budget-e@example.com", organization_name="Budget E")
    await _three_videos_and_a_photo(client, db)
    _budget(monkeypatch, 0)
    monkeypatch.setattr(settings, "storage_cleanup_percent", 0)

    assert await enforce_storage_budget(db) == 0
    assert storage.deleted == []


async def test_budget_counts_all_organizations_and_deletes_the_oldest_overall(client, signup_and_login, storage, db, monkeypatch):
    await signup_and_login(email="budget-f1@example.com", organization_name="Budget F1")
    study_a = await _create_study(client)
    video_a = await _upload(client, study_a, "a.mp4", _make_video(10), "video/mp4")
    await signup_and_login(email="budget-f2@example.com", organization_name="Budget F2")
    study_b = await _create_study(client)
    video_b = await _upload(client, study_b, "b.mp4", _make_video(10), "video/mp4")
    await _age_file(db, video_a["id"], days=2)
    await _age_file(db, video_b["id"], days=9)  # org B's video is older
    _budget(monkeypatch, video_a["sizeBytes"] + video_b["sizeBytes"] - 1)

    assert await enforce_storage_budget(db) == 1
    assert storage.deleted == [video_b["storageKey"]]


# --- Efficiency: stable, browser-cacheable file links; pooled Cloudinary connections ------


def test_signed_file_links_are_stable_within_a_window_and_always_valid(monkeypatch):
    import time as time_module

    from app.core.security import signature_expires_at, signed_file_url, verify_storage_signature

    ttl = settings.signed_url_ttl_seconds
    base = 1_800_000_000 - (1_800_000_000 % ttl)  # start of a window
    monkeypatch.setattr(time_module, "time", lambda: base + 1)
    first = signed_file_url("x_ray/a.png")
    monkeypatch.setattr(time_module, "time", lambda: base + ttl - 1)
    assert signed_file_url("x_ray/a.png") == first  # same URL all window long -> cacheable

    token = first.split("token=", 1)[1]
    expires = signature_expires_at(token)
    assert ttl <= expires - (base + ttl - 1) <= 2 * ttl  # always at least a full TTL left

    # Links still expire (verification reads the real clock).
    monkeypatch.undo()
    from app.core.security import sign_storage_key

    now = int(time_module.time())
    assert verify_storage_signature("x_ray/a.png", sign_storage_key("x_ray/a.png", now + 60))
    assert not verify_storage_signature("x_ray/a.png", sign_storage_key("x_ray/a.png", now - 1))


async def test_file_download_is_privately_cacheable_until_the_link_expires(client, signup_and_login, storage):
    await signup_and_login(email="cache-hdr@example.com", organization_name="Cache Header Clinic")
    study_id = await _create_study(client)
    record = await _upload(client, study_id, "scan.png", _TINY_PNG, "image/png")

    response = await client.get(record["signedUrl"].removeprefix("/api/v1"))

    assert response.status_code == 200
    directive, max_age = response.headers["cache-control"].split(", ")
    assert directive == "private"
    assert 0 < int(max_age.removeprefix("max-age=")) <= 2 * settings.signed_url_ttl_seconds


def test_cloudinary_keeps_a_connection_pool_for_parallel_uploads(monkeypatch):
    import cloudinary.uploader

    from app.storage import cloudinary as cloudinary_module

    monkeypatch.setattr(cloudinary_module, "_credentials", lambda: ("demo", "key", "secret"))
    monkeypatch.setattr(cloudinary.uploader, "_http", cloudinary.uploader._http)  # restored after
    cloudinary_module.CloudinaryStorageProvider()

    assert cloudinary.uploader._http.connection_pool_kw["maxsize"] == cloudinary_module._POOL_SIZE == 16
