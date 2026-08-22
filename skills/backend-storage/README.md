# backend-storage

`server/app/storage/` — the file-storage abstraction (CONTRACTS.md §6). Every uploaded
study file, generated PDF, and template logo goes through this module; nothing else in the
app talks to the filesystem/S3/Firebase SDK directly.

## Key files

- `base.py` — `StorageProvider`, an ABC with four methods every provider implements:
  `upload(key, data, content_type)`, `download(key) -> bytes`, `delete(key)`,
  `generate_signed_url(key, expires_in=None) -> str`.
- `__init__.py` — `get_storage()` (`@lru_cache`d factory) is the *only* thing the rest of
  the app imports; it picks the provider from `settings.storage_provider`. Also defines
  `STORAGE_CATEGORIES` (the fixed set of key-prefix "folders": `dicom`, `video`, `x_ray`,
  `ct`, `mri`, `ultrasound`, `other`, `pdf`, `template_logo`) and `storage_category_for(
  mime_type, modality)`, which picks the category for an uploaded study file (DICOM/video
  grouped by format since they can occur for any modality; everything else grouped by the
  study's own modality).
- `local.py` — `LocalStorageProvider`, the dev-mode default (`STORAGE_PROVIDER=local`).
  Files live under `settings.storage_local_dir` (`server/uploads/` by default), one real
  subdirectory per category. `generate_signed_url` returns a same-origin path
  (`/api/v1/uploads/file/{key}?token=...`), not an absolute external URL.
- `s3.py` — `S3StorageProvider` (`STORAGE_PROVIDER=s3` or `s3_compatible`). Works against
  AWS S3 or any S3-compatible endpoint (MinIO, DigitalOcean Spaces, Cloudflare R2, ...) via
  `STORAGE_ENDPOINT_URL`. Signed URLs are real presigned S3 URLs, generated on demand and
  never persisted.
- `firebase.py` — `FirebaseStorageProvider` (`STORAGE_PROVIDER=firebase`). Firebase Storage
  is Google Cloud Storage under a Firebase project, so this is a thin `firebase-admin` /
  `google-cloud-storage` wrapper. **Flagged in its own docstring as unverified against a
  live Firebase project** — written to match the documented SDK surface, but never actually
  exercised against a real project/service-account during development. Treat with a bit
  more suspicion than the other two providers if something looks wrong.

## Non-obvious things

- **Swapping providers is a pure env-var change** — `get_storage()` is the single choke
  point every caller goes through, so `STORAGE_PROVIDER=local|s3|s3_compatible|firebase`
  is the entire migration, no code changes required anywhere else.
- **Files are never publicly accessible, by design** — there is no static file mount
  anywhere in the app. Every read goes through `generate_signed_url` (short-lived) or a
  backend-mediated download route. If you're tempted to add a static mount for convenience,
  don't — it breaks this invariant for medical files.
- **Storage keys are server-generated, never derived from user input.** `LocalStorageProvider
  ._path_for` treats an unrecognized/absent category prefix as defense-in-depth: it flattens
  the key to `os.path.basename(key)` in the root rather than following it, so even a
  maliciously crafted key can't path-traverse — but this is a second line of defense, not a
  substitute for keys actually being generated server-side (opaque uuid hex, optionally
  `category/uuid.ext`) as they are today.
