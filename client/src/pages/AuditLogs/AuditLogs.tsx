import { FormEvent, useState } from 'react';
import { FiSearch, FiShield, FiXCircle } from 'react-icons/fi';
import { apiErrorMessage } from '../../api/axiosInstance';
import { useAuditLogsList } from '../../hooks/queries/useAuditLogs';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Pagination from '../../components/ui/Pagination/Pagination';
import { TextField } from '../../components/common/TextField/TextField';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import { AuditLog } from '../../types';
import { formatDateTime } from '../../utils/formatDate';
import { humanizeAction } from '../../utils/formatAction';
import './AuditLogs.css';

const PAGE_SIZE = 20;

export default function AuditLogs() {
  const [page, setPage] = useState(1);

  // actionDraft/resourceTypeDraft track the text fields as the user types;
  // actionFilter/resourceTypeFilter are only committed on submit and are what
  // actually drives the query, so we don't refetch on every keystroke.
  const [actionDraft, setActionDraft] = useState('');
  const [resourceTypeDraft, setResourceTypeDraft] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [resourceTypeFilter, setResourceTypeFilter] = useState('');

  const hasFilters = Boolean(actionFilter || resourceTypeFilter);

  // Cached per {page, action, resourceType} (see hooks/queries/useAuditLogs.ts) --
  // clearing a filter back to one already seen this session is instant.
  const { data, isLoading, isError, error, refetch } = useAuditLogsList({
    page,
    pageSize: PAGE_SIZE,
    action: actionFilter || undefined,
    resourceType: resourceTypeFilter || undefined,
  });
  const logs = data?.items ?? [];
  const totalPages = data?.totalPages ?? 1;
  const total = data?.total ?? 0;
  const loadError = isError ? apiErrorMessage(error) : '';

  function handleApplyFilters(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setActionFilter(actionDraft.trim());
    setResourceTypeFilter(resourceTypeDraft.trim());
  }

  function handleClearFilters() {
    setActionDraft('');
    setResourceTypeDraft('');
    setActionFilter('');
    setResourceTypeFilter('');
    setPage(1);
  }

  const columns: TableColumn<AuditLog>[] = [
    {
      key: 'createdAt',
      header: 'Timestamp',
      width: '190px',
      render: (row) => <span className="audit-logs-page__timestamp">{formatDateTime(row.createdAt)}</span>,
    },
    {
      key: 'userId',
      header: 'User',
      render: (row) => (
        <span className="audit-logs-page__id" title={row.userId}>
          {row.userId}
        </span>
      ),
    },
    {
      key: 'action',
      header: 'Action',
      render: (row) => <StatusBadge label={humanizeAction(row.action)} tone="muted" />,
    },
    {
      key: 'resource',
      header: 'Resource',
      render: (row) => (
        <div className="audit-logs-page__resource">
          <span className="audit-logs-page__resource-type">{row.resourceType}</span>
          {row.resourceId && (
            <span className="audit-logs-page__id" title={row.resourceId}>
              {row.resourceId}
            </span>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="audit-logs-page">
      <div className="audit-logs-page__header">
        <h1>Audit logs</h1>
        <p>Every action taken across your organization, newest first.</p>
      </div>

      <form className="audit-logs-page__filters" onSubmit={handleApplyFilters}>
        <TextField
          aria-label="Filter by action"
          placeholder="Filter by action (e.g. REPORT_FINALIZED)"
          icon={<FiSearch size={15} />}
          value={actionDraft}
          onChange={(e) => setActionDraft(e.target.value)}
        />
        <TextField
          aria-label="Filter by resource type"
          placeholder="Filter by resource type (e.g. report, study)"
          icon={<FiSearch size={15} />}
          value={resourceTypeDraft}
          onChange={(e) => setResourceTypeDraft(e.target.value)}
        />
        <Button type="submit">Apply filters</Button>
        {hasFilters && (
          <Button type="button" variant="ghost" icon={<FiXCircle size={15} />} onClick={handleClearFilters}>
            Clear
          </Button>
        )}
      </form>

      {loadError ? (
        <div className="audit-logs-page__error">
          <span>{loadError}</span>
          <Button size="sm" variant="ghost" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="audit-logs-page__loading">
          <Loader size="lg" />
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          icon={<FiShield />}
          title="No audit log entries found"
          description={hasFilters ? 'Try adjusting or clearing your filters.' : 'Actions taken in your organization will show up here.'}
        />
      ) : (
        <>
          <Table columns={columns} rows={logs} rowKey={(row) => row.id} emptyMessage="No audit log entries found" />
          <div className="audit-logs-page__footer">
            <span className="audit-logs-page__count">
              {total} {total === 1 ? 'entry' : 'entries'}
            </span>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </div>
        </>
      )}
    </div>
  );
}
