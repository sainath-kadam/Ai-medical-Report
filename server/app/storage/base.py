"""Storage abstraction (spec §14). Medical files are NEVER made publicly accessible —
every read goes through `generate_signed_url` (short-lived) or a backend-mediated
download; there is no static file mount anywhere in this app.
"""

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def download(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        """Returns a URL/path the frontend can use directly, valid for `expires_in`
        seconds (defaults to `settings.signed_url_ttl_seconds`)."""
        ...
