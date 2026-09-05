import { FormEvent, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { FiPlus, FiShield } from 'react-icons/fi';
import { platformApi, InviteSystemAdminResult } from '../../api/platform.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { useSystemAdmins } from '../../hooks/queries/usePlatform';
import { queryKeys } from '../../lib/queryKeys';
import { User } from '../../types';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Button from '../../components/common/Button/Button';
import Modal from '../../components/common/Modal/Modal';
import Card from '../../components/common/Card/Card';
import { TextField } from '../../components/common/TextField/TextField';
import Loader from '../../components/common/Loader/Loader';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import TempPasswordBanner from '../../components/common/TempPasswordBanner/TempPasswordBanner';
import { useAuth } from '../../hooks/useAuth';
import './Platform.css';

const EMPTY_INVITE = { name: '', email: '' };

/** system_admin-only (CONTRACTS.md §2b): the platform-wide accounts that can manage every
 * organization. There is no self-service path to this role — only this page (and the
 * one-time CLI bootstrap) creates one. */
export default function SystemAdmins() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const { data: admins = [], isLoading, isError, error } = useSystemAdmins();

  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState(EMPTY_INVITE);
  const [inviteError, setInviteError] = useState('');
  const [isInviting, setIsInviting] = useState(false);
  const [created, setCreated] = useState<InviteSystemAdminResult | null>(null);

  const loadError = isError ? apiErrorMessage(error) : '';

  async function handleInvite(event: FormEvent) {
    event.preventDefault();
    setInviteError('');
    setIsInviting(true);
    try {
      const result = await platformApi.inviteSystemAdmin(inviteForm);
      setIsInviteOpen(false);
      setInviteForm(EMPTY_INVITE);
      setCreated(result);
      queryClient.invalidateQueries({ queryKey: queryKeys.platform.systemAdmins() });
    } catch (err) {
      setInviteError(apiErrorMessage(err));
    } finally {
      setIsInviting(false);
    }
  }

  const columns: TableColumn<User>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (u) => (
        <div className="platform-page__name-cell">
          <strong>
            {u.name}
            {u.id === currentUser?.id ? ' (you)' : ''}
          </strong>
          <span className="platform-page__muted">{u.email}</span>
        </div>
      ),
    },
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
      <div className="platform-page__header">
        <div>
          <h1>Platform admins</h1>
          <p>Accounts that can create organizations and control every organization's access.</p>
        </div>
        <Button icon={<FiPlus size={16} />} onClick={() => setIsInviteOpen(true)}>
          Add platform admin
        </Button>
      </div>

      {created && (
        <Card className="platform-page__card">
          <p className="platform-page__card-hint">
            <strong>{created.name}</strong> ({created.email}) can now sign in as a platform admin.
          </p>
          <TempPasswordBanner password={created.temporaryPassword} recipientName={created.name} />
          <div className="platform-page__actions">
            <Button variant="outline" onClick={() => setCreated(null)}>
              Done
            </Button>
          </div>
        </Card>
      )}

      {isLoading ? (
        <div className="platform-page__loading">
          <Loader size="lg" />
        </div>
      ) : loadError ? (
        <div className="platform-page__error">{loadError}</div>
      ) : (
        <Table columns={columns} rows={admins} rowKey={(u) => u.id} emptyMessage="No platform admins found" />
      )}

      <Modal isOpen={isInviteOpen} onClose={() => setIsInviteOpen(false)} title="Add platform admin">
        <form className="platform-page__form" onSubmit={handleInvite}>
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
          {inviteError && <div className="platform-page__error">{inviteError}</div>}
          <p className="platform-page__card-hint">
            <FiShield size={12} /> This account will be able to manage every organization on the platform. A temporary
            password is generated and shown once — share it with them yourself.
          </p>
          <div className="platform-page__actions">
            <Button type="button" variant="ghost" onClick={() => setIsInviteOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isInviting}>
              Add admin
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
