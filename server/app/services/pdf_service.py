"""Renders a report version to a downloadable/printable PDF (spec §27), using the
organization's configured template (header/accent color/doctor-info toggles/footer
disclaimer). Ported from the original Node prototype's pdf.service.ts layout, using
reportlab's Platypus flowables instead of raw canvas calls so section text wraps properly.

Layout follows the conventional structured-radiology-report shape (facility header ->
patient/study identification block -> department/exam title -> clinical indication ->
comparison -> technique -> findings -> impression -> recommendations -> signature ->
disclaimer), matching what a radiologist would recognize from a real PACS/RIS-generated
report rather than a generic document.

Every non-finalized report gets the mandatory preliminary-report banner (spec §22/§53) —
this function does not accept a way to suppress it; that is intentional.
"""

from __future__ import annotations

import io
from datetime import date
from functools import partial
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_STATUS_LABELS = {
    "ai_generated": "AI GENERATED",
    "pending_review": "PENDING DOCTOR REVIEW",
    "draft": "DRAFT",
    "doctor_modified": "DOCTOR MODIFIED",
    "finalized": "FINALIZED",
    "amended": "AMENDED",
}

_MODALITY_LABELS = {"x_ray": "X-Ray", "ct": "CT", "mri": "MRI", "ultrasound": "Ultrasound", "other": "Other"}

# A printed hospital/RIS report conventionally opens the body by announcing which
# department read the study, in ALL CAPS, before the exam title itself. All of our defined
# modalities are radiology-department studies; "other" is the one case that isn't
# necessarily radiology, so it falls back to a more generic label.
_DEPARTMENT_LABELS = {
    "x_ray": "DEPARTMENT OF RADIO-DIAGNOSIS",
    "ct": "DEPARTMENT OF RADIO-DIAGNOSIS",
    "mri": "DEPARTMENT OF RADIO-DIAGNOSIS",
    "ultrasound": "DEPARTMENT OF RADIO-DIAGNOSIS",
}
_DEFAULT_DEPARTMENT_LABEL = "DEPARTMENT OF DIAGNOSTIC IMAGING"


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


