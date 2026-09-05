import { useQuery } from '@tanstack/react-query';
import { organizationApi } from '../../api/organization.api';
import { queryKeys } from '../../lib/queryKeys';

// Branding/profile settings -- rarely changes minute to minute.
const STALE_TIME = 60_000;

export function useMyOrganization() {
  return useQuery({
    queryKey: queryKeys.organization.mine(),
    queryFn: () => organizationApi.getMine(),
    staleTime: STALE_TIME,
  });
}
