"""S3 / S3-compatible object storage (spec §3/§14). Works against AWS S3 as well as any
S3-compatible endpoint (MinIO, DigitalOcean Spaces, Cloudflare R2, etc.) by setting
`STORAGE_ENDPOINT_URL`. Files are private (no public ACL); all access is via time-limited
presigned URLs, generated on demand and never persisted.
"""

import anyio
import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.exceptions import AppError
from app.storage.base import StorageProvider


class S3StorageProvider(StorageProvider):
    def __init__(self):
        if not settings.storage_bucket:
            raise RuntimeError("STORAGE_BUCKET must be set when STORAGE_PROVIDER=s3|s3_compatible")
        self.bucket = settings.storage_bucket
        self._client = boto3.client(
            "s3",
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            endpoint_url=settings.storage_endpoint_url or None,
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        )

    async def download(self, key: str) -> bytes:
        try:
            response = await anyio.to_thread.run_sync(lambda: self._client.get_object(Bucket=self.bucket, Key=key))
            return await anyio.to_thread.run_sync(response["Body"].read)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise AppError.not_found("File not found in storage", "FILE_NOT_FOUND") from exc
            raise

    async def delete(self, key: str) -> None:
        await anyio.to_thread.run_sync(lambda: self._client.delete_object(Bucket=self.bucket, Key=key))

    def generate_signed_url(self, key: str, expires_in: int | None = None) -> str:
        ttl = expires_in or settings.signed_url_ttl_seconds
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl
        )
