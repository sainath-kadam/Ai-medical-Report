import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { userApi } from '../../api/user.api';
import { queryKeys } from '../../lib/queryKeys';

// The org's roster changes only when someone is invited/removed/role-changed -- a
// generous window is fine.
const STALE_TIME = 60_000;

export function useUsersList(params: { page: number; pageSize: number }) {
  return useQuery({
    queryKey: queryKeys.users.list(params),
    queryFn: () => userApi.list(params),
    staleTime: STALE_TIME,
    placeholderData: keepPreviousData,
  });
}
