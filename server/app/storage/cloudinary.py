"""Cloudinary storage (`STORAGE_PROVIDER=cloudinary`). Configure with either the single
`CLOUDINARY_URL` (`cloudinary://<api_key>:<api_secret>@<cloud_name>`, copied straight from
the Cloudinary console) or the three separate `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY`
/ `CLOUDINARY_API_SECRET` values.

Every file is stored as an `authenticated`, `raw` asset:
  - `raw` keeps our own key (`x_ray/<uuid>.jpg`, `pdf/<id>_v2.pdf`, ...) verbatim as the
    Cloudinary public_id — extension and category folder included — for every file type
    (JPEG/PNG, video, DICOM, PDF) with one code path, since we only need blob storage, not
    Cloudinary's image transformations.
  - `authenticated` means Cloudinary itself refuses to serve the asset without a signed
    URL — medical files are never reachable on a plain CDN URL (spec §14; verified live:
    the unsigned URL returns 401). `download` fetches through a 60-second API-signed
    private-download link (origin, not CDN — see `_private_download_url`), generated
    server-side and never handed to a browser.

`generate_signed_url` deliberately returns the app's own same-origin download route
(`/api/v1/uploads/file/{key}?token=...`, exactly like `LocalStorageProvider`), not a
Cloudinary URL: the bytes are proxied through the API, so no medical file is ever cached
on a public CDN edge, and it works identically whether or not a fallback provider ended up
holding the file (see `fallback.py`).

The `cloudinary` SDK is synchronous, so its calls run in a worker thread
(`anyio.to_thread.run_sync`) — never call it directly from an `async def`.
"""

from __future__ import annotations

import io
import time
from urllib.parse import urlparse

import anyio
import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import sign_storage_key
from app.storage.base import StorageProvider

_RESOURCE_TYPE = "raw"
_DELIVERY_TYPE = "authenticated"


def _credentials() -> tuple[str, str, str]:
    """(cloud_name, api_key, api_secret) from CLOUDINARY_URL or the three separate vars."""
    if settings.cloudinary_url:
        parsed = urlparse(settings.cloudinary_url)
        if parsed.scheme != "cloudinary" or not (parsed.hostname and parsed.username and parsed.password):
            raise RuntimeError("CLOUDINARY_URL must look like cloudinary://<api_key>:<api_secret>@<cloud_name>")
        return parsed.hostname, parsed.username, parsed.password
    if settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret:
        return settings.cloudinary_cloud_name, settings.cloudinary_api_key, settings.cloudinary_api_secret
    raise RuntimeError(
        "Cloudinary is not configured: set CLOUDINARY_URL (or CLOUDINARY_CLOUD_NAME + CLOUDINARY_API_KEY + "
        "CLOUDINARY_API_SECRET) when STORAGE_PROVIDER=cloudinary"
    )


class CloudinaryStorageProvider(StorageProvider):
    def __init__(self):
        import cloudinary

        cloud_name, api_key, api_secret = _credentials()
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        import cloudinary.uploader

        def _upload():
            stream = io.BytesIO(data)
            stream.name = key.rsplit("/", 1)[-1]
            cloudinary.uploader.upload(
                stream,
                public_id=key,
                resource_type=_RESOURCE_TYPE,
                type=_DELIVERY_TYPE,
                overwrite=True,
                invalidate=True,
            )

        try:
            await anyio.to_thread.run_sync(_upload)
        except Exception as exc:
            raise AppError("Could not store the file in Cloudinary.", 502, "STORAGE_UPLOAD_FAILED") from exc

    def _private_download_url(self, key: str) -> str:
        """A short-lived (60 s), API-signed download link served by Cloudinary's origin, not
        its CDN. Chosen over a signed *delivery* URL (`cloudinary_url(sign_url=True)`) on
        purpose, verified against a live account: delivery URLs never expire and the CDN
        caches the bytes for up to 30 days — a deleted file kept downloading from the edge
        until the async purge landed. This link expires, and a delete is visible on the very
        next read. Only ever used server-side, right here; never handed to a browser."""
        import cloudinary.utils

        return cloudinary.utils.private_download_url(
            key, None, resource_type=_RESOURCE_TYPE, type=_DELIVERY_TYPE, expires_at=int(time.time()) + 60
        )

    async def download(self, key: str) -> bytes:
        url = self._private_download_url(key)
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise AppError("Could not reach Cloudinary to fetch the file.", 502, "STORAGE_DOWNLOAD_FAILED") from exc
        if response.status_code == 404:
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND")
        if response.status_code >= 400:
            raise AppError("Cloudinary refused the file download.", 502, "STORAGE_DOWNLOAD_FAILED")
        return response.content

    async def delete(self, key: str) -> None:
        import cloudinary.uploader

        await anyio.to_thread.run_sync(
            lambda: cloudinary.uploader.destroy(key, resource_type=_RESOURCE_TYPE, type=_DELIVERY_TYPE, invalidate=True)
        )

    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        ttl = expires_in or settings.signed_url_ttl_seconds
        expires_at = int(time.time()) + ttl
        token = sign_storage_key(key, expires_at)
        return f"/api/v1/uploads/file/{key}?token={token}"
