# backend-uploads

Attaches a file to an existing study, and serves previously-uploaded files back out via a
signed URL. See CONTRACTS.md §6 for the storage-provider abstraction and §9 for the route
list.

## Key files

- `server/app/api/uploads/routes.py` — two routes with deliberately different trust models:
  - `POST /uploads/studies/{id}/files` — normal authenticated, org-scoped,
    `require_admin_or_doctor()`. Looks up the study, delegates the actual work to
    `UploadService.upload_file`, then writes an audit log entry (`FILE_UPLOADED`) itself
    (the service doesn't audit-log).
  - `GET /uploads/file/{key}` — deliberately NOT behind `get_current_user`, since it's
    rendered directly as an `<img src=...>`/download link and a browser can't attach an
    `Authorization` header to that. Its only gate is `verify_storage_signature(storage_key,
    token)` — a short-lived HMAC token baked into the URL by
    `StorageProvider.generate_signed_url`. The study-file lookup afterward
    (`find_file_by_storage_key`) is best-effort, purely to set `Content-Disposition`/
    content-type headers — it is not part of the authorization decision.
- `server/app/services/upload_service.py` — `UploadService.upload_file(*, study_id,
  organization_id, modality, file, uploaded_by)`: validates mime type and size, builds the
  storage key, writes to storage, then calls `StudyRepository.add_file`. Returns
  `(updated_study, file_record)`.

## Non-obvious things

- **This service is shared between two very different call sites** — the plain
  `POST /uploads/studies/{id}/files` route, and `StudyService.create_from_intake` (the
  combined `POST /studies/intake` flow). Both need the exact same mime/size validation and
  storage-key construction, so that logic lives here once rather than being duplicated; if
  you change validation rules, both flows pick it up automatically.
- **Mime-type allowlist is prefix-based, not exact-match**: `_ALLOWED_MIME_PREFIXES =
  ("image/", "video/", "application/dicom", "application/octet-stream")` — anything with a
  content-type starting with one of those passes, everything else is rejected as
  `UNSUPPORTED_FILE_TYPE`. `application/octet-stream` is allowed as a catch-all for clients
  that don't set a specific content-type.
- **The storage key encodes a category, not the study id**: `f"{category}/{new_id()}
  {extension}"` via `storage_category_for(content_type, modality)` — so you cannot infer
  which study a file belongs to from its key alone. That's exactly why `study_files` has a
  unique index on `storageKey` and `find_file_by_storage_key` exists: the download route only
  has the key (from the signed URL), never the study id.
- **Size/mime validation happens after reading the whole file into memory** (`data =
  await file.read()`), not via a streaming check — fine at current expected upload sizes but
  worth knowing if very large files ever become a use case.
- **Videos take a different path** (`app/services/video_service.py`, called from
  `UploadService.upload_file` for any `video/*`): rejected over `VIDEO_MAX_SECONDS` (default
  120; `VIDEO_TOO_LONG`, also checked in the browser), streamed to a temp file in chunks (never
  held in memory), 8–16 full-quality JPEG frames cut from the ORIGINAL by OpenCV (8 up to
  30s, then one per 4s — `media_conversion.video_frame_count`) and stored as
  `video_frames/<fileId>_NN.jpg` (`frameKeys` on the file row; `frameUrls` in responses),
  then the row is created with `processingStatus: "compressing"` and the request carries
  on. In the background ffmpeg (`imageio-ffmpeg`'s bundled binary) re-encodes to H.264
  under `VIDEO_COMPRESSED_MAX_MB`, stores it at `video/<fileId>.mp4`, and sets
  `processingStatus` to null (or `"failed"`). The original is never stored. Analysis reads
  `frameKeys`, never the video (`load_study_images`), so compression can't cost it detail.
  Startup marks rows left "compressing" by a restart as "failed"
  (`fail_interrupted_compressions`).
- **ZIPs (MRI/CT exports) take a third path** (`app/services/archive_service.py` +
  `app/utils/dicom_archive.py`), recognised by MIME or `.zip` name: streamed to disk,
  validated (no encryption, <=10k entries, <=4GB unpacked, zip-bomb ratio check; members
  read via `ZipFile.open`, never extracted by name), DICOM grouped by SeriesInstanceUID and
  ordered by ImagePositionPatient, localizer/scout series dropped, and MAX_ANALYSIS_IMAGES
  slices spread across series (`_allocate`/`_spread`), converted to PNG and stored as
  `study_slices/<fileId>_NN.png` in `frameKeys` (+ `extraction` labels/counts). The ZIP is
  never stored (`processingStatus: "slices_only"`, no signedUrl). Compressed DICOM decodes
  via `python-gdcm`. Errors: ZIP_INVALID / ZIP_NO_IMAGES / ZIP_ENCRYPTED / ZIP_TOO_LARGE /
  ZIP_UNREADABLE.
