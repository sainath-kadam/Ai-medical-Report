"""Uploads domain routes (CONTRACTS.md §6/§9/§14). Two very different trust models on
purpose:

- `POST /studies/{id}/files` is a normal authenticated, organization-scoped route,
  `org_admin`/`doctor` only (RBAC matrix, CONTRACTS.md §3 — "Create studies / upload
  files" is one combined row). The actual validate/store/record logic lives in
  `UploadService.upload_file` (`app/services/upload_service.py`), shared with the combined
  `POST /studies/intake` flow so it isn't duplicated.
- `GET /file/{key}` is deliberately NOT behind `get_current_user` — it's rendered
  directly as an `<img src=...>`/download link in the browser, which cannot attach an
  `Authorization` header. Its only gate is the signed, time-limited token
  (`app/core/security.py::verify_storage_signature`) baked into the URL by
  `StorageProvider.generate_signed_url` — exactly the mechanism spec §14 requires so
  files are never served from an unauthenticated static mount.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError
from app.core.security import CurrentUser, require_admin_or_doctor, signature_expires_at, verify_storage_signature
from app.repositories.study_repository import StudyRepository
from app.services.audit_service import AuditService
from app.services.study_service import with_signed_urls
from app.services.upload_service import UploadService
from app.storage import get_storage
from app.utils.ids import to_public
from app.utils.response import ok

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/studies/{study_id}/files", status_code=201)
async def upload_study_file(
    study_id: str,
    request: Request,
    file: UploadFile,
    current_user: CurrentUser = Depends(require_admin_or_doctor()),
    db: AsyncSession = Depends(get_db),
):
    studies = StudyRepository(db)
    study = await studies.find_by_id_scoped(study_id, current_user.organization_id)
    if not study:
        raise AppError.not_found("Study not found", "STUDY_NOT_FOUND")

    updated_study, file_record = await UploadService(db).upload_file(
        study_id=study_id,
        organization_id=current_user.organization_id,
        modality=study.get("modality"),
        file=file,
        uploaded_by=current_user.id,
    )

    await AuditService(db).log(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="FILE_UPLOADED",
        resource_type="study",
        resource_id=study_id,
        metadata={"sizeBytes": file_record["sizeBytes"], "mimeType": file_record["mimeType"]},
        ip=getattr(request.state, "client_ip", None),
        user_agent=getattr(request.state, "user_agent", None),
    )

    return ok(to_public(with_signed_urls(updated_study)), status_code=201)


@router.get("/file/{storage_key:path}")
async def download_file(storage_key: str, token: str = Query(...), db: AsyncSession = Depends(get_db)):
    if not verify_storage_signature(storage_key, token):
        raise AppError.unauthorized("This link is invalid or has expired", "INVALID_OR_EXPIRED_LINK")

    # Best-effort content-type/filename lookup for whichever study this file belongs to —
    # the signed token itself is the authorization; this is purely for response headers.
    file_record = await StudyRepository(db).find_file_by_storage_key(storage_key)
    content_type = file_record["mimeType"] if file_record else "application/octet-stream"
    file_name = file_record["fileName"] if file_record else storage_key
    if not file_record and storage_key.startswith(("video_frames/", "study_slices/")):
        # A video frame or a ZIP slice the AI read (not a file row of its own) — see
        # video_service.py / archive_service.py.
        file_name = storage_key.rsplit("/", 1)[-1]
        content_type = "image/png" if file_name.endswith(".png") else "image/jpeg"

    data = await get_storage().download(storage_key)
    # The link is the authorization and stays the same URL for its whole window (see
    # signed_file_url), so the browser may keep the file until the link expires — "private"
    # keeps it out of any shared/CDN cache. Opening the same study again then costs no
    # download at all.
    max_age = max(0, (signature_expires_at(token) or 0) - int(time.time()))
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Cache-Control": f"private, max-age={max_age}",
        },
    )
