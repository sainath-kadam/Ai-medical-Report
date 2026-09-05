import { Link } from 'react-router-dom';
import { FiLock } from 'react-icons/fi';
import { useAuth } from '../../../hooks/useAuth';
import { formatDate } from '../../../utils/formatDate';
import './ReadOnlyBanner.css';

/** Shown on every authenticated page while the user's organization is read-only — its
 * trial or paid/manual access period lapsed, or the platform administrator suspended it
 * (CONTRACTS.md §2c). Reads `organization.access`, which the backend evaluates and attaches
 * on /auth/me; the server refuses every write with a 402 (code = `access.reason`) in that
 * state, so this banner is the explanation, not the enforcement. */
export default function ReadOnlyBanner() {
  const { user, organization } = useAuth();
  const access = organization?.access;
  if (!access || access.writable) return null;

  const ended = access.endsAt ? ` on ${formatDate(access.endsAt)}` : '';
  let message: string;
  let hint: string;
  switch (access.reason) {
    case 'ORGANIZATION_SUSPENDED':
      message = 'Your organization\u2019s access has been suspended by the platform administrator.';
      hint = 'You can view existing records, but nothing can be created or changed until access is restored.';
      break;
    case 'ACCESS_EXPIRED':
      message = `Your organization\u2019s access period ended${ended}.`;
      hint = 'Everything is read-only until the platform administrator renews it or a subscription is started.';
      break;
    default:
      message = `Your free trial ended${ended}.`;
      hint = 'You can still view existing records. Subscribe, or ask the platform administrator, to keep working.';
  }

  return (
    <div className="read-only-banner" role="status">
      <FiLock size={18} className="read-only-banner__icon" />
      <div className="read-only-banner__text">
        <strong>{message}</strong>
        <span>{hint}</span>
      </div>
      {user?.role === 'org_admin' && access.reason !== 'ORGANIZATION_SUSPENDED' && (
        <Link to="/billing" className="read-only-banner__link">
          Go to billing
        </Link>
      )}
    </div>
  );
}
