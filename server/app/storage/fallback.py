"""Primary-with-fallback storage (`STORAGE_FALLBACK_PROVIDER`). Wraps two real providers:
every write goes to the primary (e.g. Cloudinary) and, only if the primary is unusable —
not configured, or the upload itself fails (network, quota, 5xx) — lands in the fallback
(e.g. Firebase) instead, so an outage at one vendor never turns into a lost upload.

Reads don't need to know where a file ended up: `download` asks the primary first and the
fallback second (a miss on Cloudinary/Firebase is a fast 404). Keys that were written to
the fallback in this process are remembered so their reads skip the primary, but that's
only an optimisation — after a restart the try-then-fallback path still finds them.

`generate_signed_url` always returns the app's own same-origin download route
(`/api/v1/uploads/file/{key}?token=...`), which resolves through this wrapper's
`download`, so a link works identically whichever backend actually holds the bytes — and
no medical file is ever exposed on a vendor URL (spec §14).

Logs never include file contents or patient data — only the storage key (an opaque
server-generated id) and the exception type (spec §31).
"""

from __future__ import annotations

import time

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.security import sign_storage_key
from app.storage.base import StorageProvider

logger = get_logger(__name__)


def _is_not_found(exc: Exception) -> bool:
    """Only a provider's explicit 404 (`AppError.not_found` -> 404 status) counts as "the file
    isn't there". Anything else — connection errors, timeouts, 5xx, auth — is "couldn't
    check", and must not be reported to a doctor as a missing file."""
    return isinstance(exc, AppError) and exc.status_code == 404


class FallbackStorageProvider(StorageProvider):
    def __init__(self, primary_name: str, fallback_name: str, build):
        """`build(name) -> StorageProvider` is passed in by `app.storage.get_storage` (it owns
        the name -> class mapping) so this module doesn't import every SDK itself."""
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self._fallback_keys: set[str] = set()

        self.primary: StorageProvider | None
        try:
            self.primary = build(primary_name)
        except Exception as exc:
            # Typically "not configured" (missing credentials). Everything goes to the
            # fallback until the primary is fixed; say so once, loudly, at startup.
            logger.warning(
                "Storage primary %r unavailable (%s: %s) — using fallback %r for all files",
                primary_name, type(exc).__name__, exc, fallback_name,
            )
            self.primary = None

        try:
            self.fallback = build(fallback_name)
        except Exception as exc:
            # Both cloud backends unusable (e.g. credentials not filled in yet): keep the app
            # working on local disk rather than failing every upload, but say so loudly —
            # files written here are NOT in the cloud until the credentials are fixed.
            logger.error(
                "Storage fallback %r ALSO unavailable (%s: %s) — files are going to LOCAL DISK until "
                "STORAGE_PROVIDER/STORAGE_FALLBACK_PROVIDER credentials are fixed",
                fallback_name, type(exc).__name__, exc,
            )
            self.fallback_name = "local"
            self.fallback = build("local")

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        if self.primary is not None:
            try:
                await self.primary.upload(key, data, content_type)
                self._fallback_keys.discard(key)
                return
            except Exception as exc:
                logger.warning(
                    "Storage primary %r failed to store key=%s (%s) — falling back to %r",
                    self.primary_name, key, type(exc).__name__, self.fallback_name,
                )
        await self.fallback.upload(key, data, content_type)
        self._fallback_keys.add(key)

    async def download(self, key: str) -> bytes:
        primary_exc: Exception | None = None
        if self.primary is not None and key not in self._fallback_keys:
            try:
                return await self.primary.download(key)
            except Exception as exc:
                primary_exc = exc
                logger.info(
                    "Storage primary %r %s key=%s (%s) — trying fallback %r",
                    self.primary_name,
                    "has no" if _is_not_found(exc) else "could not be read for",
                    key, type(exc).__name__, self.fallback_name,
                )
        try:
            data = await self.fallback.download(key)
        except Exception as exc:
            # The fallback not having the file only means "file not found" if the primary
            # said the same. If the primary was *unreachable* (DNS, network, 5xx — seen live
            # when Docker's resolver stopped resolving api.cloudinary.com), the file almost
            # certainly still lives there, and reporting it as missing sends an admin
            # hunting for a lost upload instead of a network problem. Surface the primary's
            # own error so the analysis job / download says what actually happened.
            if primary_exc is not None and not _is_not_found(primary_exc):
                if isinstance(primary_exc, AppError):
                    raise primary_exc from exc
                raise AppError(
                    f"Could not reach the {self.primary_name} storage provider to fetch the file.",
                    502, "STORAGE_DOWNLOAD_FAILED",
                ) from primary_exc
            if isinstance(exc, AppError):
                raise
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND") from exc
        self._fallback_keys.add(key)
        return data

    async def delete(self, key: str) -> None:
        # A file lives in exactly one backend, but we don't persist which — remove from both
        # and treat "wasn't there" as success on each side.
        for provider in (self.primary, self.fallback):
            if provider is None:
                continue
            try:
                await provider.delete(key)
            except Exception as exc:
                logger.info("Storage delete of key=%s skipped on one backend (%s)", key, type(exc).__name__)
        self._fallback_keys.discard(key)

    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        ttl = expires_in or settings.signed_url_ttl_seconds
        expires_at = int(time.time()) + ttl
        token = sign_storage_key(key, expires_at)
        return f"/api/v1/uploads/file/{key}?token={token}"
