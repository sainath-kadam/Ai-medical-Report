import { api } from './axiosInstance';
import { AuditLog, DashboardStats } from '../types';

export const dashboardApi = {
  stats: () => api.get<{ success: boolean; data: DashboardStats }>('/dashboard/stats').then((r) => r.data.data),

  recentActivity: () =>
    api.get<{ success: boolean; data: AuditLog[] }>('/dashboard/recent-activity').then((r) => r.data.data),
};
