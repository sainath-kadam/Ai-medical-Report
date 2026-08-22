import { describe, expect, it } from 'vitest';
import { navItemsForRole } from './navItems';

describe('navItemsForRole', () => {
  it('includes role-restricted items for org_admin', () => {
    const items = navItemsForRole('org_admin');
    expect(items.some((i) => i.to === '/users')).toBe(true);
    expect(items.some((i) => i.to === '/audit-logs')).toBe(true);
  });

  it('hides admin-only items for doctor', () => {
    const items = navItemsForRole('doctor');
    expect(items.some((i) => i.to === '/users')).toBe(false);
    expect(items.some((i) => i.to === '/audit-logs')).toBe(false);
    expect(items.some((i) => i.to === '/organization')).toBe(false);
  });

  it('includes clinical items for both org_admin and doctor', () => {
    for (const role of ['org_admin', 'doctor'] as const) {
      const items = navItemsForRole(role);
      expect(items.some((i) => i.to === '/dashboard')).toBe(true);
      expect(items.some((i) => i.to === '/patients')).toBe(true);
    }
  });

  it('system_admin sees only the Organizations item, not clinical or org_admin items', () => {
    const items = navItemsForRole('system_admin');
    expect(items.some((i) => i.to === '/platform/organizations')).toBe(true);
    expect(items.some((i) => i.to === '/')).toBe(false);
    expect(items.some((i) => i.to === '/patients')).toBe(false);
    expect(items.some((i) => i.to === '/users')).toBe(false);
  });
});
