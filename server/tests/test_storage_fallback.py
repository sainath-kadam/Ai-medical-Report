"""`FallbackStorageProvider.download` error semantics (app/storage/fallback.py), with fake
providers — no cloud SDKs, no network.

Why: seen live — Docker's resolver stopped resolving api.cloudinary.com, every Cloudinary
read raised a connection error, the wrapper tried the (empty) local fallback, and the
analysis job told the doctor "File not found in storage" about files that were sitting
safely in Cloudinary. An unreachable primary must be reported as unreachable; only a real
404 from the primary may be turned into "not found" by the fallback's miss.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.storage.fallback import FallbackStorageProvider


class _Fake:
    def __init__(self, files: dict[str, bytes] | None = None, error: Exception | None = None) -> None:
        self.files = files or {}
        self.error = error
        self.calls: list[str] = []

    async def upload(self, key, data, content_type):
        self.files[key] = data

    async def download(self, key):
        self.calls.append(key)
        if self.error is not None:
            raise self.error
        if key not in self.files:
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND")
        return self.files[key]

    async def delete(self, key):
        self.files.pop(key, None)

    def generate_signed_url(self, key, expires_in=None):
        return key


def _provider(primary: _Fake, fallback: _Fake) -> FallbackStorageProvider:
    return FallbackStorageProvider("cloudinary", "local", lambda name: primary if name == "cloudinary" else fallback)


@pytest.mark.asyncio
async def test_primary_hit_never_touches_fallback():
    primary, fallback = _Fake({"k": b"bytes"}), _Fake()
    assert await _provider(primary, fallback).download("k") == b"bytes"
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_primary_404_then_fallback_hit():
    primary, fallback = _Fake(), _Fake({"k": b"local-bytes"})
    assert await _provider(primary, fallback).download("k") == b"local-bytes"


@pytest.mark.asyncio
async def test_missing_everywhere_is_not_found():
    with pytest.raises(AppError) as excinfo:
        await _provider(_Fake(), _Fake()).download("k")
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_unreachable_primary_is_reported_as_unreachable_not_as_missing():
    unreachable = AppError("Could not reach Cloudinary to fetch the file.", 502, "STORAGE_DOWNLOAD_FAILED")
    with pytest.raises(AppError) as excinfo:
        await _provider(_Fake(error=unreachable), _Fake()).download("k")
    assert excinfo.value.code == "STORAGE_DOWNLOAD_FAILED"
    assert excinfo.value.status_code == 502
    assert "Cloudinary" in excinfo.value.message


@pytest.mark.asyncio
async def test_unreachable_primary_raw_exception_is_wrapped_not_swallowed():
    with pytest.raises(AppError) as excinfo:
        await _provider(_Fake(error=OSError("Temporary failure in name resolution")), _Fake()).download("k")
    assert excinfo.value.code == "STORAGE_DOWNLOAD_FAILED"
    assert "cloudinary" in excinfo.value.message


@pytest.mark.asyncio
async def test_unreachable_primary_still_serves_from_fallback_when_it_has_the_file():
    unreachable = AppError("Could not reach Cloudinary to fetch the file.", 502, "STORAGE_DOWNLOAD_FAILED")
    assert await _provider(_Fake(error=unreachable), _Fake({"k": b"local"})).download("k") == b"local"
