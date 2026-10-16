"""Uploaded video handling — called by `UploadService` for any `video/*` file.

Order matters, and is the whole point of this module:

1. The upload is copied to a local temp file in chunks (never held in memory whole — a
   1GB video on a 512MB server would otherwise crash it), enforcing MAX_UPLOAD_MB as it goes.
2. Frames for the AI are cut by code (OpenCV) from that ORIGINAL file, at full resolution:
   8 for clips up to 30s, then one per 4s, at most 16 (`media_conversion.video_frame_count`).
   They're stored as JPEGs (`video_frames/<fileId>_NN.jpg`) and recorded on the file row
   (`frameKeys`), so analysis — now and on any later re-run — reads exactly these frames,
   never the compressed video.
3. The file row is created straight away with `processingStatus="compressing"`, and the
   request continues (the intake flow runs the AI on the frames immediately).
4. In the background, ffmpeg re-encodes the original to a small H.264 MP4 (under
   VIDEO_COMPRESSED_MAX_MB, so it fits Cloudinary's free per-video limit), that reference
   copy is stored under the row's `storageKey`, and the row flips to ready (`null`) — or
   `"failed"` if encoding/storing failed (the frames, findings and report are unaffected).
   The original is then deleted; it is never stored anywhere.

A server restart mid-compression loses the original (it only ever lived in a temp file):
`fail_interrupted_compressions` runs at startup and marks such rows "failed".
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

import anyio
from fastapi import UploadFile

from app.core.background import schedule, wait_for_background_jobs  # noqa: F401  (re-exported for tests)
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.database.connection import get_session_factory
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.study_repository import StudyRepository
from app.storage import get_storage
from app.utils.ids import new_id
from app.utils.media_conversion import (
    compress_video,
    extract_video_frames_from_path,
    probe_video,
    video_frame_count,
)

logger = get_logger(__name__)

_COPY_CHUNK_BYTES = 8 * 1024 * 1024


async def save_upload_to_temp(file: UploadFile, max_bytes: int) -> tuple[str, int]:
    """Copies the upload to a temp file chunk by chunk. Returns (path, size). Raises
    FILE_TOO_LARGE (and removes the partial file) as soon as the limit is passed."""
    suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
    fd, path = tempfile.mkstemp(prefix="radiolens-upload-", suffix=suffix)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(_COPY_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise AppError.bad_request(
                        f"File exceeds the {settings.max_upload_mb}MB upload limit.", "FILE_TOO_LARGE"
                    )
                await anyio.to_thread.run_sync(out.write, chunk)
    except BaseException:
        _remove(path)
        raise
    return path, size


async def store_video(
    *,
    file: UploadFile,
    study_id: str,
    organization_id: str,
    uploaded_by: str,
    db,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, bytes]]:
    """Steps 1-3 of the module docstring, then schedules step 4. Returns
    `(updated_study, file_record, frames_by_key)` — the frame bytes so the caller can hand
    them straight to analysis without downloading them back from storage."""
    path, size = await save_upload_to_temp(file, settings.max_upload_mb * 1024 * 1024)
    try:
        _, duration = await anyio.to_thread.run_sync(probe_video, path)
        _check_duration(duration)
        frames = await anyio.to_thread.run_sync(extract_video_frames_from_path, path, video_frame_count(duration))

        file_id = new_id()
        storage = get_storage()
        frame_keys = [f"video_frames/{file_id}_{index:02d}.jpg" for index in range(1, len(frames) + 1)]
        await asyncio.gather(*(storage.upload(key, data, "image/jpeg") for key, data in zip(frame_keys, frames)))

        file_record = {
            "id": file_id,
            "fileName": file.filename or f"{file_id}.mp4",
            # The stored reference copy is always an H.264 MP4, whatever was uploaded.
            "storageKey": f"video/{file_id}.mp4",
            "mimeType": "video/mp4",
            "sizeBytes": size,
            "uploadedBy": uploaded_by,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "frameKeys": frame_keys,
            "processingStatus": "compressing",
        }
        updated_study = await StudyRepository(db).add_file(study_id, organization_id, file_record)
    except BaseException:
        _remove(path)
        raise

    if updated_study is None:
        _remove(path)
        return None, file_record, {}

    schedule(_compress_and_store(path, file_record, organization_id, duration))
    return updated_study, file_record, dict(zip(frame_keys, frames))


# Container durations are often a fraction of a second off; don't reject a "2:00" clip.
_DURATION_TOLERANCE_SECONDS = 1


def _format_duration(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def _check_duration(duration: float | None) -> None:
    """VIDEO_MAX_SECONDS (default 2 minutes). An unreadable duration isn't rejected here —
    such a file fails frame extraction instead and is recorded as unanalyzable."""
    limit = settings.video_max_seconds
    if limit > 0 and duration and duration > limit + _DURATION_TOLERANCE_SECONDS:
        raise AppError.bad_request(
            f"This video is {_format_duration(duration)} long; the limit is {_format_duration(limit)}. "
            "Trim it and upload it again.",
            "VIDEO_TOO_LONG",
        )


async def _compress_and_store(src_path: str, file_record: dict[str, Any], organization_id: str, duration: float | None) -> None:
    fd, out_path = tempfile.mkstemp(prefix="radiolens-compressed-", suffix=".mp4")
    os.close(fd)
    status: str | None = None
    size: int | None = None
    try:
        await compress_video(src_path, out_path, duration_seconds=duration, max_mb=settings.video_compressed_max_mb)
        size = os.path.getsize(out_path)
        # Make room first (oldest videos go once storage passes the budget), then store.
        from app.services.retention_service import enforce_storage_budget

        try:
            async with get_session_factory()() as session:
                await enforce_storage_budget(session, incoming_bytes=size)
        except Exception:
            logger.exception("Video file=%s: storage budget check failed; storing anyway", file_record["id"])
        await get_storage().upload_file(file_record["storageKey"], out_path, "video/mp4")
        logger.info(
            "Video file=%s compressed %d -> %d bytes and stored", file_record["id"], file_record["sizeBytes"], size
        )
    except Exception as exc:
        status = "failed"
        logger.warning("Video file=%s: compressed copy not stored (%s: %s)", file_record["id"], type(exc).__name__, exc)
    finally:
        _remove(src_path)
        _remove(out_path)

    values: dict[str, Any] = {"processingStatus": status}
    if size is not None and status is None:
        values["sizeBytes"] = size
    try:
        async with get_session_factory()() as session:
            await StudyRepository(session).update_file(file_record["id"], organization_id, values)
    except Exception:
        logger.exception("Video file=%s: could not record compression result", file_record["id"])


async def fail_interrupted_compressions(session) -> int:
    """Rows still "compressing" at startup lost their original in the restart — mark them
    "failed" so the UI stops waiting. Walks organizations to keep every query tenant-scoped."""
    organizations = OrganizationRepository(session)
    studies = StudyRepository(session)
    failed = 0
    skip = 0
    while True:
        orgs, total = await organizations.list_all(skip=skip, limit=100)
        for org in orgs:
            for file in await studies.list_files_by_processing_status(org["_id"], "compressing"):
                await studies.update_file(file["id"], org["_id"], {"processingStatus": "failed"})
                failed += 1
        skip += 100
        if skip >= total:
            break
    if failed:
        logger.warning("Marked %d interrupted video compression(s) as failed", failed)
    return failed


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
