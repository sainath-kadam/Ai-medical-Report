import { api } from './axiosInstance';
import { Organization, User } from '../types';

export interface CreateOrganizationPayload {
  organizationName: string;
  adminName: string;
  adminEmail: string;
}

export interface CreateOrganizationResult {
  organization: Organization;
  adminUser: User;
  temporaryPassword: string;
}

export const platformApi = {
  createOrganization: (payload: CreateOrganizationPayload) =>
    api
      .post<{ success: boolean; data: CreateOrganizationResult }>('/platform/organizations', payload)
      .then((r) => r.data.data),
};
