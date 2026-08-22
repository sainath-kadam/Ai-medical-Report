import { useCallback, useEffect, useState } from 'react';
import { FiFileText } from 'react-icons/fi';
import { reportApi } from '../../api/report.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { Modality, Report, ReportStatus } from '../../types';
import { REPORT_STATUS_OPTIONS } from '../../utils/statusMeta';
import { MODALITY_OPTIONS } from '../../utils/studyMeta';
import ReportCard from '../../components/reports/ReportCard/ReportCard';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import Pagination from '../../components/ui/Pagination/Pagination';
import Select, { SelectOption } from '../../components/ui/Select/Select';
import './ReportsList.css';

const PAGE_SIZE = 20;

const STATUS_FILTER_OPTIONS: SelectOption[] = [{ value: 'all', label: 'All statuses' }, ...REPORT_STATUS_OPTIONS];
const MODALITY_FILTER_OPTIONS: SelectOption[] = [{ value: 'all', label: 'All modalities' }, ...MODALITY_OPTIONS];

export default function ReportsList() {
  const [reports, setReports] = useState<Report[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  const [statusFilter, setStatusFilter] = useState<ReportStatus | 'all'>('all');
  const [modalityFilter, setModalityFilter] = useState<Modality | 'all'>('all');

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    reportApi
      .list({
        page,
        pageSize: PAGE_SIZE,
        status: statusFilter === 'all' ? undefined : statusFilter,
        modality: modalityFilter === 'all' ? undefined : modalityFilter,
      })
      .then((data) => {
        setReports(data.items);
        setTotalPages(data.totalPages);
        setTotal(data.total);
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, statusFilter, modalityFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function handleStatusChange(value: string) {
    setStatusFilter(value === 'all' ? 'all' : (value as ReportStatus));
    setPage(1);
  }

  function handleModalityChange(value: string) {
    setModalityFilter(value === 'all' ? 'all' : (value as Modality));
    setPage(1);
  }

  const hasActiveFilters = statusFilter !== 'all' || modalityFilter !== 'all';

  return (
    <div className="reports-list-page">
      <div className="reports-list-page__header">
        <h1>Reports</h1>
        <p>Every AI-drafted report across your organization, newest first.</p>
      </div>

      <div className="reports-list-page__filters">
        <Select
          value={statusFilter}
          onChange={(e) => handleStatusChange(e.target.value)}
          options={STATUS_FILTER_OPTIONS}
          aria-label="Filter by status"
        />
        <Select
          value={modalityFilter}
          onChange={(e) => handleModalityChange(e.target.value)}
          options={MODALITY_FILTER_OPTIONS}
          aria-label="Filter by modality"
        />
      </div>

      {error && (
        <div className="reports-list-page__error">
          {error}{' '}
          <button className="reports-list-page__retry" onClick={load}>
            Try again
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="reports-list-page__loading">
          <Loader size="lg" />
        </div>
      ) : reports.length === 0 ? (
        <EmptyState
          icon={<FiFileText />}
          title={hasActiveFilters ? 'No reports match these filters' : 'No reports yet'}
          description={hasActiveFilters ? 'Try a different filter.' : 'Reports appear here once AI analysis completes on a study.'}
        />
      ) : (
        <>
          <div className="reports-list-page__grid">
            {reports.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </div>

          {total > 0 && (
            <div className="reports-list-page__footer">
              <span className="reports-list-page__count">
                {total} report{total === 1 ? '' : 's'}
              </span>
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
