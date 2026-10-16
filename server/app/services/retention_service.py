"""Keeps stored videos in check. Two rules, both run from the hourly loop started in
`app/main.py`'s lifespan:

1. Storage budget (`enforce_storage_budget`, on by default): once stored files pass
   STORAGE_CLEANUP_PERCENT (50) of STORAGE_CAPACITY_MB, the OLDEST VIDEOS are deleted until
   usage is back under it. Also called right before each new compressed video is stored
   (video_service), so room is made first, then the new one goes in.
2. Age (`purge_expired_videos`, off by default): videos older than VIDEO_RETENTION_DAYS.

Only videos are ever deleted — they're by far the largest files, and each keeps the
full-quality frames the AI read, so its report and any re-analysis are unaffected. Photos,
DICOM, PDFs, and the frames/slices themselves are never touched (photos/DICOM ARE what the
AI reads; deleting them would break re-analysis).

What a deletion does: the stored bytes go (Cloudinary and the fallback provider alike); the
`study_files` row stays, marked `purgedAt` (signedUrl becomes null, the UI says so).

Organizations are walked one at a time so every query stays tenant-scoped, like
everywhere else; the budget itself is for the whole storage account (all organizations
share one Cloudinary account), so the oldest video across all of them goes first.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import get_logger
from app.database.connection import get_session_factory
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.study_repository import StudyRepository
from app.storage import get_storage

logger = get_logger(__name__)

PURGE_INTERVAL_SECONDS = 60 * 60
_ORG_PAGE_SIZE = 100


async def purge_expired_videos(session, *, now: datetime | None = None) -> int:
    """Deletes the stored bytes of every video older than VIDEO_RETENTION_DAYS and marks
    its file record purged. Returns how many were purged. A storage error on one file is
    logged and skipped (it is retried on the next run), never raised."""
    if settings.video_retention_days <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=settings.video_retention_days)
    organizations = OrganizationRepository(session)
    studies = StudyRepository(session)
    storage = get_storage()
    purged = 0

    skip = 0
    while True:
        orgs, total = await organizations.list_all(skip=skip, limit=_ORG_PAGE_SIZE)
        for org in orgs:
            for file in await studies.list_expired_video_files(org["_id"], cutoff):
                try:
                    await storage.delete(file["storageKey"])
                except Exception as exc:
                    logger.warning("Video retention: could not delete key=%s (%s)", file["storageKey"], type(exc).__name__)
                    continue
                await studies.mark_file_purged(file["id"], org["_id"])
                purged += 1
        skip += _ORG_PAGE_SIZE
        if skip >= total:
            break

    if purged:
        logger.info("Video retention: deleted %d video(s) older than %d day(s)", purged, settings.video_retention_days)
    return purged


_budget_lock = asyncio.Lock()


async def _all_organization_ids(session) -> list[str]:
    organizations = OrganizationRepository(session)
    ids: list[str] = []
    skip = 0
    while True:
        orgs, total = await organizations.list_all(skip=skip, limit=_ORG_PAGE_SIZE)
        ids.extend(org["_id"] for org in orgs)
        skip += _ORG_PAGE_SIZE
        if skip >= total:
            return ids


def storage_budget_bytes() -> int:
    return settings.storage_capacity_mb * 1024 * 1024 * settings.storage_cleanup_percent // 100


async def enforce_storage_budget(session, *, incoming_bytes: int = 0) -> int:
    """Deletes the oldest stored videos until stored files + `incoming_bytes` fit under the
    budget. Returns how many were deleted. Never deletes anything but videos; if there are
    no videos left to delete and it's still over, that's logged, not raised (the upload
    still goes ahead). Serialized by a lock so two videos finishing together don't both
    count the same free space."""
    if settings.storage_cleanup_percent <= 0:
        return 0
    async with _budget_lock:
        studies = StudyRepository(session)
        budget = storage_budget_bytes()
        org_ids = await _all_organization_ids(session)
        used = sum([await studies.stored_bytes(org_id) for org_id in org_ids])
        if used + incoming_bytes <= budget:
            return 0

        candidates = [(file, org_id) for org_id in org_ids for file in await studies.list_stored_video_files(org_id)]
        candidates.sort(key=lambda pair: pair[0]["uploadedAt"])
        storage = get_storage()
        deleted = 0
        for file, org_id in candidates:
            if used + incoming_bytes <= budget:
                break
            try:
                await storage.delete(file["storageKey"])
            except Exception as exc:
                logger.warning("Storage budget: could not delete key=%s (%s)", file["storageKey"], type(exc).__name__)
                continue
            await studies.mark_file_purged(file["id"], org_id)
            used -= file["sizeBytes"]
            deleted += 1

        mb = 1024 * 1024
        if deleted:
            logger.info(
                "Storage budget: deleted %d oldest video(s); now %d MB used of a %d MB budget (%d%% of %d MB)",
                deleted, used // mb, budget // mb, settings.storage_cleanup_percent, settings.storage_capacity_mb,
            )
        if used + incoming_bytes > budget:
            logger.warning(
                "Storage budget: still over (%d MB used + %d MB incoming > %d MB) with no videos left to delete — "
                "photos/DICOM are never deleted; raise STORAGE_CAPACITY_MB or upgrade the storage plan",
                used // mb, incoming_bytes // mb, budget // mb,
            )
        return deleted


async def run_retention_loop() -> None:
    """Runs both rules now and then every PURGE_INTERVAL_SECONDS until cancelled (app
    shutdown). Each run gets its own session; a failed run is logged and retried on the
    next tick."""
    while True:
        try:
            async with get_session_factory()() as session:
                await purge_expired_videos(session)
                await enforce_storage_budget(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Storage cleanup run failed")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)
