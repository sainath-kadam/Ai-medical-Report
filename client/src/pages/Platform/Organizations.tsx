import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiPlus, FiSearch } from 'react-icons/fi';
import { apiErrorMessage } from '../../api/axiosInstance';
import { usePlatformOrganizations } from '../../hooks/queries/usePlatform';
import { PlatformOrganization } from '../../api/platform.api';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Pagination from '../../components/ui/Pagination/Pagination';
import Button from '../../components/common/Button/Button';
import { TextField } from '../../components/common/TextField/TextField';
import Loader from '../../components/common/Loader/Loader';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import { formatDate } from '../../utils/formatDate';
import { accessBadge } from './accessBadge';
import './Platform.css';

const PAGE_SIZE = 20;

/** system_admin-only (CONTRACTS.md §2c): every organization on the platform, with its
 * evaluated access state and usage. Click a row to manage its access period. Cached per
 * {page, search} (see hooks/queries/usePlatform.ts) -- coming back from an organization's
 * detail page with the same search reads straight from cache. */
export default function Organizations() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [activeSearch, setActiveSearch] = useState('');

  const { data, isLoading, isError, error } = usePlatformOrganizations({ page, pageSize: PAGE_SIZE, search: activeSearch || undefined });
  const items = data?.items ?? [];
  const totalPages = data?.totalPages ?? 1;
  const total = data?.total ?? 0;
  const loadError = isError ? apiErrorMessage(error) : '';

  function handleSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setActiveSearch(search.trim());
  }

  const columns: TableColumn<PlatformOrganization>[] = [
    {
      key: 'name',
      header: 'Organization',
      render: (o) => (
        <div className="platform-page__name-cell">
          <strong>{o.name}</strong>
          <span className="platform-page__muted">{o.contactEmail || `Plan: ${o.plan}`}</span>
        </div>
      ),
    },
    {
      key: 'access',
      header: 'Access',
      render: (o) => {
        const badge = accessBadge(o.access);
        return <StatusBadge label={badge.label} tone={badge.tone} />;
      },
    },
    {
      key: 'ends',
      header: 'Ends',
      render: (o) =>
        o.access.endsAt ? formatDate(o.access.endsAt) : o.access.source === 'subscription' ? 'While subscribed' : '—',
    },
    { key: 'users', header: 'Users', width: '90px', render: (o) => String(o.userCount) },
    { key: 'reports', header: 'Reports', width: '90px', render: (o) => String(o.reportCount) },
    { key: 'created', header: 'Created', render: (o) => formatDate(o.createdAt) },
  ];

  return (
    <div className="platform-page">
      <div className="platform-page__header">
        <div>
          <h1>Organizations</h1>
          <p>
            Every clinic on the platform{total ? ` (${total})` : ''}. Open one to grant an access period, suspend it,
            or see who belongs to it.
          </p>
        </div>
        <div className="platform-page__header-actions">
          <Button icon={<FiPlus size={16} />} onClick={() => navigate('/platform/organizations/new')}>
            Create organization
          </Button>
        </div>
      </div>

      <form className="platform-page__toolbar" onSubmit={handleSearch}>
        <TextField
          label="Search"
          placeholder="Organization name or contact email"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          icon={<FiSearch size={14} />}
        />
        <Button type="submit" variant="outline">
          Search
        </Button>
        {activeSearch && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setSearch('');
              setActiveSearch('');
              setPage(1);
            }}
          >
            Clear
          </Button>
        )}
      </form>

      {isLoading ? (
        <div className="platform-page__loading">
          <Loader size="lg" />
        </div>
      ) : loadError ? (
        <div className="platform-page__error">{loadError}</div>
      ) : (
        <>
          <Table
            columns={columns}
            rows={items}
            rowKey={(o) => o.id}
            onRowClick={(o) => navigate(`/platform/organizations/${o.id}`)}
            emptyMessage={activeSearch ? 'No organizations match that search' : 'No organizations yet — create the first one'}
          />
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
