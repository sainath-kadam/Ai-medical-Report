import { api } from './axiosInstance';
import { OrganizationAccess } from '../types';

export interface BillingStatus {
  subscriptionStatus: 'trial' | 'active' | 'expired';
  trialEndsAt: string | null;
  // Manual access period granted by the platform administrator, if any.
  accessEndsAt: string | null;
  isSuspended: boolean;
  // The single evaluated answer to "can we write right now, until when, and why".
  access: OrganizationAccess;
  billingConfigured: boolean;
}

export const billingApi = {
  status: () => api.get<{ success: boolean; data: BillingStatus }>('/billing/status').then((r) => r.data.data),

  checkout: () =>
    api.post<{ success: boolean; data: { checkoutUrl: string } }>('/billing/checkout').then((r) => r.data.data),
};
