import { api } from './axiosInstance';

export interface BillingStatus {
  subscriptionStatus: 'trial' | 'active' | 'expired';
  trialEndsAt: string | null;
  billingConfigured: boolean;
}

export const billingApi = {
  status: () => api.get<{ success: boolean; data: BillingStatus }>('/billing/status').then((r) => r.data.data),

  checkout: () =>
    api.post<{ success: boolean; data: { checkoutUrl: string } }>('/billing/checkout').then((r) => r.data.data),
};
