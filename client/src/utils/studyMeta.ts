// Small shared lookup tables for the Studies feature (list + detail pages, and the
// New study modal). Kept in a separate file from utils/statusMeta.ts purely by domain --
// that file covers the Reports feature's `ReportStatus`, this one covers Studies'
// `StudyStatus` / `Modality` / `AnalysisJobStatus`. statusMeta.ts re-exports
// STUDY_STATUS_META from here so callers that need both still have one import.
import { AnalysisJobStatus, Modality, StudyStatus } from '../types';

type Tone = 'info' | 'warning' | 'success' | 'danger' | 'muted';

export const STUDY_STATUS_META: Record<StudyStatus, { label: string; tone: Tone }> = {
  uploaded: { label: 'Uploaded', tone: 'muted' },
  processing: { label: 'AI Processing…', tone: 'info' },
  completed: { label: 'Completed', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

export const STUDY_STATUS_OPTIONS: { value: StudyStatus; label: string }[] = [
  { value: 'uploaded', label: 'Uploaded' },
  { value: 'processing', label: 'AI Processing' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
];

export const MODALITY_LABELS: Record<Modality, string> = {
  x_ray: 'X-Ray',
  ct: 'CT',
  mri: 'MRI',
  ultrasound: 'Ultrasound',
  other: 'Other',
};

export const MODALITY_OPTIONS: { value: Modality; label: string }[] = [
  { value: 'x_ray', label: 'X-Ray' },
  { value: 'ct', label: 'CT' },
  { value: 'mri', label: 'MRI' },
  { value: 'ultrasound', label: 'Ultrasound' },
  { value: 'other', label: 'Other' },
];

// Ordered pipeline for the analysis-job progress stepper on StudyDetail. `failed` is
// deliberately excluded -- it's rendered as an error state instead of a stepper position.
export const ANALYSIS_JOB_STAGES: { status: AnalysisJobStatus; label: string }[] = [
  { status: 'queued', label: 'Queued' },
  { status: 'preprocessing', label: 'Preprocessing' },
  { status: 'analyzing', label: 'Analyzing imaging' },
  { status: 'generating_report', label: 'Generating report' },
  { status: 'ready_for_review', label: 'Ready for review' },
  { status: 'completed', label: 'Completed' },
];

export const ANALYSIS_JOB_STATUS_META: Record<AnalysisJobStatus, { label: string; tone: Tone }> = {
  queued: { label: 'Queued', tone: 'muted' },
  preprocessing: { label: 'Preprocessing…', tone: 'info' },
  analyzing: { label: 'Analyzing imaging…', tone: 'info' },
  generating_report: { label: 'Generating report…', tone: 'info' },
  ready_for_review: { label: 'Ready for review', tone: 'warning' },
  completed: { label: 'Completed', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

// Per the task brief: stop polling once the job reaches any of these three statuses.
export const TERMINAL_JOB_STATUSES: AnalysisJobStatus[] = ['completed', 'failed', 'ready_for_review'];
