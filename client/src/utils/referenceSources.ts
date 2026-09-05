// Curated clinical reference reading shown alongside a generated report (ReportWorkspace's
// "Reference sources" card). NOT a record of what the AI itself consulted -- the imaging/
// report providers (server/app/ai/) only read the uploaded image and the clinical history
// typed into the study, with no web retrieval -- so these are real, verified pages picked to
// match this specific study's modality and body part, landing a reviewing clinician on the
// exact relevant page instead of a generic homepage. Every URL below was checked to resolve
// before being hardcoded here; if a site restructures, re-verify before changing a link.
import { Modality } from '../types';
import { MODALITY_LABELS } from './studyMeta';

export interface ReferenceSource {
  label: string;
  url: string;
}

const RADIOLOGYINFO_MODALITY_URL: Partial<Record<Modality, string>> = {
  x_ray: 'https://www.radiologyinfo.org/en/x-ray',
  ct: 'https://www.radiologyinfo.org/en/ctscan',
  mri: 'https://www.radiologyinfo.org/en/mri',
  ultrasound: 'https://www.radiologyinfo.org/en/ultrasound',
};

const MEDLINEPLUS_MODALITY: Partial<Record<Modality, { url: string; label: string }>> = {
  x_ray: { url: 'https://medlineplus.gov/xrays.html', label: 'X-Rays' },
  ct: { url: 'https://medlineplus.gov/ctscans.html', label: 'CT Scans' },
  mri: { url: 'https://medlineplus.gov/mriscans.html', label: 'MRI Scans' },
  ultrasound: { url: 'https://medlineplus.gov/ultrasound.html', label: 'Ultrasound' },
};

/** 4 general resources every study gets, plus (when known) a modality overview from two
 *  different publishers and an ACR Appropriateness Criteria search scoped to the exact
 *  body part -- typically 6-7 entries total, 4-5 for an unrecognized/"other" modality. */
export function getReferenceSources(modality: Modality | undefined, bodyPart: string | undefined): ReferenceSource[] {
  const sources: ReferenceSource[] = [
    {
      label: 'RadiologyInfo.org — How to Read Your Radiology Report',
      url: 'https://www.radiologyinfo.org/en/radiology-reports',
    },
    { label: 'MedlinePlus — Diagnostic Imaging overview', url: 'https://medlineplus.gov/diagnosticimaging.html' },
    {
      label: 'ACR Appropriateness Criteria — guidelines hub',
      url: 'https://www.acr.org/Clinical-Resources/ACR-Appropriateness-Criteria',
    },
    { label: 'Image Wisely (ACR/RSNA/ASRT/AAPM) — imaging safety', url: 'https://www.imagewisely.org/' },
  ];

  const radiologyInfoUrl = modality && RADIOLOGYINFO_MODALITY_URL[modality];
  if (radiologyInfoUrl) {
    sources.push({ label: `RadiologyInfo.org — ${MODALITY_LABELS[modality]}`, url: radiologyInfoUrl });
  }

  const medlinePlus = modality && MEDLINEPLUS_MODALITY[modality];
  if (medlinePlus) {
    sources.push({ label: `MedlinePlus — ${medlinePlus.label}`, url: medlinePlus.url });
  }

  const trimmedBodyPart = bodyPart?.trim();
  if (trimmedBodyPart) {
    sources.push({
      label: `ACR Appropriateness Criteria — search results for "${trimmedBodyPart}"`,
      url: `https://acsearch.acr.org/list?query=${encodeURIComponent(trimmedBodyPart)}`,
    });
  }

  return sources;
}
