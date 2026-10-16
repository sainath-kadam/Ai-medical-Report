"""ZIP uploads (MRI/CT exports): `dicom_archive.read_archive` (safety checks, series
grouping, slice ordering, per-series selection, decode fallback) and the upload/intake/
re-analysis flow through `archive_service`. Archives are built in-test from synthetic DICOM
(pydicom) — no real patient data, no network; storage is an in-memory fake.
"""

from __future__ import annotations

import io
import random
import zipfile

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from app.utils import dicom_archive
from app.utils.dicom_archive import ArchiveError, _allocate, _spread, read_archive

from tests.test_video_uploads import _create_study, _MemoryStorage, _study_files  # noqa: F401  (fixture helpers)

_PNG_MAGIC = b"\x89PNG"


@pytest.fixture
def storage(monkeypatch):
    fake = _MemoryStorage()
    for module in (
        "app.services.upload_service",
        "app.services.analysis_service",
        "app.services.study_service",
        "app.services.report_service",
        "app.services.archive_service",
        "app.services.video_service",
        "app.api.uploads.routes",
    ):
        monkeypatch.setattr(f"{module}.get_storage", lambda: fake)
    return fake


def _dicom(series_uid: str, series_number: int, description: str, instance: int, z: float, *, corrupt=False, image_type=None) -> bytes:
    """One 8x8 MR slice whose pixel value encodes its z position (so ordering is checkable)."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MRImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.is_little_endian, ds.is_implicit_VR = True, False
    ds.SOPClassUID = MRImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "MR"
    ds.SeriesInstanceUID = series_uid
    ds.SeriesNumber = series_number
    ds.SeriesDescription = description
    ds.InstanceNumber = instance
    ds.ImagePositionPatient = [0, 0, z]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    if image_type:
        ds.ImageType = image_type
    ds.Rows = ds.Columns = 8
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.WindowCenter, ds.WindowWidth = 500, 1000
    pixels = np.full((8, 8), int(z * 10), dtype=np.uint16)
    ds.PixelData = b"\x00\x01" if corrupt else pixels.tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, write_like_original=False)
    return buffer.getvalue()


def _series(description: str, number: int, count: int, *, shuffle_names=True, **kwargs) -> dict[str, bytes]:
    """`count` slices at z=0..count-1, written under scrambled file names and instance
    numbers — so only the real position (ImagePositionPatient) gives the right order."""
    uid = generate_uid()
    order = list(range(count))
    names = order[:]
    if shuffle_names:
        random.Random(number).shuffle(names)
    return {
        f"DICOM/S{number}/IM{names[z]:04d}": _dicom(uid, number, description, names[z] + 1, float(z), **kwargs)
        for z in order
    }


def _zip(members: dict[str, bytes], path) -> str:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return str(path)


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def _slice_z(png: bytes) -> float:
    """Decodes a picked PNG slice back to the z position its pixel value encoded."""
    from PIL import Image

    value = np.asarray(Image.open(io.BytesIO(png))).mean()
    # Window 0..1000 -> 0..255 maps pixel z*10 to z*10*255/1000.
    return round(value * 1000 / 255 / 10)


# --- Selection maths ---------------------------------------------------------------------


def test_spread_centres_picks_and_skips_the_ends():
    assert _spread(100, 1) == [50]
    assert _spread(10, 4) == [1, 3, 6, 8]
    assert _spread(40, 8)[0] > 0 and _spread(40, 8)[-1] < 39


@pytest.mark.parametrize(
    ("sizes", "budget", "expected"),
    [
        ([40, 40], 16, [8, 8]),  # equal share
        ([100, 5, 3], 16, [8, 5, 3]),  # small series take all they have, the rest goes to the big one
        ([30, 20, 10], 16, [6, 5, 5]),  # remainder goes to the largest first
        ([10] * 20, 16, [1] * 16 + [0] * 4),  # more series than budget: one from each
        ([3], 16, [3]),
    ],
)
def test_allocation_spreads_the_budget_across_series(sizes, budget, expected):
    assert _allocate(sizes, budget) == expected


# --- read_archive ------------------------------------------------------------------------


def test_picks_slices_from_every_series_in_true_slice_order(tmp_path):
    members = {**_series("T1 SAG", 2, 40), **_series("T2 AX", 3, 40)}
    result = read_archive(_zip(members, tmp_path / "mri.zip"), budget=16)

    assert result.total_images == 80
    assert result.series == [
        {"label": "T1 SAG (series 2)", "slices": 40, "picked": 8},
        {"label": "T2 AX (series 3)", "slices": 40, "picked": 8},
    ]
    assert len(result.slices) == 16
    assert all(s.mime_type == "image/png" and s.data.startswith(_PNG_MAGIC) for s in result.slices)
    # Labels name the series and the true slice number; slices come out in body order even
    # though file names and instance numbers were scrambled.
    t1 = [s for s in result.slices if s.label.startswith("T1 SAG")]
    positions = [_slice_z(s.data) for s in t1]
    assert positions == sorted(positions)
    assert positions == [2, 7, 12, 17, 22, 27, 32, 37]
    assert t1[0].label == "T1 SAG (series 2) · slice 3 of 40"


def test_localizer_series_are_skipped_when_real_series_exist(tmp_path):
    members = {
        **_series("3-Plane Localizer", 1, 3),
        **_series("Survey", 4, 3),
        **_series("T2 FLAIR AX", 5, 20),
        **_series("DWI", 6, 10, image_type=["ORIGINAL", "PRIMARY", "LOCALIZER"]),
    }
    result = read_archive(_zip(members, tmp_path / "mri.zip"), budget=16)

    assert [s["label"] for s in result.series] == ["T2 FLAIR AX (series 5)"]
    assert len(result.slices) == 16


def test_only_localizers_are_still_used_rather_than_nothing(tmp_path):
    result = read_archive(_zip(_series("Localizer", 1, 3), tmp_path / "loc.zip"), budget=16)
    assert len(result.slices) == 3


def test_non_image_dicom_and_junk_files_are_ignored(tmp_path):
    dicomdir = Dataset()
    dicomdir.file_meta = FileMetaDataset()
    dicomdir.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dicomdir.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.1.3.10"
    dicomdir.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dicomdir.is_little_endian, dicomdir.is_implicit_VR = True, False
    buffer = io.BytesIO()
    dicomdir.save_as(buffer, write_like_original=False)

    members = {
        **_series("T1", 1, 5),
        "DICOMDIR": buffer.getvalue(),
        "__MACOSX/DICOM/._IM0001": b"junk",
        "DICOM/.DS_Store": b"junk",
        "README.txt": b"exported by PACS",
    }
    result = read_archive(_zip(members, tmp_path / "mri.zip"), budget=16)

    assert result.total_images == 5
    assert len(result.slices) == 5


def test_plain_images_in_folders_become_series(tmp_path):
    from PIL import Image

    def png(value):
        buffer = io.BytesIO()
        Image.new("L", (4, 4), value).save(buffer, format="PNG")
        return buffer.getvalue()

    def bmp():
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (9, 9, 9)).save(buffer, format="BMP")
        return buffer.getvalue()

    members = {f"axial/img{i}.png": png(i) for i in range(1, 11)}
    members["sagittal/slice1.bmp"] = bmp()
    result = read_archive(_zip(members, tmp_path / "imgs.zip"), budget=16)

    assert [s["label"] for s in result.series] == ["axial", "sagittal"]
    assert len(result.slices) == 11
    assert all(s.mime_type == "image/png" for s in result.slices)  # PNG kept, BMP converted


def test_compressed_dicom_is_decoded(tmp_path):
    from pydicom.data import get_testdata_file

    with open(get_testdata_file("MR_small_jpeg_ls_lossless.dcm"), "rb") as fh:
        compressed = fh.read()
    result = read_archive(_zip({"IM0001": compressed}, tmp_path / "jpegls.zip"), budget=16)

    assert len(result.slices) == 1 and result.slices[0].data.startswith(_PNG_MAGIC)


def test_undecodable_pick_is_swapped_for_a_neighbour(tmp_path):
    uid = generate_uid()
    members = {f"S/IM{z:02d}": _dicom(uid, 1, "T1", z + 1, float(z), corrupt=(z != 4)) for z in range(10)}
    result = read_archive(_zip(members, tmp_path / "mri.zip"), budget=1)  # would pick slice 6 of 10

    assert len(result.slices) == 1
    assert result.slices[0].label == "T1 (series 1) · slice 5 of 10"


def test_nothing_decodable_is_an_error(tmp_path):
    uid = generate_uid()
    members = {f"IM{z}": _dicom(uid, 1, "T1", z + 1, float(z), corrupt=True) for z in range(3)}
    with pytest.raises(ArchiveError) as exc:
        read_archive(_zip(members, tmp_path / "bad.zip"), budget=16)
    assert exc.value.code == "ZIP_UNREADABLE"


def test_not_a_zip(tmp_path):
    path = tmp_path / "fake.zip"
    path.write_bytes(b"not a zip at all")
    with pytest.raises(ArchiveError) as exc:
        read_archive(str(path), budget=16)
    assert exc.value.code == "ZIP_INVALID"


def test_zip_without_images(tmp_path):
    with pytest.raises(ArchiveError) as exc:
        read_archive(_zip({"notes.txt": b"hi", "report.pdf": b"%PDF"}, tmp_path / "docs.zip"), budget=16)
    assert exc.value.code == "ZIP_NO_IMAGES"


def test_password_protected_zip_is_rejected(tmp_path):
    path = tmp_path / "locked.zip"
    _zip(_series("T1", 1, 2), path)
    raw = bytearray(path.read_bytes())
    # Set the "encrypted" flag bit (bit 0 of the general-purpose flags) on every central
    # directory entry — signature PK\x01\x02, flags at offset 8.
    index = raw.find(b"PK\x01\x02")
    while index != -1:
        raw[index + 8] |= 0x1
        index = raw.find(b"PK\x01\x02", index + 4)
    path.write_bytes(bytes(raw))

    with pytest.raises(ArchiveError) as exc:
        read_archive(str(path), budget=16)
    assert exc.value.code == "ZIP_ENCRYPTED"


def test_too_many_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(dicom_archive, "MAX_ARCHIVE_ENTRIES", 3)
    with pytest.raises(ArchiveError) as exc:
        read_archive(_zip(_series("T1", 1, 4), tmp_path / "many.zip"), budget=16)
    assert exc.value.code == "ZIP_TOO_LARGE"


def test_zip_bomb_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(dicom_archive, "_BOMB_CHECK_MIN_BYTES", 1024 * 1024)
    monkeypatch.setattr(dicom_archive, "_MAX_COMPRESSION_RATIO", 100)
    with pytest.raises(ArchiveError) as exc:
        read_archive(_zip({"bomb.dcm": b"\x00" * (4 * 1024 * 1024)}, tmp_path / "bomb.zip"), budget=16)
    assert exc.value.code == "ZIP_INVALID"


def test_path_tricks_in_member_names_are_never_extracted(tmp_path):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("L", (4, 4), 50).save(buffer, format="PNG")
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = read_archive(_zip({"../../escape.png": buffer.getvalue()}, workdir / "evil.zip"), budget=16)

    assert len(result.slices) == 1
    assert not (tmp_path / "escape.png").exists()
    assert sorted(p.name for p in workdir.iterdir()) == ["evil.zip"]


# --- Upload / intake / re-analysis -------------------------------------------------------


@pytest.mark.parametrize("content_type", ["application/zip", "application/x-zip-compressed", "application/octet-stream"])
async def test_zip_upload_stores_only_the_picked_slices(client, signup_and_login, storage, content_type):
    await signup_and_login(email=f"zip-{content_type.split('/')[-1]}@example.com", organization_name="Zip Clinic")
    study_id = await _create_study(client)
    data = _zip_bytes({**_series("T1 SAG", 2, 30), **_series("T2 AX", 3, 30)})

    response = await client.post(f"/uploads/studies/{study_id}/files", files={"file": ("brain_mri.zip", data, content_type)})

    assert response.status_code == 201, response.text
    record = (await _study_files(client, study_id))["brain_mri.zip"]
    assert record["mimeType"] == "application/zip"
    assert record["processingStatus"] == "slices_only"
    assert record["signedUrl"] is None  # the ZIP itself isn't kept
    assert record["sizeBytes"] == len(data)
    assert len(record["frameKeys"]) == 16 and len(record["frameUrls"]) == 16
    assert record["extraction"]["totalImages"] == 60
    assert [s["picked"] for s in record["extraction"]["series"]] == [8, 8]
    assert record["extraction"]["labels"][0].startswith("T1 SAG (series 2) · slice")
    # Storage holds exactly the 16 PNG slices — no ZIP.
    assert sorted(storage.files) == sorted(record["frameKeys"])
    assert all(storage.files[k][1] == "image/png" for k in record["frameKeys"])

    slice_response = await client.get(record["frameUrls"][0].removeprefix("/api/v1"))
    assert slice_response.status_code == 200
    assert slice_response.headers["content-type"] == "image/png"


async def test_bad_zip_upload_is_a_clear_400(client, signup_and_login, storage):
    await signup_and_login(email="zip-bad@example.com", organization_name="Zip Bad Clinic")
    study_id = await _create_study(client)

    response = await client.post(
        f"/uploads/studies/{study_id}/files", files={"file": ("scan.zip", _zip_bytes({"a.txt": b"x"}), "application/zip")}
    )

    assert response.status_code == 400
    assert response.json()["error"] == {"code": "ZIP_NO_IMAGES", "message": "No DICOM slices or images were found in this ZIP."}
    assert storage.files == {}
    assert await _study_files(client, study_id) == {}


async def test_zip_intake_analyzes_slices_and_reanalysis_reads_the_same_slices(client, signup_and_login, storage):
    await signup_and_login(email="zip-intake@example.com", organization_name="Zip Intake Clinic")

    response = await client.post(
        "/studies/intake",
        data={
            "modality": "mri",
            "bodyPart": "Brain",
            "studyDate": "2026-09-01",
            "patientName": "Zip Patient",
            "patientDateOfBirth": "1970-01-01",
            "patientSex": "male",
            "runAnalysis": "true",
        },
        files={"file": ("brain.zip", _zip_bytes(_series("T2 AX", 3, 20)), "application/zip")},
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["report"]["status"] == "ai_generated"
    assert storage.downloads == []  # first analysis used the slices from the request
    frame_keys = data["study"]["files"][0]["frameKeys"]
    assert len(frame_keys) == 16

    # Re-analysis: the ZIP is gone; it reads back exactly the stored slices.
    rerun = await client.post(f"/analysis/studies/{data['study']['id']}/analyze")
    assert rerun.status_code in (200, 201, 202), rerun.text
    assert storage.downloads == frame_keys
