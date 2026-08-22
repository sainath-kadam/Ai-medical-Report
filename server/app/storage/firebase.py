"""Firebase Storage (spec §3/§14). Firebase Storage IS Google Cloud Storage under a
Firebase project — `firebase_admin.storage.bucket()` just hands back the same GCS bucket
object the Firebase console shows you, so this is really a thin `google-cloud-storage`
wrapper. Files are private; all access is via time-limited signed URLs, matching every
other `StorageProvider`.

UNVERIFIED AGAINST A LIVE PROJECT: written to match the documented `firebase-admin` SDK
surface, but no Firebase project/service-account was available to actually exercise this
file during development.
"""

from __future__ import annotations

import anyio

from app.core.config import settings
from app.core.exceptions import AppError
from app.storage.base import StorageProvider


class FirebaseStorageProvider(StorageProvider):
    def __init__(self):
        if not settings.firebase_storage_bucket:
            raise RuntimeError("FIREBASE_STORAGE_BUCKET must be set when STORAGE_PROVIDER=firebase")

        import firebase_admin
        from firebase_admin import credentials, storage

        if not firebase_admin._apps:
            cred = (
                credentials.Certificate(settings.firebase_credentials_path)
                if settings.firebase_credentials_path
                else credentials.ApplicationDefault()
            )
            firebase_admin.initialize_app(cred, {"storageBucket": settings.firebase_storage_bucket})

        self._bucket = storage.bucket()

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        def _upload():
            self._bucket.blob(key).upload_from_string(data, content_type=content_type)

        await anyio.to_thread.run_sync(_upload)

    async def download(self, key: str) -> bytes:
        from google.api_core.exceptions import NotFound

        def _download():
            return self._bucket.blob(key).download_as_bytes()

        try:
            return await anyio.to_thread.run_sync(_download)
        except NotFound as exc:
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND") from exc

    async def delete(self, key: str) -> None:
        await anyio.to_thread.run_sync(lambda: self._bucket.blob(key).delete())

    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        from datetime import timedelta

        ttl = expires_in or settings.signed_url_ttl_seconds
        return self._bucket.blob(key).generate_signed_url(expiration=timedelta(seconds=ttl), method="GET")
