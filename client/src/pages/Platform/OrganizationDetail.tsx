import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FiArrowLeft, FiCalendar, FiLock, FiUnlock, FiUsers } from 'react-icons/fi';
import { platformApi, PlatformOrganization } from '../../api/platform.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { Organization, User } from '../../types';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Select from '../../components/ui/Select/Select';
import { TextArea, TextField } from '../../components/common/TextField/TextField';
import { formatDate, formatDateTime } from '../../utils/formatDate';
import { accessBadge } from './accessBadge';
import './Platform.css';

const PLAN_OPTIONS: { value: Organization['plan']; label: string }[] = [
  { value: 'free', label: 'Free' },
  { value: 'pro', label: 'Pro' },
  { value: 'enterprise', label: 'Enterprise' },
];

const ROLE_LABEL: Record<User['role'], string> = { org_admin: 'Org Admin', doctor: 'Doctor', system_admin: 'Platform Admin' };

/** ISO instant -> the `yyyy-mm-dd` an <input type="date"> wants (UTC date). */
function toDateInput(iso: string | null | undefined): string {
  return iso ? new Date(iso).toISOString().slice(0, 10) : '';
}

/** `yyyy-mm-dd` -> the last second of that UTC day, so "until Dec 31" includes Dec 31. */
function toEndOfDayIso(date: string): string {
  return new Date(`${date}T23:59:59Z`).toISOString();
}

function addDays(fromIso: string | null | undefined, days: number): string {
  const base = fromIso && new Date(fromIso).getTime() > Date.now() ? new Date(fromIso) : new Date();
  base.setUTCDate(base.getUTCDate() + days);
  return base.toISOString().slice(0, 10);
}

/** system_admin-only (CONTRACTS.md §2c): one organization's access controls — grant or clear a
 * manual access period, suspend/restore, annotate — plus its members. Every change here is
 * audit-logged against the organization as ORGANIZATION_ACCESS_UPDATED. */
