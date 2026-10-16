import { api } from './axiosInstance';
import { DashboardStats } from '../types';

export const dashboardApi = {
  stats: () => api.get<{ success: boolean; data: DashboardStats }>('/dashboard/stats').then((r) => r.data.data),

};
