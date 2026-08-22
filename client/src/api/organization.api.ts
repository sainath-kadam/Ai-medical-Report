import { api } from './axiosInstance';
import { Organization } from '../types';

export const organizationApi = {
  getMine: () =>
    api.get<{ success: boolean; data: { organization: Organization } }>('/organizations/me').then((r) => r.data.data),

  update: (payload: Partial<Organization>) =>
    api.patch<{ success: boolean; data: { organization: Organization } }>('/organizations/me', payload).then((r) => r.data.data.organization),
};
