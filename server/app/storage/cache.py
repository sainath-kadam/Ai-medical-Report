"""A small in-memory read cache in front of the storage provider (`get_storage()` wraps
the real one in `CachedStorageProvider`).

Why: every view of a stored image went back to Cloudinary (~0.5s per file through its
private-download API, measured live) — 16 slices on a study page, again for each doctor,
again on every re-analysis. Only files that can NEVER change are cached: study images,
DICOM, and the video frames / ZIP slices the AI reads. Each is written once under a unique
server-generated key and never overwritten. PDFs, template logos (rewritten under the
same key) and videos (large) always go to storage.

Bounded: at most `_MAX_TOTAL_BYTES` held, no single file over `_MAX_FILE_BYTES`, least-
recently-used evicted first. Per process, so it starts empty after a restart — a cache
miss just means the normal download.
"""

from __future__ import annotations

from collections import OrderedDict

from app.storage.base import StorageProvider

_CACHEABLE_PREFIXES = ("video_frames/", "study_slices/", "x_ray/", "ct/", "mri/", "ultrasound/", "other/", "dicom/")
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_FILE_BYTES = 4 * 1024 * 1024


class CachedStorageProvider(StorageProvider):
    def __init__(self, inner: StorageProvider) -> None:
        self.inner = inner
        self._entries: OrderedDict[str, bytes] = OrderedDict()
        self._total = 0

    @staticmethod
    def _cacheable(key: str, size: int) -> bool:
        return key.startswith(_CACHEABLE_PREFIXES) and size <= _MAX_FILE_BYTES

    def _remember(self, key: str, data: bytes) -> None:
        if not self._cacheable(key, len(data)):
            return
        self._forget(key)
        self._entries[key] = data
        self._total += len(data)
        while self._total > _MAX_TOTAL_BYTES:
            _, evicted = self._entries.popitem(last=False)
            self._total -= len(evicted)

    def _forget(self, key: str) -> None:
        old = self._entries.pop(key, None)
        if old is not None:
            self._total -= len(old)

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        await self.inner.upload(key, data, content_type)
        self._remember(key, data)

    async def upload_file(self, key: str, path: str, content_type: str) -> None:
        self._forget(key)
        await self.inner.upload_file(key, path, content_type)

    async def download(self, key: str) -> bytes:
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached
        data = await self.inner.download(key)
        self._remember(key, data)
        return data

    async def delete(self, key: str) -> None:
        self._forget(key)
        await self.inner.delete(key)

    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        return self.inner.generate_signed_url(key, expires_in)
