import { api } from './axiosInstance';
import { AnalysisJob, Modality, Paginated, Sex, Study, StudyIntakeResult, StudyStatus } from '../types';

export interface StudyListParams {
  page?: number;
  pageSize?: number;
  patientId?: string;
  status?: StudyStatus;
  modality?: Modality;
}

export interface StudyPayload {
  patientId: string;
  modality: Modality;
  bodyPart: string;
  clinicalHistory?: string;
  studyDate: string;
  referringPhysician?: string;
  templateId?: string;
}

export interface NewPatientForIntake {
  /** Optional — omitted, the server assigns a per-organization `MRN-000123`. */
  mrn?: string;
  name: string;
  dateOfBirth: string;
  sex: Sex;
  contactPhone?: string;
  contactEmail?: string;
}

export interface StudyIntakePayload {
  /** Exactly one of `patientId`/`newPatient` should be set. */
  patientId?: string;
  newPatient?: NewPatientForIntake;
  modality: Modality;
  bodyPart: string;
  clinicalHistory?: string;
  studyDate: string;
  referringPhysician?: string;
  templateId?: string;
  runAnalysis: boolean;
}

// Study files go up to 1GB (MAX_UPLOAD_MB server-side, e.g. an MRI video), and intake also
// runs AI analysis in the same request -- far past axiosInstance's 120s default -- so file
// uploads get no client timeout and report upload progress instead.
export const MAX_STUDY_FILE_BYTES = 1024 * 1024 * 1024;

function fileUploadConfig(onUploadProgress?: (percent: number) => void) {
  return {
    timeout: 0,
    onUploadProgress: onUploadProgress
      ? (event: { loaded: number; total?: number }) => {
        if (event.total) onUploadProgress(Math.round((event.loaded / event.total) * 100));
      }
      : undefined,
  };
}

export const studyApi = {
  list: (params?: StudyListParams) =>
    api.get<{ success: boolean; data: Paginated<Study> }>('/studies', { params }).then((r) => r.data.data),

  getById: (id: string) => api.get<{ success: boolean; data: Study }>(`/studies/${id}`).then((r) => r.data.data),

  create: (payload: StudyPayload) => api.post<{ success: boolean; data: Study }>('/studies', payload).then((r) => r.data.data),

  update: (id: string, payload: Partial<StudyPayload>) =>
    api.patch<{ success: boolean; data: Study }>(`/studies/${id}`, payload).then((r) => r.data.data),

  remove: (id: string) => api.delete(`/studies/${id}`),

  uploadFile: (studyId: string, file: File, onUploadProgress?: (percent: number) => void) => {
    const form = new FormData();
    form.append('file', file);
    return api
      .post<{ success: boolean; data: Study }>(`/uploads/studies/${studyId}/files`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        ...fileUploadConfig(onUploadProgress),
      })
      .then((r) => r.data.data);
  },

  runAnalysis: (studyId: string) =>
    api.post<{ success: boolean; data: { jobId: string } }>(`/analysis/studies/${studyId}/analyze`).then((r) => r.data.data),

  // One-request "new study" flow -- creates/resolves the patient, creates the study,
  // uploads the file, and (if `runAnalysis`) runs AI analysis, all in a single multipart
  // POST, instead of the old create -> upload -> analyze chain.
  intake: (payload: StudyIntakePayload, file: File, onUploadProgress?: (percent: number) => void) => {
    const form = new FormData();
    if (payload.patientId) {
      form.append('patientId', payload.patientId);
    } else if (payload.newPatient) {
      // Optional: omitted -> the server assigns a per-organization MRN.
      if (payload.newPatient.mrn) form.append('patientMrn', payload.newPatient.mrn);
      form.append('patientName', payload.newPatient.name);
      form.append('patientDateOfBirth', payload.newPatient.dateOfBirth);
      form.append('patientSex', payload.newPatient.sex);
      if (payload.newPatient.contactPhone) form.append('patientContactPhone', payload.newPatient.contactPhone);
      if (payload.newPatient.contactEmail) form.append('patientContactEmail', payload.newPatient.contactEmail);
    }
    form.append('modality', payload.modality);
    form.append('bodyPart', payload.bodyPart);
    if (payload.clinicalHistory) form.append('clinicalHistory', payload.clinicalHistory);
    form.append('studyDate', payload.studyDate);
    if (payload.referringPhysician) form.append('referringPhysician', payload.referringPhysician);
    if (payload.templateId) form.append('templateId', payload.templateId);
    form.append('runAnalysis', String(payload.runAnalysis));
    form.append('file', file);
    return api
      .post<{ success: boolean; data: StudyIntakeResult }>('/studies/intake', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        ...fileUploadConfig(onUploadProgress),
      })
      .then((r) => r.data.data);
  },

  getJob: (jobId: string) => api.get<{ success: boolean; data: AnalysisJob }>(`/analysis/jobs/${jobId}`).then((r) => r.data.data),

  // Backend returns the standard paginated envelope ({items, page, ...}), not a bare array
  // -- unwrapped here since no caller needs more than the first page (an org's per-study
  // analysis history is always small).
  getJobsForStudy: (studyId: string) =>
    api
      .get<{ success: boolean; data: Paginated<AnalysisJob> }>(`/analysis/studies/${studyId}/jobs`, { params: { pageSize: 50 } })
      .then((r) => r.data.data.items),
};
