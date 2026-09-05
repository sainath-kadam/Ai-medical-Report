import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { FiEdit2, FiPlus, FiSearch, FiTrash2, FiUsers } from 'react-icons/fi';
import { patientApi } from '../../api/patient.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { usePatientsList } from '../../hooks/queries/usePatients';
import { queryKeys } from '../../lib/queryKeys';
import { Patient, Sex } from '../../types';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import Pagination from '../../components/ui/Pagination/Pagination';
import Button from '../../components/common/Button/Button';
import Modal from '../../components/common/Modal/Modal';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import { TextField } from '../../components/common/TextField/TextField';
import PatientForm, { PatientFormValues, patientFormToPayload } from '../../components/patients/PatientForm/PatientForm';
import { useAuth } from '../../hooks/useAuth';
import { useToast } from '../../components/ui/Toast/ToastProvider';
import { formatDate } from '../../utils/formatDate';
import './Patients.css';

const PAGE_SIZE = 20;

const SEX_LABEL: Record<Sex, string> = {
  male: 'Male',
  female: 'Female',
  other: 'Other',
  unspecified: 'Unspecified',
};

export default function Patients() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // RBAC (CONTRACTS.md §3): org_admin/doctor can all create+edit+delete patients.
  const canDelete = user?.role === 'org_admin' || user?.role === 'doctor';

  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');

  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null);
  const [activePatient, setActivePatient] = useState<Patient | null>(null);
  const [formError, setFormError] = useState('');
  const [actionError, setActionError] = useState('');

  // Debounce free-text search so we don't fire a request on every keystroke.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setPage(1);
      setSearch(searchInput.trim());
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  // Cached per {page, pageSize, search} -- revisiting Patients with the same filters
  // within the freshness window (see hooks/queries/usePatients.ts) reads straight from
  // cache; a create/update/delete below invalidates the whole `patients` domain so the
  // list (and any open patient detail page) picks up the change on its next render.
  const { data, isLoading, isError, error, refetch } = usePatientsList({ page, pageSize: PAGE_SIZE, search: search || undefined });
  const patients = data?.items ?? [];
  const totalPages = data?.totalPages ?? 1;
  const total = data?.total ?? 0;

  function invalidatePatients() {
    queryClient.invalidateQueries({ queryKey: queryKeys.patients.all });
  }

  function openCreate() {
    setFormError('');
    setModalMode('create');
  }

  function openEdit(patient: Patient) {
    setActivePatient(patient);
    setFormError('');
    setModalMode('edit');
  }

  function closeModal() {
    setModalMode(null);
    setActivePatient(null);
  }

  async function handleCreate(values: PatientFormValues) {
    setFormError('');
    try {
      await patientApi.create(patientFormToPayload(values));
      closeModal();
      showToast('Patient created', 'success');
      invalidatePatients();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    }
  }

  async function handleUpdate(values: PatientFormValues) {
    if (!activePatient) return;
    setFormError('');
    try {
      await patientApi.update(activePatient.id, patientFormToPayload(values));
      closeModal();
      showToast('Patient updated', 'success');
      invalidatePatients();
    } catch (err) {
      setFormError(apiErrorMessage(err));
    }
  }

  async function handleDelete(patient: Patient) {
    if (!confirm(`Delete patient ${patient.name}? This cannot be undone.`)) return;
    try {
      await patientApi.remove(patient.id);
      showToast('Patient deleted', 'success');
      invalidatePatients();
    } catch (err) {
      setActionError(apiErrorMessage(err));
    }
  }

  const columns: TableColumn<Patient>[] = [
    { key: 'mrn', header: 'MRN', render: (p) => <span className="patients-page__mrn">{p.mrn}</span> },
    { key: 'name', header: 'Name' },
    { key: 'dateOfBirth', header: 'DOB', render: (p) => (p.dateOfBirth ? formatDate(p.dateOfBirth) : '—') },
    { key: 'sex', header: 'Sex', render: (p) => SEX_LABEL[p.sex ?? 'unspecified'] },
    {
      key: 'actions',
      header: '',
      width: '1%',
      render: (p) => (
        <div className="patients-page__row-actions" onClick={(e) => e.stopPropagation()}>
          <button type="button" className="patients-page__icon-btn" aria-label={`Edit ${p.name}`} onClick={() => openEdit(p)}>
            <FiEdit2 size={14} />
          </button>
          {canDelete && (
            <button
              type="button"
              className="patients-page__icon-btn patients-page__icon-btn--danger"
              aria-label={`Delete ${p.name}`}
              onClick={() => handleDelete(p)}
            >
              <FiTrash2 size={14} />
            </button>
          )}
        </div>
      ),
    },
  ];

  const loadError = isError ? apiErrorMessage(error) : '';

  return (
    <div className="patients-page">
      <div className="patients-page__header">
        <div>
          <h1>Patients</h1>
          <p>Search and manage every patient record in your organization.</p>
        </div>
        <Button icon={<FiPlus size={16} />} onClick={openCreate}>
          New patient
        </Button>
      </div>

      <div className="patients-page__toolbar">
        <TextField
          icon={<FiSearch size={16} />}
          placeholder="Search by name or MRN…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          aria-label="Search patients"
        />
        {!isLoading && !loadError && (
          <span className="patients-page__count">
            {total} patient{total === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {(actionError || loadError) && <div className="patients-page__error">{actionError || loadError}</div>}

      {isLoading ? (
        <div className="patients-page__loading">
          <Loader size="lg" />
        </div>
      ) : loadError ? (
        <Button variant="outline" onClick={() => refetch()}>
          Try again
        </Button>
      ) : patients.length === 0 ? (
        <EmptyState
          icon={<FiUsers />}
          title={search ? 'No patients match your search' : 'No patients yet'}
          description={search ? 'Try a different name or MRN.' : 'Add your first patient to start creating studies and reports.'}
          action={
            !search ? (
              <Button icon={<FiPlus size={15} />} onClick={openCreate}>
                Add patient
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <Table columns={columns} rows={patients} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/patients/${p.id}`)} />
          <div className="patients-page__pagination">
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </div>
        </>
      )}

      <Modal isOpen={modalMode === 'create'} onClose={closeModal} title="New patient">
        {formError && <div className="patients-page__form-error">{formError}</div>}
        <PatientForm onSubmit={handleCreate} submitLabel="Create patient" />
      </Modal>

      <Modal isOpen={modalMode === 'edit'} onClose={closeModal} title={`Edit ${activePatient?.name ?? 'patient'}`}>
        {formError && <div className="patients-page__form-error">{formError}</div>}
        {activePatient && <PatientForm initial={activePatient} onSubmit={handleUpdate} submitLabel="Save changes" />}
      </Modal>
    </div>
  );
}
