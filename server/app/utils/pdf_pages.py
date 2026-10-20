"""Reads a PDF that contains scan images (e.g. an X-ray/CT/MRI exported or printed to
PDF) and turns its pages into images the AI can read — the PDF counterpart of
`dicom_archive.read_archive`, returning the same `ArchiveResult`.

Each page is rendered whole (pypdfium2 — Chrome's PDF engine), so it works whether the
scan is an embedded image, a vector drawing, or a scanned page. Up to `budget` pages are
used; a longer PDF gets that many pages spread evenly through it (same spacing rule as ZIP
slices). Rendered at most `_MAX_SIDE_PX` on the longest side: enough detail for the AI,
while a page claiming absurd dimensions can't blow up memory.

A PDF is untrusted input: password-protected, unreadable, page-less or over-long
documents are rejected with a clear `ArchiveError`.
"""

from __future__ import annotations

import io

from app.utils.dicom_archive import ArchiveError, ArchiveResult, ArchiveSlice, _spread

MAX_PDF_PAGES = 500
_MAX_SIDE_PX = 2000
_JPEG_QUALITY = 92


def read_pdf(path: str, budget: int) -> ArchiveResult:
    """Synchronous (pdfium) — call it in a worker thread."""
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise ArchiveError("PDF_ENCRYPTED", "This PDF is password-protected. Upload it without a password.") from exc
        raise ArchiveError("PDF_INVALID", "This file isn't a readable PDF.") from exc

    try:
        total = len(document)
        if total == 0:
            raise ArchiveError("PDF_NO_PAGES", "This PDF has no pages.")
        if total > MAX_PDF_PAGES:
            raise ArchiveError("PDF_TOO_LARGE", f"This PDF has {total} pages; the limit is {MAX_PDF_PAGES}.")

        slices: list[ArchiveSlice] = []
        for index in _spread(total, min(budget, total)):
            page = document[index]
            try:
                width, height = page.get_size()  # in points (1/72 inch)
                scale = min(_MAX_SIDE_PX / max(width, height, 1), 3.0)
                image = page.render(scale=scale).to_pil().convert("RGB")
            except Exception:
                continue  # one unrenderable page doesn't sink the rest
            finally:
                page.close()
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
            slices.append(ArchiveSlice(buffer.getvalue(), "image/jpeg", f"Page {index + 1} of {total}"))
    finally:
        document.close()

    if not slices:
        raise ArchiveError("PDF_UNREADABLE", "The pages of this PDF couldn't be rendered.")
    return ArchiveResult(slices=slices, total_images=total, series=[{"label": "PDF pages", "slices": total, "picked": len(slices)}])
