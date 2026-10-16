"""Storage abstraction (spec §14). Medical files are NEVER made publicly accessible —
every read goes through `generate_signed_url` (short-lived) or a backend-mediated
download; there is no static file mount anywhere in this app.
"""

from abc import ABC, abstractmethod


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    async def upload_file(self, key: str, path: str, content_type: str) -> None:
        """Uploads a file from local disk (the compressed video). Default: read it and call
        `upload`; providers that can stream from a path (Cloudinary) override this."""
        import anyio

        data = await anyio.to_thread.run_sync(_read_bytes, path)
        await self.upload(key, data, content_type)

    @abstractmethod
    async def download(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        """Returns a URL/path the frontend can use directly, valid for `expires_in`
        seconds (defaults to `settings.signed_url_ttl_seconds`)."""
        ...
