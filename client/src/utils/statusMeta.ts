// Report-status display metadata -- the single source of truth for how the 6-value
// ReportStatus enum (CONTRACTS.md §4) is labeled/colored across the app (ReportCard,
// ReportViewer, ReportsList, etc). Study-status metadata (StudyStatus, Modality,
// AnalysisJobStatus) lives in utils/studyMeta.ts -- STUDY_STATUS_META is re-exported
// from there below so this file stays a one-stop status lookup without duplicating
// (and risking drift on) that table.
import { ReportStatus } from '../types';
import { STUDY_STATUS_META } from './studyMeta';

export type StatusTone = 'info' | 'warning' | 'success' | 'danger' | 'muted';

export const REPORT_STATUS_META: Record<ReportStatus, { label: string; tone: StatusTone }> = {
  ai_generated: { label: 'AI Generated', tone: 'info' },
  pending_review: { label: 'Pending Review', tone: 'warning' },
  draft: { label: 'Draft', tone: 'muted' },
  doctor_modified: { label: 'Doctor Modified', tone: 'info' },
  finalized: { label: 'Finalized', tone: 'success' },
  amended: { label: 'Amended', tone: 'warning' },
};

export const REPORT_STATUS_OPTIONS: { value: ReportStatus; label: string }[] = [
  { value: 'ai_generated', label: 'AI Generated' },
  { value: 'pending_review', label: 'Pending Review' },
  { value: 'draft', label: 'Draft' },
  { value: 'doctor_modified', label: 'Doctor Modified' },
  { value: 'finalized', label: 'Finalized' },
  { value: 'amended', label: 'Amended' },
];

export { STUDY_STATUS_META };
