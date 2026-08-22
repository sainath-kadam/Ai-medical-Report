import { useEffect, useState } from 'react';
import { FiAlertTriangle, FiCheckCircle, FiClock, FiCreditCard } from 'react-icons/fi';
import { billingApi, BillingStatus } from '../../api/billing.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import { formatDate } from '../../utils/formatDate';
import './Billing.css';

const STATUS_META: Record<BillingStatus['subscriptionStatus'], { label: string; tone: 'success' | 'warning' | 'danger' }> = {
  active: { label: 'Active subscription', tone: 'success' },
  trial: { label: 'Free trial', tone: 'warning' },
  expired: { label: 'Trial expired', tone: 'danger' },
};

function daysRemaining(trialEndsAt: string | null): number | null {
  if (!trialEndsAt) return null;
  const ms = new Date(trialEndsAt).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

export default function Billing() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    billingApi
      .status()
      .then(setStatus)
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  async function handleSubscribe() {
    setIsCheckingOut(true);
    setError('');
    try {
      const { checkoutUrl } = await billingApi.checkout();
      window.location.href = checkoutUrl;
    } catch (err) {
      setError(apiErrorMessage(err));
      setIsCheckingOut(false);
    }
  }

  if (isLoading) {
    return (
      <div className="billing-page__loading">
        <Loader size="lg" label="Loading billing status…" />
      </div>
    );
  }

  return (
    <div className="billing-page">
      <div className="billing-page__header">
        <h1>Billing</h1>
        <p>Your organization's subscription and trial status.</p>
      </div>

      {error && <div className="billing-page__error">{error}</div>}

      {status && (
        <Card className="billing-page__status-card">
          <div className="billing-page__status-row">
            <span className="billing-page__status-label">Status</span>
            <StatusBadge label={STATUS_META[status.subscriptionStatus].label} tone={STATUS_META[status.subscriptionStatus].tone} />
          </div>

          {status.subscriptionStatus === 'active' && (
            <div className="billing-page__active-note">
              <FiCheckCircle size={18} />
              <span>Your organization has an active subscription — AI report generation is unlimited.</span>
            </div>
          )}

          {status.subscriptionStatus === 'trial' && status.trialEndsAt && (
            <div className="billing-page__trial-note">
              <FiClock size={18} />
              <span>
                {daysRemaining(status.trialEndsAt)} day{daysRemaining(status.trialEndsAt) === 1 ? '' : 's'} left in your free
                trial (ends {formatDate(status.trialEndsAt)}).
              </span>
            </div>
          )}

          {status.subscriptionStatus === 'expired' && (
            <div className="billing-page__expired-note">
              <FiAlertTriangle size={18} />
              <span>Your free trial has ended. Subscribe to keep generating AI reports.</span>
            </div>
          )}

          {status.subscriptionStatus !== 'active' && (
            <>
              {status.billingConfigured ? (
                <Button icon={<FiCreditCard size={16} />} onClick={handleSubscribe} isLoading={isCheckingOut} size="lg">
                  Subscribe now
                </Button>
              ) : (
                <p className="billing-page__not-configured">
                  Payment is not configured for this deployment yet — contact your platform administrator to enable
                  subscriptions.
                </p>
              )}
            </>
          )}
        </Card>
      )}
    </div>
  );
}