def _age_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(str(dob)[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


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
    report_status: str,
    report_id: str,
    version_number: int,
    logo_bytes: bytes | None = None,
) -> bytes:
    accent = template.get("accentColor") or "#0E7C86"
    accent_color = colors.HexColor(accent)

    # Every style knob below falls back to the exact literal that was hardcoded here before
    # templates supported customization, so a template with no `style` data (every template
    # created before this feature existed) renders byte-for-byte as it always has.
    style = template.get("style") or {}
    header_text_color = colors.HexColor(style["headerTextColor"]) if style.get("headerTextColor") else accent_color
    content_text_color = colors.HexColor(style["contentTextColor"]) if style.get("contentTextColor") else colors.HexColor("#101828")
    font_size = style.get("fontSize") or 10.5
    background_color = colors.HexColor(style["backgroundColor"]) if style.get("backgroundColor") else None

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=font_size, leading=font_size + 4.5, textColor=content_text_color)
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading3"], textColor=accent_color, spaceAfter=4, spaceBefore=6
    )
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#475467"))
    header_meta_style = ParagraphStyle("HeaderMeta", parent=styles["Normal"], fontSize=10, textColor=header_text_color)
    org_style = ParagraphStyle("Org", parent=styles["Heading1"], textColor=header_text_color)
    label_style = ParagraphStyle("MetaLabel", parent=body_style, fontName="Helvetica-Bold", fontSize=9, leading=12)
    value_style = ParagraphStyle("MetaValue", parent=body_style, fontSize=9, leading=12)
    department_style = ParagraphStyle(
        "Department", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5,
        leading=14, alignment=TA_CENTER, textColor=content_text_color,
    )
    exam_title_style = ParagraphStyle(
        "ExamTitle", parent=styles["Heading2"], alignment=TA_CENTER, textColor=content_text_color,
        spaceBefore=2, spaceAfter=4,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    elements: list = []

    # ------------------------------------------------------------------
    # Facility header
    # ------------------------------------------------------------------
    header = template.get("header", {})
    org_name = _safe(header.get("organizationName")) or "Medical Imaging Report"
    header_text_flowables: list = [Paragraph(org_name, org_style)]
    if header.get("tagline"):
        header_text_flowables.append(Paragraph(_safe(header["tagline"]), header_meta_style))
    if header.get("contactNumber"):
        header_text_flowables.append(Paragraph(f"Tel: {_safe(header['contactNumber'])}", header_meta_style))

    logo_flowable = _logo_flowable(logo_bytes) if logo_bytes else None
    if logo_flowable:
        header_table = Table([[logo_flowable, header_text_flowables]], colWidths=[50 * mm, doc.width - 50 * mm])
        header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        elements.append(header_table)
    else:
        elements.extend(header_text_flowables)

    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=accent_color))
    elements.append(Spacer(1, 10))

    is_final = report_status == "finalized"
    banner_text = (
        "FINALIZED REPORT — reviewed and approved by a licensed physician"
        if is_final
        else "PRELIMINARY AI-ASSISTED REPORT — REQUIRES QUALIFIED MEDICAL REVIEW. Not a final diagnosis."
    )
    banner_bg = colors.HexColor("#EAF6E9") if is_final else colors.HexColor("#FFF4E5")
    banner_fg = colors.HexColor("#1E5B33") if is_final else colors.HexColor("#8A5300")
    banner_table = Table([[Paragraph(f"<b>{banner_text}</b>", ParagraphStyle("Banner", parent=body_style, textColor=banner_fg))]], colWidths=[doc.width])
    banner_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), banner_bg), ("BOX", (0, 0), (-1, -1), 0.5, banner_fg), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    elements.append(banner_table)
    elements.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Patient / study identification block -- plain label/value pairs, the way a real
    # RIS-generated report identifies the patient and study before any narrative content.
    # ------------------------------------------------------------------
    age = _age_from_dob(patient.get("dateOfBirth"))
    sex = patient.get("sex")
    sex_label = sex.capitalize() if sex and sex != "unspecified" else "—"
    age_sex = f"{age} / {sex_label}" if age is not None else sex_label
    accession = f"ACC-{report_id[:10].upper()}"

    def _id_row(label_a: str, value_a: str, label_b: str, value_b: str) -> list:
        return [
            Paragraph(f"{label_a} :", label_style),
            Paragraph(_safe(value_a) or "—", value_style),
            Paragraph(f"{label_b} :", label_style),
            Paragraph(_safe(value_b) or "—", value_style),
        ]

    id_table = Table(
        [
            _id_row("Patient Name", patient.get("name", "Unknown"), "Patient ID", patient.get("mrn", "—")),
            _id_row("Age / Sex", age_sex, "Date of Study", study.get("studyDate", "—")),
            _id_row("Reviewing Physician", doctor_name, "Accession No.", accession),
        ],
        colWidths=[38 * mm, (doc.width - 76 * mm) / 2, 38 * mm, (doc.width - 76 * mm) / 2],
    )
    # Plain "label : value" pairs, no grid lines or cell shading -- a printed hospital/RIS
    # report lays this block out as text, not a bordered form. Label column is wide enough
    # for "Reviewing Physician :", the longest label, to stay on one line.
    id_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
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
    modality_label = _MODALITY_LABELS.get(study.get("modality"), study.get("modality", "").upper())
    department_label = _DEPARTMENT_LABELS.get(study.get("modality"), _DEFAULT_DEPARTMENT_LABEL)
    exam_title = _safe(f"{modality_label} {study.get('bodyPart', '')}".strip().upper())
    elements.append(Paragraph(department_label, department_style))
    elements.append(Paragraph(f"<u>{exam_title}</u>", exam_title_style))
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
        left_label = "Electronically Verified by" if is_final else "Reported by"
        left_lines = [Paragraph(f"<b>{left_label}</b>", meta_style), Paragraph(_safe(doctor_name), body_style)]
        right_lines: list = []
        if doctor_info.get("showSignatureLine", True):
            right_lines = [
                Paragraph("_______________________________", body_style),
                Paragraph("Signature", meta_style),
            ]
        if right_lines:
            sig_table = Table([[left_lines, right_lines]], colWidths=[doc.width / 2, doc.width / 2])
            sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            elements.append(sig_table)
        else:
            elements.extend(left_lines)
    elif doctor_info.get("showSignatureLine", True):
        elements.append(Spacer(1, 24))
        elements.append(Paragraph("_______________________________", body_style))
        elements.append(Paragraph("Signature", meta_style))

    if is_final:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("Report finalized", ParagraphStyle("Finalized", parent=meta_style, textColor=colors.HexColor("#1E5B33"))))

    footer = template.get("footer", {})
    elements.append(Spacer(1, 20))
    disclaimer_style = ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#94A3B8"), alignment=1)
    disclaimer = footer.get("disclaimer") or (
        "This report was drafted with AI assistance and has been reviewed and approved by a licensed physician. "
        "It is not a substitute for independent clinical judgment."
    )
    elements.append(Paragraph(_safe(disclaimer), disclaimer_style))
    if footer.get("text"):
        elements.append(Paragraph(_safe(footer["text"]), disclaimer_style))
    elements.append(Paragraph(f"Report {_safe(report_id)} (version {version_number}) · Status: {_STATUS_LABELS.get(report_status, report_status)}", disclaimer_style))

    if background_color:
        on_page = partial(_draw_background, color=background_color)
        doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    else:
        doc.build(elements)
    return buffer.getvalue()
