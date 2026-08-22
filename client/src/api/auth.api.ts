import { api } from './axiosInstance';
import { Organization, User } from '../types';

export interface AuthResponse {
  accessToken: string;
  refreshToken: string;
  user: User;
  organization?: { id: string; name: string };
}

export const authApi = {
  signup: (payload: { name: string; email: string; password: string; organizationName: string }) =>
    api.post<{ success: boolean; data: AuthResponse }>('/auth/signup', payload).then((r) => r.data.data),

  login: (payload: { email: string; password: string }) =>
    api.post<{ success: boolean; data: AuthResponse }>('/auth/login', payload).then((r) => r.data.data),

  google: (payload: { idToken: string; organizationName?: string }) =>
    api.post<{ success: boolean; data: AuthResponse }>('/auth/google', payload).then((r) => r.data.data),

  me: () => api.get<{ success: boolean; data: { user: User; organization: Organization } }>('/auth/me').then((r) => r.data.data),

  logout: (refreshToken: string) => api.post('/auth/logout', { refreshToken }),

  changePassword: (payload: { currentPassword: string; newPassword: string }) =>
    api.post('/auth/change-password', payload),

  forgotPassword: (email: string) => api.post('/auth/forgot-password', { email }),

  resetPassword: (payload: { token: string; newPassword: string }) => api.post('/auth/reset-password', payload),
};
