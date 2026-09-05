import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { platformApi } from '../../api/platform.api';
import { queryKeys } from '../../lib/queryKeys';

// A system_admin actively managing access wants to see another admin's change show up
// reasonably soon -- shorter window than most settings-like data.
const STALE_TIME = 20_000;

export function usePlatformOrganizations(params: { page: number; pageSize: number; search?: string }) {
  return useQuery({
    queryKey: queryKeys.platform.organizations(params),
    queryFn: () => platformApi.listOrganizations(params),
    staleTime: STALE_TIME,
    placeholderData: keepPreviousData,
  });
}

export function usePlatformOrganization(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.platform.organization(id ?? ''),
    queryFn: () => platformApi.getOrganization(id!),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
  });
}

export function useSystemAdmins() {
  return useQuery({
    queryKey: queryKeys.platform.systemAdmins(),
    queryFn: () => platformApi.listSystemAdmins(),
    staleTime: STALE_TIME,
  });
}