export default function OrganizationDetail() {
  const { id } = useParams<{ id: string }>();
  const [org, setOrg] = useState<PlatformOrganization | null>(null);
  const [members, setMembers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [form, setForm] = useState({ accessEndsAt: '', accessNote: '', plan: 'free' as Organization['plan'] });
  const [isSaving, setIsSaving] = useState(false);
  const [isTogglingSuspend, setIsTogglingSuspend] = useState(false);
  const [actionError, setActionError] = useState('');
  const [success, setSuccess] = useState('');

  const applyOrg = useCallback((next: PlatformOrganization) => {
    setOrg(next);
    setForm({ accessEndsAt: toDateInput(next.accessEndsAt), accessNote: next.accessNote || '', plan: next.plan });
  }, []);

  useEffect(() => {
    if (!id) return;
    setIsLoading(true);
    platformApi
      .getOrganization(id)
      .then((data) => {
        applyOrg(data.organization);
        setMembers(data.users);
      })
      .catch((err) => setLoadError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [id, applyOrg]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!id) return;
    setActionError('');
    setSuccess('');
    setIsSaving(true);
    try {
      const updated = await platformApi.updateAccess(id, {
        accessEndsAt: form.accessEndsAt ? toEndOfDayIso(form.accessEndsAt) : null,
        accessNote: form.accessNote.trim() || null,
        plan: form.plan,
      });
      applyOrg(updated);
      setSuccess(
        updated.accessEndsAt
          ? `Access granted until ${formatDate(updated.accessEndsAt)}.`
          : 'Manual access period cleared — the organization is back on its trial/subscription state.'
      );
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleSuspend() {
    if (!id || !org) return;
    const suspend = !org.isSuspended;
    if (suspend && !window.confirm(`Suspend ${org.name}? Its users will be able to log in and read, but not change anything.`)) {
      return;
    }
    setActionError('');
    setSuccess('');
    setIsTogglingSuspend(true);
    try {
      const updated = await platformApi.updateAccess(id, { isSuspended: suspend });
      applyOrg(updated);
      setSuccess(suspend ? 'Organization suspended — it is now read-only.' : 'Suspension lifted.');
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setIsTogglingSuspend(false);
    }
  }

  if (isLoading) {
    return (
      <div className="platform-page__loading">
        <Loader size="lg" label="Loading organization…" />
      </div>
    );
  }
  if (loadError || !org) {
    return (
      <div className="platform-page">
        <Link to="/platform/organizations" className="platform-page__back">
          <FiArrowLeft size={14} /> All organizations
        </Link>
        <div className="platform-page__error">{loadError || 'Organization not found.'}</div>
      </div>
    );
  }

  const badge = accessBadge(org.access);
  const memberColumns: TableColumn<User>[] = [
    {
      key: 'name',
      header: 'Member',
      render: (u) => (
        <div className="platform-page__name-cell">
          <strong>{u.name}</strong>
          <span className="platform-page__muted">{u.email}</span>
        </div>
      ),
    },
    { key: 'role', header: 'Role', render: (u) => ROLE_LABEL[u.role] },
    {
      key: 'status',
      header: 'Status',
      render: (u) => (
        <StatusBadge label={u.isActive === false ? 'Inactive' : 'Active'} tone={u.isActive === false ? 'danger' : 'success'} />
      ),
    },
  ];

  return (
    <div className="platform-page">
      <Link to="/platform/organizations" className="platform-page__back">
        <FiArrowLeft size={14} /> All organizations
      </Link>

      <div className="platform-page__header">
        <div>
          <h1>{org.name}</h1>
          <p>
            Created {formatDate(org.createdAt)} · {org.userCount} user{org.userCount === 1 ? '' : 's'} · {org.reportCount}{' '}
            report{org.reportCount === 1 ? '' : 's'}
          </p>
        </div>
        <StatusBadge label={badge.label} tone={badge.tone} />
      </div>

      {actionError && <div className="platform-page__error">{actionError}</div>}
      {success && <div className="platform-page__success">{success}</div>}

      <div className="platform-page__grid">
        <Card className="platform-page__card">
          <h3>
            <FiCalendar size={16} /> Access
          </h3>

          <div className="platform-page__access-state">
            {org.access.writable ? <FiUnlock size={16} /> : <FiLock size={16} />}
            <span>
              {org.access.writable
                ? org.access.source === 'subscription'
                  ? 'Writable — paid subscription (Stripe), no end date.'
                  : org.access.source === 'manual'
                    ? `Writable — access granted until ${formatDateTime(org.access.endsAt!)}.`
                    : `Writable — free trial until ${formatDateTime(org.access.endsAt!)}.`
                : org.access.reason === 'ORGANIZATION_SUSPENDED'
                  ? 'Read-only — suspended by a platform admin.'
                  : org.access.reason === 'ACCESS_EXPIRED'
                    ? `Read-only — access period ended ${formatDateTime(org.access.endsAt!)}.`
                    : `Read-only — free trial ended${org.access.endsAt ? ` ${formatDateTime(org.access.endsAt)}` : ''}.`}
            </span>
          </div>

          <form className="platform-page__form" onSubmit={handleSave}>
            <TextField
              label="Access granted until"
              type="date"
              value={form.accessEndsAt}
              onChange={(e) => setForm((p) => ({ ...p, accessEndsAt: e.target.value }))}
              hint="The organization can create and edit until the end of this day (UTC), regardless of trial or subscription. Leave empty for no manual period."
            />
            <div className="platform-page__quick-row">
              {[30, 90, 365].map((days) => (
                <Button
                  key={days}
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setForm((p) => ({ ...p, accessEndsAt: addDays(p.accessEndsAt ? toEndOfDayIso(p.accessEndsAt) : null, days) }))}
                >
                  +{days === 365 ? '1 year' : `${days} days`}
                </Button>
              ))}
              {form.accessEndsAt && (
                <Button type="button" size="sm" variant="ghost" onClick={() => setForm((p) => ({ ...p, accessEndsAt: '' }))}>
                  Clear date
                </Button>
              )}
            </div>
            <Select
              label="Plan"
              options={PLAN_OPTIONS}
              value={form.plan}
              onChange={(e) => setForm((p) => ({ ...p, plan: e.target.value as Organization['plan'] }))}
            />
            <TextArea
              label="Internal note"
              placeholder="e.g. Paid by bank transfer, invoice #1042, 12 months"
              value={form.accessNote}
              onChange={(e) => setForm((p) => ({ ...p, accessNote: e.target.value }))}
              rows={3}
              hint="Visible to platform admins only — never to the organization."
            />
            <div className="platform-page__actions">
              <Button type="submit" isLoading={isSaving}>
                Save access
              </Button>
            </div>
          </form>

          <div className="platform-page__danger-zone">
            <span>
              {org.isSuspended
                ? 'This organization is suspended. Lifting it restores whatever trial, subscription or granted period applies.'
                : 'Suspending makes the organization read-only immediately, whatever its trial or subscription state.'}
            </span>
            <Button
              type="button"
              variant={org.isSuspended ? 'primary' : 'danger'}
              icon={org.isSuspended ? <FiUnlock size={14} /> : <FiLock size={14} />}
              isLoading={isTogglingSuspend}
              onClick={handleToggleSuspend}
            >
              {org.isSuspended ? 'Lift suspension' : 'Suspend organization'}
            </Button>
          </div>
        </Card>

        <div className="platform-page__card">
          <Card className="platform-page__card">
            <h3>Details</h3>
            <dl className="platform-page__facts">
              <div>
                <dt>Plan</dt>
                <dd>{org.plan}</dd>
              </div>
              <div>
                <dt>Billing status</dt>
                <dd>{org.subscriptionStatus || '—'}</dd>
              </div>
              <div>
                <dt>Trial ends</dt>
                <dd>{org.trialEndsAt ? formatDate(org.trialEndsAt) : '—'}</dd>
              </div>
              <div>
                <dt>Granted until</dt>
                <dd>{org.accessEndsAt ? formatDate(org.accessEndsAt) : '—'}</dd>
              </div>
              <div>
                <dt>Contact</dt>
                <dd>{org.contactEmail || org.contactPhone || '—'}</dd>
              </div>
              <div>
                <dt>High-accuracy AI</dt>
                <dd>{org.highAccuracyMode ? 'On' : 'Off'}</dd>
              </div>
            </dl>
          </Card>

          <Card className="platform-page__card">
            <h3>
              <FiUsers size={16} /> Members
            </h3>
            <Table columns={memberColumns} rows={members} rowKey={(u) => u.id} emptyMessage="No users in this organization" />
          </Card>
        </div>
      </div>
    </div>
  );
}
