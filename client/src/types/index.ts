// Wire types for the FastAPI backend (see server/../CONTRACTS.md — this file is the
// frontend half of that same contract). Every entity uses `id` (string), never `_id`.

// system_admin is a platform-wide account (CONTRACTS.md §2a) — the one role not scoped to
// a single organization, used only to onboard new organizations (see pages/Platform/).
export type UserRole = 'org_admin' | 'doctor' | 'system_admin';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatarUrl?: string;
  // null only for role="system_admin" — every other role always belongs to one org.
  organizationId: string | null;
  isActive?: boolean;
}

// What currently lets an organization write: a paid Stripe subscription, a manual access
// period a system_admin granted, the free trial, or nothing (read-only).
export type AccessSource = 'subscription' | 'manual' | 'trial' | 'none';
export type AccessReason = 'ORGANIZATION_SUSPENDED' | 'ACCESS_EXPIRED' | 'TRIAL_EXPIRED';

/** Evaluated server-side (server/app/core/subscription.py::evaluate_access) and attached to
 * the organization on /auth/me, /organizations/me, /billing/status and every platform
 * response — the client never re-derives trial/Stripe/manual precedence itself. While
 * `writable` is false every POST/PATCH/DELETE on clinical routes returns 402 with `reason`
 * as the error code; reading and logging in keep working (CONTRACTS.md §2c). */
export interface OrganizationAccess {
  writable: boolean;
  reason: AccessReason | null;
  source: AccessSource;
  endsAt: string | null;
}

export interface Organization {
  id: string;
  name: string;
  logoUrl?: string;
  address?: string;
  contactEmail?: string;
  contactPhone?: string;
  website?: string;
  plan: 'free' | 'pro' | 'enterprise';
  highAccuracyMode: boolean;
  reportHeader?: string;
  reportFooter?: string;
  primaryColor?: string;
  subscriptionStatus?: 'trial' | 'active' | 'expired';
  trialEndsAt?: string | null;
  // Platform-managed access (set only by a system_admin) — see OrganizationAccess.
  accessEndsAt?: string | null;
  isSuspended?: boolean;
  createdAt?: string;
  access?: OrganizationAccess;
}

export interface TemplateSection {
  key: string;
  title: string;
  order: number;
  enabled: boolean;
  guidance?: string;
}

export interface TemplateStyle {
  headerTextColor?: string;
  backgroundColor?: string;
  contentTextColor?: string;
  fontSize?: number;
}

export interface ReportTemplate {
  id: string;
  name: string;
  isDefault: boolean;
  // `logoKey` is the storage key sent on create/update; `logoUrl` is a short-lived signed
  // URL computed fresh by the backend on every read -- never write it back on save.
  header: { organizationName: string; logoKey?: string | null; logoUrl?: string; tagline?: string; contactNumber?: string };
  doctorInfo: { showDoctorName: boolean; showSignatureLine: boolean; showRegistrationNo: boolean };
  sections: TemplateSection[];
  footer: { text: string; disclaimer: string };
  accentColor: string;
  style: TemplateStyle;
}

export type Sex = 'male' | 'female' | 'other' | 'unspecified';

export interface Patient {
  id: string;
  mrn: string;
  name: string;
  dateOfBirth?: string;
  sex?: Sex;
  contactPhone?: string;
  contactEmail?: string;
  createdAt: string;
}

export type Modality = 'x_ray' | 'ct' | 'mri' | 'ultrasound' | 'other';
export type StudyStatus = 'uploaded' | 'processing' | 'completed' | 'failed';

export interface StudyFile {
  id: string;
  fileName: string;
  mimeType: string;
  sizeBytes: number;
  uploadedAt: string;
  signedUrl?: string;
}

export interface StudyFindings {
  observations: string[];
  rawSummary: string;
  analyzable: boolean;
  unanalyzableReason?: string;
}

export interface Study {
  id: string;
  patientId: string;
  patient?: Patient;
  modality: Modality;
  bodyPart: string;
  clinicalHistory?: string;
  studyDate: string;
  referringPhysician?: string;
  status: StudyStatus;
  assignedDoctorId?: string;
  templateId?: string;
  files: StudyFile[];
  lastFindings?: StudyFindings;
  createdAt: string;
}

export type AnalysisJobStatus =
  | 'queued'
  | 'preprocessing'
  | 'analyzing'
  | 'generating_report'
  | 'ready_for_review'
  | 'completed'
  | 'failed';

export interface AnalysisJob {
  id: string;
  studyId: string;
  status: AnalysisJobStatus;
  provider?: string;
  imagingModel?: string;
  reportModel?: string;
  error?: string;
  errorCode?: string;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
}

export type ReportStatus = 'ai_generated' | 'pending_review' | 'draft' | 'doctor_modified' | 'finalized' | 'amended';

export interface ReportSectionContent {
  key: string;
  title: string;
  content: string;
}

export interface GeneratedReportContent {
  summary: string;
  sections: ReportSectionContent[];
  impression: string;
  recommendations: string;
}

export interface ReportVersion {
  versionNumber: number;
  content: GeneratedReportContent;
  author: 'ai' | string;
  generatedAt: string;
  changeRequestNote?: string;
  aiModelUsed?: string;
}

export interface Report {
  id: string;
  studyId: string;
  study?: Study;
  templateId: string;
  template?: ReportTemplate;
  versions: ReportVersion[];
  currentVersion: number;
  status: ReportStatus;
  finalizedBy?: string;
  finalizedAt?: string;
  createdAt: string;
}

export interface StudyIntakeResult {
  study: Study;
  report: Report | null;
  analysisJobId: string | null;
}

export interface AuditLog {
  id: string;
  userId: string;
  action: string;
  resourceType: string;
  resourceId?: string;
  metadata?: Record<string, unknown>;
  createdAt: string;
}

export interface DashboardStats {
  totalStudies: number;
  pendingReview: number;
  aiProcessing: number;
  completedReports: number;
  reportsThisWeek: number;
  reportsThisMonth: number;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}
