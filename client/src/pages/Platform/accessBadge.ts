import { OrganizationAccess } from '../../types';

type Tone = 'info' | 'warning' | 'success' | 'danger' | 'muted';

/** One label/tone per access state, shared by the platform list and detail pages so an
 * organization never looks "Active" in one place and "Expired" in another. */
export function accessBadge(access: OrganizationAccess | undefined): { label: string; tone: Tone } {
  if (!access) return { label: 'Unknown', tone: 'muted' };
  if (!access.writable) {
    switch (access.reason) {
      case 'ORGANIZATION_SUSPENDED':
        return { label: 'Suspended', tone: 'danger' };
      case 'ACCESS_EXPIRED':
        return { label: 'Access expired', tone: 'danger' };
      default:
        return { label: 'Trial expired', tone: 'danger' };
    }
  }
  switch (access.source) {
    case 'subscription':
      return { label: 'Subscribed', tone: 'success' };
    case 'manual':
      return { label: 'Active (granted)', tone: 'success' };
    default:
      return { label: 'Free trial', tone: 'warning' };
  }
}
