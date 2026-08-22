"""Shared file-validation + storage-write logic for attaching a file to a study
(CONTRACTS.md §6/§14). Used by both `POST /uploads/studies/{id}/files` and the combined
`POST /studies/intake` flow (`StudyService.create_from_intake`) so the mime/size checks
and storage-key construction live in exactly one place.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories.study_repository import StudyRepository
from app.storage import get_storage, storage_category_for
from app.utils.ids import new_id

_ALLOWED_MIME_PREFIXES = ("image/", "video/", "application/dicom", "application/octet-stream")


class UploadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.studies = StudyRepository(db)

    async def upload_file(
        self,
        *,
        study_id: str,
        organization_id: str,
        modality: str | None,
        file: UploadFile,
        uploaded_by: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validates and stores one file against an already org-scoped study, then records
        it via `StudyRepository.add_file`. Returns `(updated_study, file_record)` — the
        refreshed study dict (with `files` attached, `_id`-keyed) and the new file's own
        record, since callers want both (an audit-log entry needs the file record; the
        response needs the whole study)."""
        content_type = file.content_type or "application/octet-stream"
        if not any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
            raise AppError.bad_request(
                f"Unsupported file type: {content_type}. Upload an image, video, or DICOM file.",
                "UNSUPPORTED_FILE_TYPE",
            )

        data = await file.read()
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if len(data) > max_bytes:
            raise AppError.bad_request(f"File exceeds the {settings.max_upload_mb}MB upload limit.", "FILE_TOO_LARGE")

        extension = os.path.splitext(file.filename or "")[1]
        category = storage_category_for(content_type, modality)
        storage_key = f"{category}/{new_id()}{extension}"
        await get_storage().upload(storage_key, data, content_type)

        file_record = {
            "id": new_id(),
            "fileName": file.filename or storage_key,
            "storageKey": storage_key,
            "mimeType": content_type,
            "sizeBytes": len(data),
            "uploadedBy": uploaded_by,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
        }
        updated_study = await self.studies.add_file(study_id, organization_id, file_record)
        if not updated_study:
            raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")
        return updated_study, file_record
