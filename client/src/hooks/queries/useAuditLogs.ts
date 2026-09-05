import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { auditLogApi } from '../../api/auditLog.api';
import { queryKeys } from '../../lib/queryKeys';

export interface AuditLogListParams {
  page: number;
  pageSize: number;
  action?: string;
  resourceType?: string;
}

// Audit logs are append-only history -- nothing already fetched ever changes underneath
// you, so a slightly longer window than most lists is safe.
const STALE_TIME = 45_000;

export function useAuditLogsList(params: AuditLogListParams) {
  return useQuery({
    queryKey: queryKeys.auditLogs.list(params),
    queryFn: () => auditLogApi.list(params),
    staleTime: STALE_TIME,
    placeholderData: keepPreviousData,
  });
}
