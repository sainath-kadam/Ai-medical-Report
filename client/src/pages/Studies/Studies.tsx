import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiPlus } from 'react-icons/fi';
import { studyApi } from '../../api/study.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { Modality, Study, StudyStatus } from '../../types';
import { MODALITY_LABELS, MODALITY_OPTIONS, STUDY_STATUS_META, STUDY_STATUS_OPTIONS } from '../../utils/studyMeta';
import { formatDate, formatRelative } from '../../utils/formatDate';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Pagination from '../../components/ui/Pagination/Pagination';
import Select, { SelectOption } from '../../components/ui/Select/Select';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import './Studies.css';

const PAGE_SIZE = 20;

const STATUS_FILTER_OPTIONS: SelectOption[] = [{ value: 'all', label: 'All statuses' }, ...STUDY_STATUS_OPTIONS];
const MODALITY_FILTER_OPTIONS: SelectOption[] = [{ value: 'all', label: 'All modalities' }, ...MODALITY_OPTIONS];

export default function Studies() {
  const navigate = useNavigate();

  const [studies, setStudies] = useState<Study[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  const [statusFilter, setStatusFilter] = useState<StudyStatus | 'all'>('all');
  const [modalityFilter, setModalityFilter] = useState<Modality | 'all'>('all');

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    studyApi
      .list({
        page,
        pageSize: PAGE_SIZE,
        status: statusFilter === 'all' ? undefined : statusFilter,
        modality: modalityFilter === 'all' ? undefined : modalityFilter,
      })
      .then((data) => {
        setStudies(data.items);
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
    setStatusFilter(value === 'all' ? 'all' : (value as StudyStatus));
    setPage(1);
  }

  function handleModalityChange(value: string) {
    setModalityFilter(value === 'all' ? 'all' : (value as Modality));
    setPage(1);
  }

  const columns: TableColumn<Study>[] = [
    {
      key: 'patient',
      header: 'Patient',
      render: (study) =>
        study.patient ? (
          <div className="studies-page__patient-cell">
            <strong>{study.patient.name}</strong>
            <span>MRN {study.patient.mrn}</span>
          </div>
        ) : (
          <span className="studies-page__muted">{study.patientId}</span>
        ),
    },
    { key: 'modality', header: 'Modality', render: (study) => MODALITY_LABELS[study.modality] },
    { key: 'bodyPart', header: 'Body part' },
    { key: 'studyDate', header: 'Study date', render: (study) => formatDate(study.studyDate) },
    {
      key: 'status',
      header: 'Status',
      render: (study) => {
        const meta = STUDY_STATUS_META[study.status];
        return <StatusBadge label={meta.label} tone={meta.tone} />;
      },
    },
    { key: 'createdAt', header: 'Uploaded', render: (study) => formatRelative(study.createdAt) },
  ];

  const hasActiveFilters = statusFilter !== 'all' || modalityFilter !== 'all';

  return (
    <div className="studies-page">
      <div className="studies-page__header">
        <div>
          <h1>Studies</h1>
          <p>Every imaging study across your organization, newest first.</p>
        </div>
        <Button icon={<FiPlus size={16} />} onClick={() => navigate('/dashboard?startUpload=1')}>
          New study
        </Button>
      </div>

      <div className="studies-page__filters">
        <Select value={statusFilter} onChange={(e) => handleStatusChange(e.target.value)} options={STATUS_FILTER_OPTIONS} aria-label="Filter by status" />
        <Select
          value={modalityFilter}
          onChange={(e) => handleModalityChange(e.target.value)}
          options={MODALITY_FILTER_OPTIONS}
          aria-label="Filter by modality"
        />
      </div>

      {error && (
        <div className="studies-page__error">
          {error}{' '}
          <button className="studies-page__retry" onClick={load}>
            Try again
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="studies-page__loading">
          <Loader size="lg" />
        </div>
      ) : (
        <>
          <Table
            columns={columns}
            rows={studies}
            rowKey={(study) => study.id}
            onRowClick={(study) => navigate(`/studies/${study.id}`)}
            emptyMessage={hasActiveFilters ? 'No studies match these filters' : 'No studies yet'}
          />

          {total > 0 && (
            <div className="studies-page__footer">
              <span className="studies-page__count">
                {total} stud{total === 1 ? 'y' : 'ies'}
              </span>
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
