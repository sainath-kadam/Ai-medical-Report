"""Clinical instructions shared by every AI provider (Gemini, Anthropic) — what to look for
and how thoroughly, kept in one place so both providers read scans and write reports the
same way.

Why this exists: physician feedback on live reports was that the major findings were
right but the small ones — subtle, minor, incidental, and pertinent normals — were
missing. The original imaging instruction was a single line ("return discrete, neutral
observations"), so the model reported the obvious finding and stopped. A radiologist
works through a systematic search pattern for the modality and region and dictates every
finding, small ones included; these instructions ask the model to do the same, and the
report step to carry every one of those findings through to the report.
"""

from __future__ import annotations

import re

# Systematic search patterns, chosen by body part / modality keywords (first match wins: spine, then bones/joints — so "femoral head" isn't read as a
# brain — then chest, brain, abdomen). Each is the
# region-by-region checklist a radiologist works through so nothing is skipped.
_CHECKLISTS: list[tuple[tuple[str, ...], str]] = [
    (
        ("spine", "spinal", "cervical", "lumbar", "thoracic spine", "sacral", "vertebra", "disc"),
        "Alignment (lordosis/kyphosis, scoliosis, listhesis with grade); vertebral body heights (fractures) and "
        "marrow signal; EACH disc level individually (desiccation, height loss, bulge/protrusion/extrusion and "
        "its direction); central canal stenosis per level; neural foramina per level AND side; facet joints and "
        "ligamentum flavum; cord/conus signal and position; paraspinal soft tissues; incidental findings in the "
        "field of view (e.g. renal cysts, aortic calibre).",
    ),
    (
        ("knee", "shoulder", "hip", "femoral", "ankle", "foot", "hand", "wrist", "elbow", "joint", "femur", "tibia",
         "humerus", "forearm", "radius", "ulna", "fibula", "bone", "extremity", "limb", "leg", "arm", "finger", "toe"),
        "Alignment and dislocation; fractures — check every cortex, including subtle and non-displaced "
        "lines; joint spaces; effusion; bone density and focal lesions; degenerative change (osteophytes, "
        "subchondral sclerosis/cysts, joint-space narrowing); soft-tissue swelling, calcifications, gas or "
        "foreign bodies; on MRI also ligaments, tendons, menisci/labrum, cartilage and marrow oedema.",
    ),
    (
        ("chest", "lung", "thorax", "thoracic", "rib", "cardiac", "heart"),
        "Technique (projection, rotation, inspiration, penetration); lines, tubes and devices; trachea and "
        "mediastinum (width, shift); heart size and contour; hila; each lung zone on BOTH sides — upper, mid, "
        "lower (opacities, nodules, consolidation, atelectasis, interstitial markings, hyperinflation, "
        "cavities); pleura (effusion — including blunted costophrenic angles, thickening, pneumothorax); "
        "diaphragm and below it (free air, bowel gas); bones (ribs, clavicles, spine, shoulders — fractures, "
        "lesions, degenerative change); soft tissues (subcutaneous emphysema, masses); and the classic "
        "review areas where small findings hide: apices, retrocardiac, behind the diaphragm, hila.",
    ),
    (
        ("brain", "head", "skull", "cranial", "intracranial"),
        "Technique/sequences; ventricles and sulci (size, symmetry, hydrocephalus, atrophy for age); midline "
        "shift, mass effect, herniation; grey-white matter differentiation; parenchymal lesions lobe by lobe "
        "(density/signal, restricted diffusion if DWI shown, enhancement if contrast shown); white-matter "
        "hyperintensities and their extent; haemorrhage or infarct (age if possible); extra-axial spaces "
        "(subdural, epidural, subarachnoid); posterior fossa (cerebellum, brainstem, fourth ventricle); "
        "sella/pituitary; vascular flow voids; calvarium and skull base; orbits; and the often-missed "
        "incidental areas — paranasal sinuses (mucosal thickening, fluid levels) and mastoid air cells.",
    ),
    (
        ("abdomen", "abdominal", "pelvis", "pelvic", "liver", "kidney", "renal", "gallbladder", "pancrea",
         "spleen", "bladder", "bowel", "appendix", "kub", "uterus", "ovary", "prostate"),
        "Liver (size, texture, focal lesions); gallbladder and bile ducts (stones, wall, dilatation); pancreas; "
        "spleen; adrenals; kidneys, ureters and bladder (size, stones, hydronephrosis, cysts, masses); bowel and "
        "appendix (wall, dilatation, obstruction); mesentery and lymph nodes; vessels (aortic calibre, "
        "calcification); free fluid or free air; pelvic organs; abdominal wall (hernias); visible lung bases; "
        "bones (lesions, degenerative change).",
    ),
]

