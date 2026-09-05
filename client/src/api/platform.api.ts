import { api } from './axiosInstance';
import { Organization, OrganizationAccess, Paginated, User } from '../types';

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

/** An organization as the platform (system_admin) sees it: the public org, its evaluated
 * access state, usage counts, and the platform-only `accessNote`. */
export interface PlatformOrganization extends Organization {
  access: OrganizationAccess;
  userCount: number;
  reportCount: number;
  accessNote?: string | null;
  createdAt: string;
}

export interface PlatformOrganizationDetail {
  organization: PlatformOrganization;
  users: User[];
}

/** Partial update — send only the fields to change. `accessEndsAt: null` clears the manual
 * period; `isSuspended` is the hard read-only switch (CONTRACTS.md §2c). */
export interface UpdateAccessPayload {
  accessEndsAt?: string | null;
  isSuspended?: boolean;
  accessNote?: string | null;
  plan?: Organization['plan'];
}

export interface InviteSystemAdminResult extends User {
  temporaryPassword: string;
}

export const platformApi = {
  listOrganizations: (params?: { page?: number; pageSize?: number; search?: string }) =>
    api
      .get<{ success: boolean; data: Paginated<PlatformOrganization> }>('/platform/organizations', { params })
      .then((r) => r.data.data),

  getOrganization: (id: string) =>
    api
      .get<{ success: boolean; data: PlatformOrganizationDetail }>(`/platform/organizations/${id}`)
      .then((r) => r.data.data),

  updateAccess: (id: string, payload: UpdateAccessPayload) =>
    api
      .patch<{ success: boolean; data: { organization: PlatformOrganization } }>(`/platform/organizations/${id}/access`, payload)
      .then((r) => r.data.data.organization),

  createOrganization: (payload: CreateOrganizationPayload) =>
    api
      .post<{ success: boolean; data: CreateOrganizationResult }>('/platform/organizations', payload)
      .then((r) => r.data.data),

  listSystemAdmins: () =>
    api.get<{ success: boolean; data: User[] }>('/platform/system-admins').then((r) => r.data.data),

  inviteSystemAdmin: (payload: { name: string; email: string }) =>
    api
      .post<{ success: boolean; data: InviteSystemAdminResult }>('/platform/system-admins', payload)
      .then((r) => r.data.data),
};
