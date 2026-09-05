import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '../../api/dashboard.api';
import { reportApi } from '../../api/report.api';
import { queryKeys } from '../../lib/queryKeys';

const STALE_TIME = 30_000;
const RECENT_REPORTS_PAGE_SIZE = 6;

export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboard.stats(),
    queryFn: () => dashboardApi.stats(),
    staleTime: STALE_TIME,
  });
}

export function useDashboardRecentReports() {
  return useQuery({
    queryKey: queryKeys.dashboard.recentReports(),
    queryFn: () => reportApi.list({ page: 1, pageSize: RECENT_REPORTS_PAGE_SIZE }),
    staleTime: STALE_TIME,
  });
}
