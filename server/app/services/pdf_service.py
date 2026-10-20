"""Renders a report version to a downloadable/printable PDF (spec §27), using the
organization's configured template (header/doctor-info toggles/footer text). Body text is
always plain/neutral (no color) — the template's `accentColor` is UI chrome only (buttons,
active states), never used here. Section headings are bold + underlined + plain black, and
the patient/study block is a bordered box, both matching a real hospital-issued report's
convention (not a stylistic accent).
Ported from the original Node prototype's pdf.service.ts layout, using reportlab's
Platypus flowables instead of raw canvas calls so section text wraps properly.

Layout follows the conventional structured-radiology-report shape (facility header ->
patient/study identification block -> department/exam title -> clinical indication ->
comparison -> technique -> findings -> impression -> recommendations -> signature ->
footer), matching what a radiologist would recognize from a real PACS/RIS-generated
report rather than a generic document.

By design, this renders identically regardless of `report status` — no AI/draft/
finalized wording or banner in the document itself, on request (see git history if that
behavior is ever needed again). Draft-vs-finalized status is only ever surfaced in the
surrounding application UI (`ReportViewer`'s toolbar), never inside the report document
or this PDF — once a PDF leaves the app there is no "surrounding UI" left to carry that
signal, so a still-unreviewed draft downloaded as a PDF is not visually distinguishable
from a finalized one. `report status` is still tracked and enforced everywhere else
(immutable once `finalized`, gates which mutations are allowed) — only this rendering no
longer reflects it.
"""

from __future__ import annotations

import io
from functools import partial
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils.patient_age import patient_age

_MODALITY_LABELS = {"x_ray": "X-Ray", "ct": "CT", "mri": "MRI", "ultrasound": "Ultrasound", "other": "Other"}

# A printed hospital/RIS report conventionally opens the body by announcing which
# department read the study, in ALL CAPS, before the exam title itself -- one universal
# label regardless of modality, matching real hospital reports (not split per-modality).
_DEPARTMENT_LABEL = "DEPARTMENT OF RADIOLOGY"


def _safe(text: Any) -> str:
    """Escapes free text (patient/study data, AI-generated content, user-entered template
    copy) before handing it to a reportlab Paragraph, which parses a light XML-like markup —
    an unescaped '&' or '<' in ordinary clinical text (e.g. "T1 & T2 sequences") would
    otherwise throw a parse error instead of rendering. Also turns newlines into <br/>, since
    plain '\\n' is whitespace to Paragraph and would collapse a numbered impression list
    ("1. ...\\n2. ...") onto one run-on line."""
    if not text:
        return ""
    return _xml_escape(str(text)).replace("\n", "<br/>")


def _logo_flowable(data: bytes, max_width: float = 42 * mm, max_height: float = 16 * mm) -> Image | None:
    """Scales a logo down to fit the header without ever upscaling a small image. Returns
    None on anything unreadable (corrupt bytes, zero-size image) so a bad logo degrades to
    "no logo" rather than a 500."""
    try:
        reader = ImageReader(io.BytesIO(data))
        width, height = reader.getSize()
        if width <= 0 or height <= 0:
            return None
        scale = min(max_width / width, max_height / height, 1.0)
        return Image(io.BytesIO(data), width=width * scale, height=height * scale)
    except Exception:
        return None


def _draw_background(canvas, doc: SimpleDocTemplate, color) -> None:
    canvas.saveState()
    canvas.setFillColor(color)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    canvas.restoreState()


