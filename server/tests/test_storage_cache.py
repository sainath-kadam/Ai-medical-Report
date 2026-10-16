"""`CachedStorageProvider` (app/storage/cache.py): only never-changing files are cached,
memory stays bounded (LRU), and a delete/overwrite never serves stale bytes."""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.storage import cache as cache_module
from app.storage.cache import CachedStorageProvider


class _Inner:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.downloads: list[str] = []

    async def upload(self, key, data, content_type):
        self.files[key] = data

    async def upload_file(self, key, path, content_type):
        with open(path, "rb") as fh:
            self.files[key] = fh.read()

    async def download(self, key):
        self.downloads.append(key)
        if key not in self.files:
            raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND")
        return self.files[key]

    async def delete(self, key):
        self.files.pop(key, None)

    def generate_signed_url(self, key, expires_in=None):
        return f"signed:{key}"


@pytest.fixture
def storage():
    inner = _Inner()
    return CachedStorageProvider(inner), inner


async def test_slices_and_scan_images_are_served_from_memory_after_the_first_read(storage):
    cached, inner = storage
    inner.files["study_slices/a_01.png"] = b"slice"
    inner.files["mri/b.png"] = b"image"

    for _ in range(3):
        assert await cached.download("study_slices/a_01.png") == b"slice"
        assert await cached.download("mri/b.png") == b"image"

    assert inner.downloads == ["study_slices/a_01.png", "mri/b.png"]


async def test_uploaded_frames_are_cached_without_a_download(storage):
    cached, inner = storage
    await cached.upload("video_frames/v_01.jpg", b"frame", "image/jpeg")

    assert await cached.download("video_frames/v_01.jpg") == b"frame"
    assert inner.downloads == []


@pytest.mark.parametrize("key", ["pdf/r_v1.pdf", "template_logo/org.png", "video/v.mp4"])
async def test_files_that_can_change_or_are_large_always_go_to_storage(storage, key):
    cached, inner = storage
    inner.files[key] = b"x"

    await cached.download(key)
    await cached.download(key)

    assert inner.downloads == [key, key]


async def test_delete_drops_the_cached_copy(storage):
    cached, inner = storage
    await cached.upload("x_ray/a.png", b"img", "image/png")
    await cached.delete("x_ray/a.png")

    with pytest.raises(AppError):
        await cached.download("x_ray/a.png")


async def test_memory_is_bounded_and_least_recently_used_goes_first(storage, monkeypatch):
    monkeypatch.setattr(cache_module, "_MAX_TOTAL_BYTES", 10)
    cached, inner = storage
    for name in ("a", "b", "c"):
        inner.files[f"x_ray/{name}"] = b"1234"  # 4 bytes each, room for two
    await cached.download("x_ray/a")
    await cached.download("x_ray/b")
    await cached.download("x_ray/a")  # a is now the most recently used
    await cached.download("x_ray/c")  # evicts b
    inner.downloads.clear()

    await cached.download("x_ray/a")
    await cached.download("x_ray/c")
    await cached.download("x_ray/b")

    assert inner.downloads == ["x_ray/b"]
    assert cached._total <= 10


async def test_oversized_files_are_not_cached(storage, monkeypatch):
    monkeypatch.setattr(cache_module, "_MAX_FILE_BYTES", 3)
    cached, inner = storage
    inner.files["dicom/big.dcm"] = b"1234"

    await cached.download("dicom/big.dcm")
    await cached.download("dicom/big.dcm")

    assert inner.downloads == ["dicom/big.dcm", "dicom/big.dcm"]


def test_signed_urls_pass_through(storage):
    cached, _ = storage
    assert cached.generate_signed_url("x_ray/a.png") == "signed:x_ray/a.png"
