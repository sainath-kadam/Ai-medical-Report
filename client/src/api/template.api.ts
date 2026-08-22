import { api } from './axiosInstance';
import { Paginated, ReportTemplate } from '../types';

export const templateApi = {
  // Backend returns the standard paginated envelope ({items, page, ...}) — unwrapped to a
  // flat array here since an organization's template list is always small enough that no
  // page of this app needs to paginate it (pageSize defaults to 20 on the backend).
  list: () =>
    api.get<{ success: boolean; data: Paginated<ReportTemplate> }>('/templates', { params: { pageSize: 100 } }).then((r) => r.data.data.items),

  getById: (id: string) => api.get<{ success: boolean; data: ReportTemplate }>(`/templates/${id}`).then((r) => r.data.data),

  create: (payload: Partial<ReportTemplate>) =>
    api.post<{ success: boolean; data: ReportTemplate }>('/templates', payload).then((r) => r.data.data),

  update: (id: string, payload: Partial<ReportTemplate>) =>
    api.patch<{ success: boolean; data: ReportTemplate }>(`/templates/${id}`, payload).then((r) => r.data.data),

  remove: (id: string) => api.delete(`/templates/${id}`),

  // Backend has no dedicated /default sub-route (see CONTRACTS.md §9) — setting a
  // template as default is just a regular partial update.
  setDefault: (id: string) => templateApi.update(id, { isDefault: true }),

  uploadLogo: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api
      .post<{ success: boolean; data: { logoKey: string; logoUrl: string } }>('/templates/logo', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data.data);
  },

  // Stateless render of a (possibly unsaved) draft's sections/style/logo through a sample
  // report -- mirrors reportApi.downloadPdf's blob pattern. Powers the live preview panel
  // in the template editor and the "which template will this study use" preview in
  // NewStudyForm.
  previewPdf: (payload: Partial<ReportTemplate>) =>
    api.post('/templates/preview-pdf', payload, { responseType: 'blob' }).then((r) => r.data as Blob),
};
