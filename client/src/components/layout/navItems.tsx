import { IconType } from 'react-icons';
import { FiHome, FiUsers, FiFilePlus, FiFileText, FiLayers, FiUserCheck, FiBriefcase, FiShield, FiGlobe, FiCreditCard } from 'react-icons/fi';
import { UserRole } from '../../types';
import { SKIP_AUTH } from '../../utils/devFlags';

export interface NavItem {
  to: string;
  label: string;
  icon: IconType;
  end?: boolean;
  roles?: UserRole[]; // omit for "everyone"
  group?: 'admin'; // groups this item into the Topbar's "Admin" dropdown instead of the
  // inline row — keeps the primary row to a handful of frequently-used tabs. Omit for
  // "show inline". See Topbar.tsx.
}

// Every clinical item is explicitly org_admin/doctor now that system_admin exists
// (CONTRACTS.md §2a) — a system_admin has no organization, so none of these apply to it;
// leaving `roles` unset used to mean "everyone" back when those were the only two roles.
const CLINICAL_ROLES: UserRole[] = ['org_admin', 'doctor'];

export const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: FiHome, end: true, roles: CLINICAL_ROLES },
  { to: '/patients', label: 'Patients', icon: FiUsers, roles: CLINICAL_ROLES },
  { to: '/studies', label: 'Studies', icon: FiFilePlus, roles: CLINICAL_ROLES },
  { to: '/reports', label: 'Reports', icon: FiFileText, roles: CLINICAL_ROLES },
  { to: '/billing', label: 'Billing', icon: FiCreditCard, roles: CLINICAL_ROLES },
  // Upload is NOT here on purpose — it's an action (start something), not a section to
  // browse like the others. It has no route of its own: the Dashboard's "Upload study"
  // button switches that page into an inline chat thread (ChatIntake) instead.
  { to: '/templates', label: 'Templates', icon: FiLayers, roles: ['org_admin'], group: 'admin' },
  { to: '/users', label: 'Users', icon: FiUserCheck, roles: ['org_admin'], group: 'admin' },
  { to: '/organization', label: 'Organization', icon: FiBriefcase, roles: ['org_admin'], group: 'admin' },
  // Audit Logs stays inline (not grouped) on purpose — it's a compliance/oversight tool an
  // org_admin may want to glance at often, unlike Templates/Users/Organization, which are
  // configure-once settings that belong behind the Admin dropdown.
  { to: '/audit-logs', label: 'Audit Logs', icon: FiShield, roles: ['org_admin'] },
  // Settings is NOT here on purpose — it lives in the Topbar's account dropdown next to
  // Profile/Log out (account-level actions), not the primary workflow nav. The route
  // itself (`/settings`) still exists — see AppRoutes.tsx.
  { to: '/platform/organizations', label: 'Organizations', icon: FiGlobe, roles: ['system_admin'] },
  { to: '/platform/admins', label: 'Platform admins', icon: FiShield, roles: ['system_admin'] },
];

export function navItemsForRole(role?: UserRole): NavItem[] {
  // SKIP_AUTH (devFlags.ts) lets you browse every page without logging in, but every nav
  // item below is role-gated — with no real user there'd be no role to match, and the
  // whole nav would silently render empty. Show everything instead so the flag still
  // does what it promises (click through the app's layout with no backend session).
  if (!role && SKIP_AUTH) {
    return NAV_ITEMS;
  }
  return NAV_ITEMS.filter((item) => !item.roles || (role && item.roles.includes(role)));
}

/** Items the Topbar renders inline. Kept short on purpose — see `group` above. */
export function primaryNavItems(role?: UserRole): NavItem[] {
  return navItemsForRole(role).filter((item) => !item.group);
}

/** Admin-only management links, tucked into the Topbar's "Admin" dropdown so the
 *  inline row doesn't have to fit all nine items side by side. */
export function adminNavItems(role?: UserRole): NavItem[] {
  return navItemsForRole(role).filter((item) => item.group === 'admin');
}
