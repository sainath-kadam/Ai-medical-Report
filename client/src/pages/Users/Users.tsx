import { FormEvent, useEffect, useState } from 'react';
import { FiPlus, FiUserCheck, FiUserX } from 'react-icons/fi';
import { userApi } from '../../api/user.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { User, UserRole } from '../../types';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Pagination from '../../components/ui/Pagination/Pagination';
import Select from '../../components/ui/Select/Select';
import Button from '../../components/common/Button/Button';
import Modal from '../../components/common/Modal/Modal';
import { TextField } from '../../components/common/TextField/TextField';
import Loader from '../../components/common/Loader/Loader';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import TempPasswordBanner from '../../components/common/TempPasswordBanner/TempPasswordBanner';
import { useAuth } from '../../hooks/useAuth';
import { getInitial } from '../../utils/formatName';
import './Users.css';

const PAGE_SIZE = 20;

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'org_admin', label: 'Org Admin' },
  { value: 'doctor', label: 'Doctor' },
];

const ROLE_LABEL: Record<UserRole, string> = {
  org_admin: 'Org Admin',
  doctor: 'Doctor',
  // Never actually appears here — GET /users is organization-scoped and system_admin
  // belongs to none (CONTRACTS.md §2a) — included only so this map stays exhaustive.
  system_admin: 'Platform Admin',
};

interface InviteFormState {
  name: string;
  email: string;
  role: UserRole;
}

const EMPTY_INVITE: InviteFormState = { name: '', email: '', role: 'doctor' };

