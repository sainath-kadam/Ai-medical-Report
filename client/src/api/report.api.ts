import { api } from './axiosInstance';
import { GeneratedReportContent, Modality, Paginated, Report, ReportStatus, ReportVersion } from '../types';

export interface ReportListParams {
  page?: number;
  pageSize?: number;
  status?: ReportStatus;
  patientId?: string;
  modality?: Modality;
}

export const reportApi = {
  list: (params: ReportListParams = {}) =>
    api.get<{ success: boolean; data: Paginated<Report> }>('/reports', { params }).then((r) => r.data.data),

  getById: (id: string) => api.get<{ success: boolean; data: Report }>(`/reports/${id}`).then((r) => r.data.data),

  getVersions: (id: string) =>
    api.get<{ success: boolean; data: ReportVersion[] }>(`/reports/${id}/versions`).then((r) => r.data.data),

  // Doctor's manual edit of the current version's content. Backend appends a new version.
  update: (id: string, payload: Partial<GeneratedReportContent>) =>
    api.patch<{ success: boolean; data: Report }>(`/reports/${id}`, payload).then((r) => r.data.data),

  // Runs the AI revision inline server-side and returns once it's done, but still only
  // hands back a jobId, not the updated report -- poll GET /analysis/jobs/{jobId} (same
  // as ReportDetail.tsx already does), which resolves as "completed" right away.
  requestChanges: (id: string, instruction: string) =>
    api
      .post<{ success: boolean; data: { jobId: string } }>(`/reports/${id}/change-request`, { instruction })
      .then((r) => r.data.data),

  // Synchronous -- re-runs report GENERATION only (text-only, from the study's existing
  // findings) and appends a new version to this same report. Fast enough not to need the
  // job-queue pattern change-request uses (see server ReportService.regenerate_report).
  regenerate: (id: string) => api.post<{ success: boolean; data: Report }>(`/reports/${id}/regenerate`).then((r) => r.data.data),

  finalize: (id: string) => api.post<{ success: boolean; data: Report }>(`/reports/${id}/finalize`).then((r) => r.data.data),

  // Authenticated binary download -- fetch via the api client (carries the Bearer token)
  // and turn the blob into an object URL at the call site, rather than a plain <a href>.
  downloadPdf: (id: string) => api.get(`/reports/${id}/pdf`, { responseType: 'blob' }).then((r) => r.data as Blob),

  // Convenience string for reference/debugging only -- not fetchable directly from the
  // browser (no auth header), use downloadPdf() instead.
  downloadUrl: (id: string) => `${api.defaults.baseURL}/reports/${id}/pdf`,
};
