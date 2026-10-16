"""Reads a ZIP of scan images — typically an MRI/CT export: hundreds of DICOM slices across
several series (T1, T2, FLAIR, ...) — and picks the slices the AI should read.

Why a ZIP beats a screen-recorded video for MRI/CT: these are the scanner's original
slices — full bit depth, proper windowing from the DICOM header, and each slice's real
position and series — instead of a lossy recording of someone scrolling through a viewer.

Selection is done by code, not by the AI (`select_slices`):
  - DICOM slices are grouped by series (SeriesInstanceUID) and ordered by their real
    position along the scan axis (ImagePositionPatient projected on the slice normal),
    falling back to InstanceNumber, then SliceLocation, then file name.
  - Localizer/scout series (the low-detail planning shots) are dropped when there's
    anything else.
  - The budget (MAX_ANALYSIS_IMAGES) is spread across series — every series gets a share,
    so a finding visible on only one sequence is still in front of the AI — and within a
    series slices are evenly spaced through the volume, skipping the extreme ends.
  - Plain images in the ZIP (JPEG/PNG/...) are treated as one "series" per folder.

Safety (a ZIP is untrusted input): members are read through `ZipFile.open` one at a time
— nothing is ever extracted to disk under its own name, so path tricks ("../") can't
escape; encrypted archives, too many entries, an oversized total, or an extreme
compression ratio (zip bomb) are rejected up front from the central directory.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.utils.media_conversion import dicom_to_png_bytes

logger = get_logger(__name__)

MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 4 * 1024**3
# A real DICOM slice compresses maybe 2-10x; a zip bomb compresses thousands of times.
# Only checked on large members, where an absurd ratio can't be a legitimately blank slice.
_BOMB_CHECK_MIN_BYTES = 10 * 1024**2
_MAX_COMPRESSION_RATIO = 1000

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_PASSTHROUGH_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
_LOCALIZER_WORDS = ("localizer", "localiser", "scout", "survey", "tri-pilot", "3-plane", "3pl loc", "loc")


class ArchiveError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _Entry:
    member: str
    kind: str  # "dicom" | "image"
    series_key: str
    series_label: str
    series_number: int
    sort_key: tuple
    is_localizer: bool = False


@dataclass
class _Series:
    key: str
    label: str
    number: int
    is_localizer: bool
    entries: list[_Entry] = field(default_factory=list)


@dataclass
class ArchiveSlice:
    data: bytes
    mime_type: str
    label: str


@dataclass
class ArchiveResult:
    slices: list[ArchiveSlice]
    total_images: int
    series: list[dict]  # [{"label", "slices", "picked"}] in series order


# --- Reading -------------------------------------------------------------------------


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def _validate(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ArchiveError("ZIP_TOO_LARGE", f"This ZIP has {len(infos)} files; the limit is {MAX_ARCHIVE_ENTRIES}.")
    if sum(info.file_size for info in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise ArchiveError("ZIP_TOO_LARGE", "This ZIP is larger than 4GB once unpacked.")
    members = []
    for info in infos:
        if info.flag_bits & 0x1:
            raise ArchiveError("ZIP_ENCRYPTED", "This ZIP is password-protected. Upload it without a password.")
        if info.is_dir():
            continue
        name = info.filename
        base = os.path.basename(name)
        if not base or base.startswith(".") or name.startswith("__MACOSX/"):
            continue
        if info.file_size >= _BOMB_CHECK_MIN_BYTES and info.file_size > _MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
            raise ArchiveError("ZIP_INVALID", "This ZIP looks malformed (an entry expands far beyond its size).")
        members.append(info)
    return members


def _looks_like_dicom(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bool:
    if info.filename.lower().endswith(".dcm"):
        return True
    if info.file_size < 132:
        return False
    with archive.open(info) as fh:
        return fh.read(132)[128:132] == b"DICM"


def _slice_position(ds) -> float | None:
    """Position along the scan axis: ImagePositionPatient projected on the slice normal
    (cross product of the row/column direction cosines) — the robust way to order slices."""
    position = getattr(ds, "ImagePositionPatient", None)
    orientation = getattr(ds, "ImageOrientationPatient", None)
    if not position or not orientation or len(position) != 3 or len(orientation) != 6:
        return None
    try:
        r = [float(v) for v in orientation[:3]]
        c = [float(v) for v in orientation[3:]]
        normal = (r[1] * c[2] - r[2] * c[1], r[2] * c[0] - r[0] * c[2], r[0] * c[1] - r[1] * c[0])
        return sum(float(p) * n for p, n in zip(position, normal))
    except (TypeError, ValueError):
        return None


def _number(value, default):
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _dicom_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> _Entry | None:
    import pydicom

    try:
        with archive.open(info) as fh:
            ds = pydicom.dcmread(fh, stop_before_pixels=True, force=True)
    except Exception:
        return None
    if not getattr(ds, "Rows", None) or not getattr(ds, "Columns", None):
        return None  # DICOMDIR, structured reports, presentation states: no image

    description = str(getattr(ds, "SeriesDescription", "") or getattr(ds, "ProtocolName", "") or "").strip()
    series_number = _number(getattr(ds, "SeriesNumber", None), 10**6)
    label = description or str(getattr(ds, "Modality", "") or "Series")
    if series_number != 10**6:
        label = f"{label} (series {series_number})"
    image_type = " ".join(str(v) for v in (getattr(ds, "ImageType", None) or [])).lower()
    lowered = description.lower()
    is_localizer = "localizer" in image_type or any(
        lowered == word or lowered.startswith(word + " ") or f" {word}" in f" {lowered}" for word in _LOCALIZER_WORDS
    )

    position = _slice_position(ds)
    instance = _number(getattr(ds, "InstanceNumber", None), None)
    location = getattr(ds, "SliceLocation", None)
    sort_key = (
        position if position is not None else float("inf"),
        instance if instance is not None else 10**9,
        float(location) if location not in (None, "") else float("inf"),
        _natural_key(info.filename),
    )
    return _Entry(
        member=info.filename,
        kind="dicom",
        series_key=str(getattr(ds, "SeriesInstanceUID", "") or label),
        series_label=label,
        series_number=series_number,
        sort_key=sort_key,
        is_localizer=is_localizer,
    )


def _scan(archive: zipfile.ZipFile) -> list[_Entry]:
    entries: list[_Entry] = []
    for info in _validate(archive):
        extension = os.path.splitext(info.filename)[1].lower()
        if _looks_like_dicom(archive, info):
            entry = _dicom_entry(archive, info)
            if entry:
                entries.append(entry)
        elif extension in _IMAGE_EXTENSIONS:
            folder = os.path.dirname(info.filename) or "Images"
            entries.append(
                _Entry(
                    member=info.filename,
                    kind="image",
                    series_key=f"folder:{folder}",
                    series_label=os.path.basename(folder) or "Images",
                    series_number=10**6,
                    sort_key=(0, 0, 0, _natural_key(info.filename)),
                )
            )
    return entries


def _group(entries: list[_Entry]) -> list[_Series]:
    by_key: dict[str, _Series] = {}
    for entry in entries:
        series = by_key.setdefault(
            entry.series_key, _Series(entry.series_key, entry.series_label, entry.series_number, entry.is_localizer)
        )
        series.entries.append(entry)
    groups = list(by_key.values())
    for series in groups:
        series.entries.sort(key=lambda e: e.sort_key)
    if any(not s.is_localizer for s in groups):
        groups = [s for s in groups if not s.is_localizer]
    groups.sort(key=lambda s: (s.number, _natural_key(s.label)))
    return groups


# --- Selection -----------------------------------------------------------------------


def _allocate(sizes: list[int], budget: int) -> list[int]:
    """How many slices each series gets: an equal share each (larger series take the
    remainder), never more than a series has; anything left over goes to series with slices
    to spare. More series than budget -> one slice from each of the largest."""
    if budget <= 0 or not sizes:
        return [0] * len(sizes)
    if len(sizes) >= budget:
        largest = sorted(range(len(sizes)), key=lambda i: (-sizes[i], i))[:budget]
        return [1 if i in largest else 0 for i in range(len(sizes))]
    shares = [min(size, budget // len(sizes)) for size in sizes]
    left = budget - sum(shares)
    while left > 0:
        spare = [i for i in sorted(range(len(sizes)), key=lambda i: (-sizes[i], i)) if shares[i] < sizes[i]]
        if not spare:
            break
        for i in spare:
            if left == 0:
                break
            shares[i] += 1
            left -= 1
    return shares


def _spread(count: int, picks: int) -> list[int]:
    """`picks` indices evenly spaced through `count` slices, centered in each segment — so
    one pick is the middle slice and the noisy first/last slices are skipped."""
    if picks <= 0:
        return []
    return sorted({min(count - 1, int((i + 0.5) * count / picks)) for i in range(picks)})


def select_slices(series: list[_Series], budget: int) -> list[tuple[_Series, int]]:
    """(series, index-in-series) pairs to send to the AI, in series order."""
    shares = _allocate([len(s.entries) for s in series], budget)
    return [(s, index) for s, share in zip(series, shares) for index in _spread(len(s.entries), share)]


# --- Converting ----------------------------------------------------------------------


def _convert(archive: zipfile.ZipFile, entry: _Entry) -> tuple[bytes, str] | None:
    data = archive.read(entry.member)
    if entry.kind == "dicom":
        png = dicom_to_png_bytes(data)
        return (png, "image/png") if png else None
    extension = os.path.splitext(entry.member)[1].lower()
    if extension in _PASSTHROUGH_MIME:
        return data, _PASSTHROUGH_MIME[extension]
    try:
        from PIL import Image

        buffer = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buffer, format="PNG")
        return buffer.getvalue(), "image/png"
    except Exception:
        return None


def read_archive(path: str, budget: int) -> ArchiveResult:
    """Validates the ZIP at `path`, picks up to `budget` slices and converts them to
    PNG/JPEG. A picked slice that won't decode is swapped for its nearest neighbour in the
    same series. Raises ArchiveError if it's not a usable ZIP or nothing in it decodes.
    Synchronous (pydicom/zipfile) — call it in a worker thread."""
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError("ZIP_INVALID", "This file isn't a valid ZIP archive.") from exc

    with archive:
        series = _group(_scan(archive))
        total = sum(len(s.entries) for s in series)
        if total == 0:
            raise ArchiveError("ZIP_NO_IMAGES", "No DICOM slices or images were found in this ZIP.")

        slices: list[ArchiveSlice] = []
        picked_per_series: dict[str, int] = {}
        used: set[tuple[str, int]] = set()
        for s, index in select_slices(series, budget):
            n = len(s.entries)
            # Try the chosen slice, then its neighbours outward, until one decodes.
            for offset in range(n):
                candidates = [index + offset, index - offset] if offset else [index]
                converted = None
                for candidate in candidates:
                    if 0 <= candidate < n and (s.key, candidate) not in used:
                        converted = _convert(archive, s.entries[candidate])
                        if converted:
                            used.add((s.key, candidate))
                            slices.append(ArchiveSlice(converted[0], converted[1], f"{s.label} · slice {candidate + 1} of {n}"))
                            picked_per_series[s.key] = picked_per_series.get(s.key, 0) + 1
                            break
                if converted or offset > 5:
                    break

        if not slices:
            raise ArchiveError(
                "ZIP_UNREADABLE",
                "The DICOM files in this ZIP couldn't be decoded (unsupported compression).",
            )

    summary = [{"label": s.label, "slices": len(s.entries), "picked": picked_per_series.get(s.key, 0)} for s in series]
    return ArchiveResult(slices=slices, total_images=total, series=summary)