export default function Users() {
  const { user: currentUser } = useAuth();

  const [users, setUsers] = useState<User[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyUserId, setBusyUserId] = useState<string | null>(null);

  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState<InviteFormState>(EMPTY_INVITE);
  const [inviteError, setInviteError] = useState('');
  const [isInviting, setIsInviting] = useState(false);

  const [newCredentials, setNewCredentials] = useState<{ user: User; temporaryPassword: string } | null>(null);

  function load(pageToLoad: number) {
    setIsLoading(true);
    setLoadError('');
    userApi
      .list({ page: pageToLoad, pageSize: PAGE_SIZE })
      .then((data) => {
        setUsers(data.items);
        setPage(data.page);
        setTotalPages(data.totalPages);
      })
      .catch((err) => setLoadError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openInvite() {
    setInviteForm(EMPTY_INVITE);
    setInviteError('');
    setIsInviteOpen(true);
  }

  async function handleInvite(event: FormEvent) {
    event.preventDefault();
    setInviteError('');
    setIsInviting(true);
    try {
      const result = await userApi.create(inviteForm);
      setIsInviteOpen(false);
      setNewCredentials(result);
      load(1);
    } catch (err) {
      setInviteError(apiErrorMessage(err));
    } finally {
      setIsInviting(false);
    }
  }

  async function handleRoleChange(target: User, role: UserRole) {
    if (target.id === currentUser?.id || role === target.role) return;
    setActionError('');
    setBusyUserId(target.id);
    try {
      const updated = await userApi.update(target.id, { role });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleToggleActive(target: User) {
    if (target.id === currentUser?.id) return;
    setActionError('');
    setBusyUserId(target.id);
    try {
      const updated = await userApi.update(target.id, { isActive: target.isActive === false });
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setBusyUserId(null);
    }
  }

  const columns: TableColumn<User>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (u) => (
        <div className="users-page__name-cell">
          <span className="users-page__avatar">{getInitial(u.name)}</span>
          <span>{u.name}</span>
          {u.id === currentUser?.id && <span className="users-page__you-tag">You</span>}
        </div>
      ),
    },
    { key: 'email', header: 'Email', render: (u) => u.email },
    {
      key: 'role',
      header: 'Role',
      width: '190px',
      render: (u) => {
        const isSelf = u.id === currentUser?.id;
        const select = (
          <Select
            aria-label={`Role for ${u.name}`}
            options={ROLE_OPTIONS}
            value={u.role}
            disabled={isSelf || busyUserId === u.id}
            onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
          />
        );
        return isSelf ? (
          <span className="users-page__disabled-wrap" title="You can't change your own role">
            {select}
          </span>
        ) : (
          select
        );
      },
    },
    {
      key: 'status',
      header: 'Status',
      render: (u) => (
        <StatusBadge label={u.isActive === false ? 'Inactive' : 'Active'} tone={u.isActive === false ? 'danger' : 'success'} />
      ),
    },
    {
      key: 'actions',
      header: '',
      width: '150px',
      render: (u) => {
        const isSelf = u.id === currentUser?.id;
        const isInactive = u.isActive === false;
        const button = (
          <Button
            size="sm"
            variant="ghost"
            icon={isInactive ? <FiUserCheck size={13} /> : <FiUserX size={13} />}
            disabled={isSelf}
            isLoading={busyUserId === u.id}
            onClick={() => handleToggleActive(u)}
          >
            {isInactive ? 'Activate' : 'Deactivate'}
          </Button>
        );
        return isSelf ? (
          <span className="users-page__disabled-wrap" title="You can't deactivate your own account">
            {button}
          </span>
        ) : (
          button
        );
      },
    },
  ];

  return (
    <div className="users-page">
      <div className="users-page__header">
        <div>
          <h1>Users</h1>
          <p>Manage who in your organization can sign in and what they can do.</p>
        </div>
        <Button icon={<FiPlus size={16} />} onClick={openInvite}>
          Invite user
        </Button>
      </div>

      {actionError && <div className="users-page__error">{actionError}</div>}

      {isLoading ? (
        <div className="users-page__loading">
          <Loader size="lg" />
        </div>
      ) : loadError ? (
        <div className="users-page__error">{loadError}</div>
      ) : (
        <>
          <Table columns={columns} rows={users} rowKey={(u) => u.id} emptyMessage="No users yet — invite your team to get started" />
          <Pagination page={page} totalPages={totalPages} onPageChange={load} />
        </>
      )}

      <Modal isOpen={isInviteOpen} onClose={() => setIsInviteOpen(false)} title="Invite user">
        <form className="users-page__invite-form" onSubmit={handleInvite}>
          <TextField
            label="Full name"
            value={inviteForm.name}
            onChange={(e) => setInviteForm((p) => ({ ...p, name: e.target.value }))}
            required
            autoFocus
          />
          <TextField
            label="Email"
            type="email"
            value={inviteForm.email}
            onChange={(e) => setInviteForm((p) => ({ ...p, email: e.target.value }))}
            required
          />
          <Select
            label="Role"
            options={ROLE_OPTIONS}
            value={inviteForm.role}
            onChange={(e) => setInviteForm((p) => ({ ...p, role: e.target.value as UserRole }))}
          />

          {inviteError && <div className="users-page__error">{inviteError}</div>}

          <p className="users-page__invite-hint">
            A temporary password is generated automatically — no invitation email is sent in this version, so
            you&apos;ll need to share it with them yourself right after this.
          </p>

          <div className="users-page__invite-actions">
            <Button type="button" variant="outline" onClick={() => setIsInviteOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isInviting}>
              Send invite
            </Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={!!newCredentials} onClose={() => setNewCredentials(null)} title="User invited">
        {newCredentials && (
          <div className="users-page__credentials">
            <p className="users-page__credentials-summary">
              <strong>{newCredentials.user.name}</strong> ({newCredentials.user.email}) has been added as{' '}
              <strong>{ROLE_LABEL[newCredentials.user.role]}</strong>.
            </p>

            <TempPasswordBanner password={newCredentials.temporaryPassword} recipientName={newCredentials.user.name} />

            <Button fullWidth onClick={() => setNewCredentials(null)}>
              Done
            </Button>
          </div>
        )}
      </Modal>
    </div>
  );
}
