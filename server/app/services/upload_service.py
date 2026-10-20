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
# Browsers label a .zip differently per OS (application/zip, application/x-zip-compressed,
# sometimes octet-stream), so a ZIP is recognised by type OR by its .zip name.
_ZIP_MIME_TYPES = ("application/zip", "application/x-zip-compressed", "application/x-zip", "multipart/x-zip")


def is_zip_upload(content_type: str, filename: str | None) -> bool:
    return content_type in _ZIP_MIME_TYPES or (filename or "").lower().endswith(".zip")


def is_pdf_upload(content_type: str, filename: str | None) -> bool:
    return content_type == "application/pdf" or (filename or "").lower().endswith(".pdf")


class UploadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.studies = StudyRepository(db)
        # After `upload_file`: storage key -> bytes of what analysis should read for the file
        # just uploaded (the image itself, or a video's frames), so the intake flow can run
        # analysis without downloading any of it back from storage.
        self.preloaded: dict[str, bytes] = {}

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
        archive_kind = "zip" if is_zip_upload(content_type, file.filename) else "pdf" if is_pdf_upload(content_type, file.filename) else None
        if archive_kind:
            # A ZIP (MRI/CT export: slices picked per series) or a PDF of scan images (pages
            # rendered to images). Only the picked images are kept, not the file itself —
            # see archive_service.py.
            from app.services.archive_service import store_archive

            updated_study, file_record, self.preloaded = await store_archive(
                file=file,
                study_id=study_id,
                organization_id=organization_id,
                uploaded_by=uploaded_by,
                db=self.db,
                kind=archive_kind,
            )
            if not updated_study:
                raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")
            return updated_study, file_record

        if not any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
            raise AppError.bad_request(
                f"Unsupported file type: {content_type}. Upload an image, video, DICOM, a ZIP of scan images, or a PDF.",
                "UNSUPPORTED_FILE_TYPE",
            )

        if content_type.startswith("video/"):
            # Streamed to disk, frames cut from the original, compressed copy stored in the
            # background — see video_service.py.
            from app.services.video_service import store_video

            updated_study, file_record, self.preloaded = await store_video(
                file=file,
                study_id=study_id,
                organization_id=organization_id,
                uploaded_by=uploaded_by,
                db=self.db,
            )
            if not updated_study:
                raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")
            return updated_study, file_record

        # Starlette has already spooled the multipart body to a temp file and knows its size,
        # so an oversized upload (MAX_UPLOAD_MB, default 1GB for MRI/ultrasound video) is
        # rejected before it's pulled into memory; the post-read check covers a missing size.
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if file.size is not None and file.size > max_bytes:
            raise AppError.bad_request(f"File exceeds the {settings.max_upload_mb}MB upload limit.", "FILE_TOO_LARGE")
        data = await file.read()
        if len(data) > max_bytes:
            raise AppError.bad_request(f"File exceeds the {settings.max_upload_mb}MB upload limit.", "FILE_TOO_LARGE")

        extension = os.path.splitext(file.filename or "")[1]
        category = storage_category_for(content_type, modality)
        storage_key = f"{category}/{new_id()}{extension}"
        await get_storage().upload(storage_key, data, content_type)
        self.preloaded = {storage_key: data}

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
