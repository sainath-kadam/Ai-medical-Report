import { api } from './axiosInstance';
import { AuditLog, Paginated } from '../types';

export const auditLogApi = {
  list: (params?: { page?: number; pageSize?: number; action?: string; userId?: string; resourceType?: string }) =>
    api.get<{ success: boolean; data: Paginated<AuditLog> }>('/audit-logs', { params }).then((r) => r.data.data),
};
