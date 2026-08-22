"""Storage provider selection (spec §3/§14). `get_storage()` is the only thing the rest
of the app imports — swapping `STORAGE_PROVIDER` in the environment is the entire
migration from local disk to Firebase/S3/S3-compatible storage, no code changes required.
"""

from functools import lru_cache

from app.core.config import settings
from app.storage.base import StorageProvider

# Every storage key is prefixed with one of these — files land in a predictable "folder"
# (a real subdirectory for local disk, an S3 key prefix that every S3 console/tool already
# renders as a folder) instead of one flat namespace. `LocalStorageProvider` also uses this
# set to validate the prefix before touching the filesystem.
STORAGE_CATEGORIES = frozenset({"dicom", "video", "x_ray", "ct", "mri", "ultrasound", "other", "pdf", "template_logo"})

_IMAGE_MODALITY_CATEGORIES = frozenset({"x_ray", "ct", "mri", "ultrasound", "other"})


def storage_category_for(mime_type: str, modality: str | None) -> str:
    """Which top-level storage category an uploaded study file belongs in. DICOM and video
    are grouped by format (they can occur for any modality); everything else is grouped by
    the study's own modality so x-rays, CTs, MRIs, and ultrasounds each land separately."""
    if mime_type == "application/dicom":
        return "dicom"
    if mime_type.startswith("video/"):
        return "video"
    if modality in _IMAGE_MODALITY_CATEGORIES:
        return modality
    return "other"


@lru_cache
def get_storage() -> StorageProvider:
    if settings.storage_provider in ("s3", "s3_compatible"):
        from app.storage.s3 import S3StorageProvider

        return S3StorageProvider()
    if settings.storage_provider == "firebase":
        from app.storage.firebase import FirebaseStorageProvider

        return FirebaseStorageProvider()
    from app.storage.local import LocalStorageProvider

    return LocalStorageProvider()
