import { useQuery } from '@tanstack/react-query';
import { billingApi } from '../../api/billing.api';
import { queryKeys } from '../../lib/queryKeys';

// Shorter than most: this drives the read-only/trial-expiry messaging (CONTRACTS.md §2c),
// and a platform admin granting access, or a Stripe webhook landing, should show up on
// this page again reasonably soon without a hard refresh.
const STALE_TIME = 15_000;

export function useBillingStatus() {
  return useQuery({
    queryKey: queryKeys.billing.status(),
    queryFn: () => billingApi.status(),
    staleTime: STALE_TIME,
  });
}
