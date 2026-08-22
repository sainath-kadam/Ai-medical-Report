"""Local-disk storage — the dev-mode default (`STORAGE_PROVIDER=local`). Every uploaded
file lives under `settings.storage_local_dir` (`server/uploads/` by default), organized
into one subdirectory per `app.storage.STORAGE_CATEGORIES` entry (`dicom/`, `x_ray/`,
`pdf/`, ...), keyed within that folder by an opaque string (never the original filename,
to avoid path traversal / collisions). Reads are only ever served through the
signed-URL-verifying route in `app/api/uploads/routes.py` — never a static file mount
(spec §14: never publicly accessible).
"""

import os
import time

import anyio

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import sign_storage_key
from app.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self):
        self.root = os.path.abspath(settings.storage_local_dir)
        os.makedirs(self.root, exist_ok=True)

    def _path_for(self, key: str) -> str:
        # Keys are generated server-side (uuid hex, optionally "category/uuid.ext" — see
        # app.storage.storage_category_for) — these checks are defense in depth against a
        # future caller accidentally passing user input as key. Only a whitelisted category
        # is ever allowed as a real subdirectory; anything else (including any attempted
        # "../" traversal) is flattened to a plain filename in the root, never followed.
        from app.storage import STORAGE_CATEGORIES

        category, sep, rest = key.partition("/")
        if sep and category in STORAGE_CATEGORIES and rest:
            category_dir = os.path.join(self.root, category)
            os.makedirs(category_dir, exist_ok=True)
            return os.path.join(category_dir, os.path.basename(rest))
        return os.path.join(self.root, os.path.basename(key))

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path_for(key)

        def _write():
            with open(path, "wb") as f:
                f.write(data)

        await anyio.to_thread.run_sync(_write)

    async def download(self, key: str) -> bytes:
        path = self._path_for(key)
        if not os.path.exists(path):
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND")

        def _read() -> bytes:
            with open(path, "rb") as f:
                return f.read()

        return await anyio.to_thread.run_sync(_read)

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        if os.path.exists(path):
            await anyio.to_thread.run_sync(os.remove, path)

    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        ttl = expires_in or settings.signed_url_ttl_seconds
        expires_at = int(time.time()) + ttl
        token = sign_storage_key(key, expires_at)
        return f"/api/v1/uploads/file/{key}?token={token}"
