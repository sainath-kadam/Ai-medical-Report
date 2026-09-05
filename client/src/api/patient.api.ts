import { api } from './axiosInstance';
import { Paginated, Patient, Study } from '../types';

const STUDIES_PAGE_SIZE = 100;

export interface PatientListParams {
  page?: number;
  pageSize?: number;
  search?: string;
}

export interface PatientPayload {
  /** Optional — omitted, the server assigns a per-organization `MRN-000123`. */
  mrn?: string;
  name: string;
  dateOfBirth?: string;
  sex?: Patient['sex'];
  contactPhone?: string;
  contactEmail?: string;
}

export const patientApi = {
  list: (params?: PatientListParams) =>
    api.get<{ success: boolean; data: Paginated<Patient> }>('/patients', { params }).then((r) => r.data.data),

  getById: (id: string) => api.get<{ success: boolean; data: Patient }>(`/patients/${id}`).then((r) => r.data.data),

  create: (payload: PatientPayload) =>
    api.post<{ success: boolean; data: Patient }>('/patients', payload).then((r) => r.data.data),

  update: (id: string, payload: Partial<PatientPayload>) =>
    api.patch<{ success: boolean; data: Patient }>(`/patients/${id}`, payload).then((r) => r.data.data),

  remove: (id: string) => api.delete(`/patients/${id}`),

  // Backend returns the standard paginated envelope ({items, page, ...}) -- unwrapped to a
  // flat array here since PatientDetail renders a patient's studies as one plain list with
  // no pagination UI (a single patient rarely has more than a handful of studies).
  getStudies: (id: string) =>
    api
      .get<{ success: boolean; data: Paginated<Study> }>(`/patients/${id}/studies`, { params: { pageSize: STUDIES_PAGE_SIZE } })
      .then((r) => r.data.data.items),
};
