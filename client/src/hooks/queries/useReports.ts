import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { reportApi, ReportListParams } from '../../api/report.api';
import { queryKeys } from '../../lib/queryKeys';

const STALE_TIME = 30_000;

export function useReportsList(params: ReportListParams) {
  return useQuery({
    queryKey: queryKeys.reports.list(params),
    queryFn: () => reportApi.list(params),
    staleTime: STALE_TIME,
    placeholderData: keepPreviousData,
  });
}

export function useReport(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.reports.detail(id ?? ''),
    queryFn: () => reportApi.getById(id!),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
  });
}
