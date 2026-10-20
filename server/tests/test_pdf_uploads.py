"""PDF uploads containing scan images: `pdf_pages.read_pdf` (page rendering, even page
spread, safety checks) and the upload/intake flow through `archive_service` (only the
rendered pages are stored, never the PDF). PDFs are generated in-test; storage is the
in-memory fake from test_video_uploads.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.utils import pdf_pages
from app.utils.dicom_archive import ArchiveError
from app.utils.pdf_pages import read_pdf

from tests.test_video_uploads import _create_study, _study_files
from tests.test_zip_uploads import storage  # noqa: F401  (fixture)

_JPEG_MAGIC = b"\xff\xd8"


def _pdf_bytes(pages: int, *, size=(800, 600)) -> bytes:
    """A PDF whose page N is a flat grey image of brightness 10*N (so pages are tellable apart)."""
    images = [Image.new("L", size, min(250, 10 * (n + 1))) for n in range(pages)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def _write(tmp_path, data: bytes, name="scan.pdf") -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _brightness(jpeg: bytes) -> float:
    image = Image.open(io.BytesIO(jpeg)).convert("L")
    return sum(image.getdata()) / (image.size[0] * image.size[1])


# --- read_pdf ------------------------------------------------------------------------------


def test_every_page_of_a_short_pdf_becomes_an_image(tmp_path):
    result = read_pdf(_write(tmp_path, _pdf_bytes(3)), budget=16)

    assert result.total_images == 3
    assert [s.label for s in result.slices] == ["Page 1 of 3", "Page 2 of 3", "Page 3 of 3"]
    assert all(s.mime_type == "image/jpeg" and s.data.startswith(_JPEG_MAGIC) for s in result.slices)
    assert [round(_brightness(s.data) / 10) for s in result.slices] == [1, 2, 3]  # right pages, in order
    assert result.series == [{"label": "PDF pages", "slices": 3, "picked": 3}]


def test_a_long_pdf_gets_pages_spread_evenly(tmp_path):
    result = read_pdf(_write(tmp_path, _pdf_bytes(20, size=(100, 100))), budget=16)

    assert len(result.slices) == 16
    numbers = [int(s.label.split()[1]) for s in result.slices]
    assert numbers == sorted(numbers) and numbers[0] == 1 and numbers[-1] == 20


def test_huge_pages_are_rendered_at_a_capped_size(tmp_path):
    result = read_pdf(_write(tmp_path, _pdf_bytes(1, size=(4000, 3000))), budget=16)

    width, height = Image.open(io.BytesIO(result.slices[0].data)).size
    assert max(width, height) <= 2000


def test_not_a_pdf(tmp_path):
    with pytest.raises(ArchiveError) as exc:
        read_pdf(_write(tmp_path, b"definitely not a pdf"), budget=16)
    assert exc.value.code == "PDF_INVALID"


def test_password_protected_pdf_is_rejected(tmp_path):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(_pdf_bytes(1))).pages:
        writer.add_page(page)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(ArchiveError) as exc:
        read_pdf(_write(tmp_path, buffer.getvalue()), budget=16)
    assert exc.value.code == "PDF_ENCRYPTED"


def test_too_many_pages_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_pages, "MAX_PDF_PAGES", 2)
    with pytest.raises(ArchiveError) as exc:
        read_pdf(_write(tmp_path, _pdf_bytes(3, size=(50, 50))), budget=16)
    assert exc.value.code == "PDF_TOO_LARGE"


# --- Upload / intake -----------------------------------------------------------------------


@pytest.mark.parametrize("content_type", ["application/pdf", "application/octet-stream"])
async def test_pdf_upload_stores_only_the_page_images(client, signup_and_login, storage, content_type):  # noqa: F811
    await signup_and_login(email=f"pdf-{content_type.split('/')[-1]}@example.com", organization_name="Pdf Clinic")
    study_id = await _create_study(client)
    data = _pdf_bytes(4)

    response = await client.post(f"/uploads/studies/{study_id}/files", files={"file": ("xray_scan.pdf", data, content_type)})

    assert response.status_code == 201, response.text
    record = (await _study_files(client, study_id))["xray_scan.pdf"]
    assert record["mimeType"] == "application/pdf"
    assert record["processingStatus"] == "slices_only"
    assert record["signedUrl"] is None  # the PDF itself isn't kept
    assert record["sizeBytes"] == len(data)
    assert len(record["frameKeys"]) == 4 and len(record["frameUrls"]) == 4
    assert record["extraction"]["source"] == "pdf"
    assert record["extraction"]["labels"] == ["Page 1 of 4", "Page 2 of 4", "Page 3 of 4", "Page 4 of 4"]
    assert sorted(storage.files) == sorted(record["frameKeys"])
    assert all(key.endswith(".jpg") for key in record["frameKeys"])

    page = await client.get(record["frameUrls"][0].removeprefix("/api/v1"))
    assert page.status_code == 200 and page.headers["content-type"] == "image/jpeg"


async def test_unreadable_pdf_upload_is_a_clear_400(client, signup_and_login, storage):  # noqa: F811
    await signup_and_login(email="pdf-bad@example.com", organization_name="Pdf Bad Clinic")
    study_id = await _create_study(client)

    response = await client.post(
        f"/uploads/studies/{study_id}/files", files={"file": ("scan.pdf", b"%PDF-broken", "application/pdf")}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PDF_INVALID"
    assert storage.files == {}


async def test_pdf_intake_runs_the_ai_on_the_pages_without_downloading_them(client, signup_and_login, storage):  # noqa: F811
    await signup_and_login(email="pdf-intake@example.com", organization_name="Pdf Intake Clinic")

    response = await client.post(
        "/studies/intake",
        data={
            "modality": "x_ray",
            "bodyPart": "Chest",
            "studyDate": "2026-10-19",
            "patientName": "Pdf Patient",
            "patientDateOfBirth": "1970-01-01",
            "patientSex": "male",
            "runAnalysis": "true",
        },
        files={"file": ("chest.pdf", _pdf_bytes(2), "application/pdf")},
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["report"]["status"] == "ai_generated"
    assert len(data["study"]["files"][0]["frameKeys"]) == 2
    assert storage.downloads == []
