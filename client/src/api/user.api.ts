import { api } from './axiosInstance';
import { Paginated, User, UserRole } from '../types';

export interface CreateUserPayload {
  name: string;
  email: string;
  role: UserRole;
}

export interface CreateUserResult {
  user: User;
  temporaryPassword: string;
}

export const userApi = {
  list: (params?: { page?: number; pageSize?: number; search?: string }) =>
    api.get<{ success: boolean; data: Paginated<User> }>('/users', { params }).then((r) => r.data.data),

  getById: (id: string) => api.get<{ success: boolean; data: User }>(`/users/${id}`).then((r) => r.data.data),

  create: (payload: CreateUserPayload) =>
    api.post<{ success: boolean; data: CreateUserResult }>('/users', payload).then((r) => r.data.data),

  update: (id: string, payload: Partial<Pick<User, 'name' | 'role' | 'isActive'>>) =>
    api.patch<{ success: boolean; data: User }>(`/users/${id}`, payload).then((r) => r.data.data),

  remove: (id: string) => api.delete<{ success: boolean; data: null }>(`/users/${id}`).then((r) => r.data.data),
};