def build_report_pdf(
    *,
    content: dict[str, Any],
    patient: dict[str, Any],
    study: dict[str, Any],
    template: dict[str, Any],
    doctor_name: str,
    report_id: str,
    logo_bytes: bytes | None = None,
) -> bytes:
    # Every style knob below falls back to the exact literal that was hardcoded here before
    # templates supported customization, so a template with no `style` data (every template
    # created before this feature existed) renders byte-for-byte as it always has.
    style = template.get("style") or {}
    content_text_color = colors.HexColor(style["contentTextColor"]) if style.get("contentTextColor") else colors.HexColor("#101828")
    # `accentColor` is a UI-chrome color (buttons, active states) — a standard printed
    # report doesn't use it for body text/headings, only an org's own explicit
    # `headerTextColor` customization (falling back to plain body text color, not accent).
    header_text_color = colors.HexColor(style["headerTextColor"]) if style.get("headerTextColor") else content_text_color
    font_size = style.get("fontSize") or 10.5
    background_color = colors.HexColor(style["backgroundColor"]) if style.get("backgroundColor") else None

    # One font size, one color, for every element of the report body -- a standard
    # printed report doesn't mix sizes/colors between the header, id block, headings, and
    # footer the way ad-hoc styling had drifted into doing. The only intentional
    # exception is title_size (org name + exam title), a single shared larger size for
    # the two "letterhead title" elements -- exactly like a real report's institution
    # name/exam title being bigger than its body text, still just one size between them.
    title_size = font_size * 1.7
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=font_size, leading=font_size + 4.5, textColor=content_text_color)
    heading_style = ParagraphStyle(
        "SectionHeading", parent=body_style, fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=6
    )
    meta_style = ParagraphStyle("Meta", parent=body_style)
    header_center_style = ParagraphStyle("HeaderCenter", parent=body_style, alignment=TA_CENTER)
    header_right_style = ParagraphStyle("HeaderRight", parent=body_style, alignment=TA_RIGHT)
    # Org name keeps its own text color (an org's explicit headerTextColor customization,
    # falling back to the one shared content color) -- every other element always uses
    # the shared content color, no separate customization point.
    org_style = ParagraphStyle(
        "Org", parent=body_style, fontName="Helvetica-Bold", fontSize=font_size * 1.45, leading=font_size * 1.45 + 4,
        textColor=header_text_color, alignment=TA_CENTER, spaceAfter=2,
    )
    label_style = ParagraphStyle("MetaLabel", parent=body_style, fontName="Helvetica-Bold")
    value_style = ParagraphStyle("MetaValue", parent=body_style)
    department_style = ParagraphStyle(
        "Department", parent=body_style, fontName="Helvetica-Bold", alignment=TA_CENTER,
    )
    exam_title_style = ParagraphStyle(
        "ExamTitle", parent=body_style, fontName="Helvetica-Bold", fontSize=title_size, leading=title_size + 4,
        alignment=TA_CENTER, spaceBefore=2, spaceAfter=4,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    elements: list = []
    # The frame insets its content 6pt on each side, so tables sized to `doc.width` stuck
    # out past the text and rules; size them to the frame's real content width instead.
    content_width = doc.width - 12

    # ------------------------------------------------------------------
    # Facility header
    # ------------------------------------------------------------------
    header = template.get("header", {})
    # Letterhead, three columns: the logo on the left; the organization name with the
    # tagline and address under it, centered in the middle (a long name wraps, centered);
    # the doctor's name, mobile and the hospital phone number(s) on the right.
    right_lines: list = []
    if header.get("doctorName"):
        right_lines.append(Paragraph(f"<b>{_safe(header['doctorName'])}</b>", header_right_style))
    if header.get("doctorPhone"):
        right_lines.append(Paragraph(f"Mob: {_safe(header['doctorPhone'])}", header_right_style))
    if header.get("contactNumber"):
        right_lines.append(Paragraph(f"Tel: {_safe(header['contactNumber'])}", header_right_style))
    # The right column is as wide as its longest line, so the middle gets the rest.
    right_texts = [
        (header.get("doctorName") or "", "Helvetica-Bold"),
        (f"Mob: {header.get('doctorPhone') or ''}", "Helvetica"),
        (f"Tel: {header.get('contactNumber') or ''}", "Helvetica"),
    ]
    right_width = (
        min(max(stringWidth(text, font, font_size) for text, font in right_texts) + 4 * mm, 70 * mm) if right_lines else 0
    )

    logo_flowable = _logo_flowable(logo_bytes, max_width=24 * mm, max_height=20 * mm) if logo_bytes else None
    logo_width = logo_flowable.drawWidth + 4 * mm if logo_flowable else 0

    center_lines: list = [Paragraph(_safe(header.get("organizationName")) or "Medical Imaging Report", org_style)]
    for key in ("tagline", "address"):
        if header.get(key):
            center_lines.append(Paragraph(_safe(header[key]), header_center_style))

    row = [logo_flowable or "", center_lines, right_lines or ""]
    header_table = Table([row], colWidths=[logo_width or 0.1, content_width - logo_width - right_width, right_width or 0.1])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
                ("RIGHTPADDING", (1, 0), (1, 0), 4),
            ]
        )
    )
    elements.append(header_table)

    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#101828")))
    elements.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Patient / study identification block -- plain label/value pairs in the layout of a real
    # hospital radiology report (ID/Name, Age/Sex, Referring Physician/Modality, Date/Study).
    # ------------------------------------------------------------------
    age = patient_age(patient)
    sex = patient.get("sex")
    sex_label = sex.capitalize() if sex and sex != "unspecified" else "—"
    modality_label = _MODALITY_LABELS.get(study.get("modality"), (study.get("modality") or "").upper())
    study_label = f"{modality_label} {study.get('bodyPart', '')}".strip().upper()

    def _id_row(label_a: str, value_a: str, label_b: str, value_b: str) -> list:
        return [
            Paragraph(f"{label_a}:", label_style),
            Paragraph(_safe(value_a) or "—", value_style),
            Paragraph(f"{label_b}:", label_style),
            Paragraph(_safe(value_b) or "—", value_style),
        ]

    id_table = Table(
        [
            _id_row("Patient ID", patient.get("mrn", "—"), "Patient Name", patient.get("name", "Unknown")),
            _id_row("Age", f"{age} Years" if age is not None else "—", "Sex", sex_label),
            _id_row("Referring Physician", study.get("referringPhysician") or "—", "Modality", modality_label),
            _id_row("Study Date", study.get("studyDate", "—"), "Study", study_label),
        ],
        colWidths=[42 * mm, (content_width - 84 * mm) / 2, 42 * mm, (content_width - 84 * mm) / 2],
    )
    # A bordered box around plain "label : value" pairs -- matches a real hospital/RIS
    # report's patient-identification block. Label column is wide enough for "Referring
    # Physician :", the longest label, to stay on one line.
    id_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#101828")),
            ]
        )
    )
    elements.append(id_table)
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#D0D5DD")))
    elements.append(Spacer(1, 10))

    # Centered "which department / which exact study" block -- the way a printed
    # hospital/RIS report announces the test before any narrative content, rather than a
    # small left-aligned "EXAMINATION" label.
    exam_title = _safe(study_label)
    elements.append(Paragraph(_DEPARTMENT_LABEL, department_style))
    elements.append(Paragraph(exam_title, exam_title_style))
    elements.append(Spacer(1, 4))

    if content.get("summary"):
        elements.append(Paragraph("<u>SUMMARY</u>", heading_style))
        elements.append(Paragraph(_safe(content["summary"]), body_style))
        elements.append(Spacer(1, 6))

    # ------------------------------------------------------------------
    # Template-defined body sections (Clinical Indication, Comparison, Technique, Findings,
    # any custom section an org_admin added) -- title/order/enabled all come from the
    # template, rendered in the order it defines.
    # ------------------------------------------------------------------
    ordered_sections = sorted([s for s in template.get("sections", []) if s.get("enabled", True)], key=lambda s: s.get("order", 0))
    content_by_key = {s["key"]: s for s in content.get("sections", [])}
    for section in ordered_sections:
        match = content_by_key.get(section["key"])
        if not match:
            continue
        title = match.get("title") or section["title"]
        # Uppercase the raw title before escaping, not after -- escaping first can turn a
        # special character into an entity (e.g. "&" -> "&amp;"), and upper-casing that
        # entity afterwards ("&AMP;") would render as literal text instead of "&".
        elements.append(Paragraph(f"<u>{_safe(title.upper())}</u>", heading_style))
        elements.append(Paragraph(_safe(match.get("content")) or "—", body_style))
        elements.append(Spacer(1, 6))

    if content.get("impression"):
        elements.append(Paragraph("<u>IMPRESSION</u>", heading_style))
        elements.append(Paragraph(_safe(content["impression"]), body_style))
        elements.append(Spacer(1, 6))

    if content.get("recommendations"):
        elements.append(Paragraph("<u>RECOMMENDATIONS</u>", heading_style))
        elements.append(Paragraph(_safe(content["recommendations"]), body_style))
        elements.append(Spacer(1, 6))

    # ------------------------------------------------------------------
    # Signature block
    # ------------------------------------------------------------------
    doctor_info = template.get("doctorInfo", {})
    elements.append(Spacer(1, 18))
    if doctor_info.get("showDoctorName", True):
        left_lines = [Paragraph("<b>Reported by</b>", meta_style), Paragraph(_safe(doctor_name), body_style)]
        right_lines: list = []
        if doctor_info.get("showSignatureLine", True):
            right_lines = [
                Paragraph("_______________________________", body_style),
                Paragraph("Signature", meta_style),
            ]
        if right_lines:
            sig_table = Table([[left_lines, right_lines]], colWidths=[content_width / 2, content_width / 2])
            sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            elements.append(sig_table)
        else:
            elements.extend(left_lines)
    elif doctor_info.get("showSignatureLine", True):
        elements.append(Spacer(1, 24))
        elements.append(Paragraph("_______________________________", body_style))
        elements.append(Paragraph("Signature", meta_style))

    footer = template.get("footer", {})
    elements.append(Spacer(1, 20))
    disclaimer_style = ParagraphStyle("Disclaimer", parent=body_style, alignment=1)
    if footer.get("disclaimer"):
        elements.append(Paragraph(_safe(footer["disclaimer"]), disclaimer_style))
    if footer.get("text"):
        elements.append(Paragraph(_safe(footer["text"]), disclaimer_style))

    if background_color:
        on_page = partial(_draw_background, color=background_color)
        doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    else:
        doc.build(elements)
    return buffer.getvalue()
