"""ZIP uploads — an MRI/CT export of DICOM slices (or a folder of images). Called by
`UploadService` for any upload recognised as a ZIP.

1. The ZIP is copied to a local temp file in chunks (never held in memory whole),
   enforcing MAX_UPLOAD_MB as it goes (same helper as video uploads).
2. `dicom_archive.read_archive` validates it, groups slices by series, and picks up to
   MAX_ANALYSIS_IMAGES slices spread across the series, converting each to PNG (DICOM,
   windowed from its header) or keeping it as JPEG/PNG.
3. Those slices are stored (`study_slices/<fileId>_NN.png`) and recorded on the file row
   as `frameKeys` — exactly like a video's frames, so analysis and re-analysis read them
   the same way — with what was picked in `extraction`.
4. The ZIP itself is NOT kept (often hundreds of MB; Cloudinary's free plan caps a file at
   10MB): the row is marked `processingStatus="slices_only"` and has no download link.
   The temp file is deleted before the request returns.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import anyio
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories.study_repository import StudyRepository
from app.services.analysis_service import MAX_ANALYSIS_IMAGES
from app.services.video_service import save_upload_to_temp
from app.storage import get_storage
from app.utils.dicom_archive import ArchiveError, read_archive
from app.utils.ids import new_id


async def store_archive(
    *,
    file: UploadFile,
    study_id: str,
    organization_id: str,
    uploaded_by: str,
    db,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, bytes]]:
    """Returns `(updated_study, file_record, slices_by_key)` — the slice bytes so the
    caller can hand them straight to analysis without downloading them back."""
    path, size = await save_upload_to_temp(file, settings.max_upload_mb * 1024 * 1024)
    try:
        try:
            result = await anyio.to_thread.run_sync(read_archive, path, MAX_ANALYSIS_IMAGES)
        except ArchiveError as exc:
            raise AppError.bad_request(exc.message, exc.code) from exc
    finally:
        os.unlink(path)

    file_id = new_id()
    keys = [
        f"study_slices/{file_id}_{index:02d}.{'png' if item.mime_type == 'image/png' else 'jpg'}"
        for index, item in enumerate(result.slices, start=1)
    ]
    storage = get_storage()
    await asyncio.gather(*(storage.upload(key, item.data, item.mime_type) for key, item in zip(keys, result.slices)))

    file_record = {
        "id": file_id,
        "fileName": file.filename or f"{file_id}.zip",
        # Never written to storage — the row has no download link (processingStatus).
        "storageKey": f"archive/{file_id}.zip",
        "mimeType": "application/zip",
        "sizeBytes": size,
        "uploadedBy": uploaded_by,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "frameKeys": keys,
        "processingStatus": "slices_only",
        "extraction": {
            "labels": [item.label for item in result.slices],
            "totalImages": result.total_images,
            "series": result.series,
        },
    }
    updated_study = await StudyRepository(db).add_file(study_id, organization_id, file_record)
    return updated_study, file_record, {key: item.data for key, item in zip(keys, result.slices)}