_ULTRASOUND_CHECKLIST = (
    "For each organ or structure shown: size, echotexture and margins; focal lesions (size, echogenicity, "
    "vascularity if Doppler shown); fluid or collections; stones; duct or vessel calibre; and read any "
    "on-screen calipers, measurements and labels — report the measured values."
)

_GENERIC_CHECKLIST = (
    "Every structure visible in the image, region by region from one edge to the other; devices and lines; "
    "bones; soft tissues; and the edges and corners of the image, where small findings are easy to miss."
)


def _checklist(modality: str, body_part: str) -> str:
    """First matching region wins (spine before chest, so "thoracic spine" gets the spine
    pattern). Keywords match at the start of a word, so "arm" doesn't match "forearm"-like
    substrings of unrelated words and "renal" doesn't match inside another word."""
    part = (body_part or "").lower()
    for keywords, checklist in _CHECKLISTS:
        if any(re.search(rf"\b{re.escape(word)}", part) for word in keywords):
            return checklist
    if (modality or "").lower() == "ultrasound":
        return _ULTRASOUND_CHECKLIST
    return _GENERIC_CHECKLIST


def imaging_instructions(modality: str, body_part: str) -> str:
    """What the image-reading step is asked to do — appended to each provider's safety
    preamble."""
    return (
        " Read the images like an experienced radiologist dictating a complete report: thorough, systematic, "
        "and specific. Do not stop at the most obvious finding.\n\n"
        f"Work through this search pattern for {body_part or 'the region'} ({modality or 'imaging'}), item by "
        f"item: {_checklist(modality, body_part)}\n\n"
        "Return EVERY finding as its own observation — including small, subtle, mild, chronic, degenerative and "
        "incidental ones (e.g. a small nodule, minimal effusion, mild degenerative change, a calcification, "
        "sinus mucosal thickening). For each abnormal finding give: exact location and side (lobe/segment, "
        "level, quadrant, left/right), approximate size when it can be judged (say it is approximate — never "
        "invent a precise measurement; report on-image measurements as shown), character, severity "
        "(mild/moderate/severe), and how confident you are (definite / probable / possible / cannot exclude).\n\n"
        "Start every observation with one tag, then the finding:\n"
        "[Major] — clinically significant, needs attention;\n"
        "[Minor] — real but less significant (mild, small, early, chronic);\n"
        "[Incidental] — unrelated to the clinical question but worth recording;\n"
        "[Normal] — a pertinent normal for this region and clinical question (e.g. 'No pneumothorax', 'No "
        "fracture'); include the key ones a physician would expect to see stated;\n"
        "[Technique] — image quality or coverage limits that restrict assessment.\n"
        "Order: [Major] first, then [Minor], [Incidental], [Normal], [Technique]. When several images or "
        "slices are attached, say when a finding is seen on only some of them. Read any text, labels, "
        "annotations or measurements printed on the images. Still never fabricate: if something cannot be "
        "assessed on these images, say so as a [Technique] observation rather than guessing.\n\n"
        "Do not write a full report or impression — that happens in a separate step. If the source is not a "
        "directly viewable, interpretable image, set analyzable=false and explain why instead of fabricating "
        "observations."
    )


# Appended to each provider's report-writing system prompt.
REPORT_DETAIL_RULES = (
    "Completeness is the priority: the physician needs every finding, not only the main one. Include EVERY "
    "observation from the image analysis in the report — no finding may be dropped, merged away or "
    "generalised, including [Minor] and [Incidental] ones. Do not copy the bracketed tags into the report; "
    "use them to decide emphasis and order.\n"
    "Findings: organise region by region (systematically), state each abnormal finding with its location, "
    "side, approximate size and severity exactly as given, and include the pertinent normals. Mention "
    "[Technique] limitations where they restrict assessment.\n"
    "Impression: a numbered list (1., 2., 3., … each on its own line) — significant findings first, then "
    "minor and incidental ones, each in one concise line. Never call the study normal or unremarkable if any abnormal finding was reported.\n"
    "Recommendations: specific to the findings (clinical correlation, comparison with prior imaging, "
    "follow-up or further imaging where a finding warrants it), without inventing details that are not "
    "supported by the findings."
)
