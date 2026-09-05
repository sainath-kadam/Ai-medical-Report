import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { FiArrowLeft, FiCalendar, FiEdit2, FiEye, FiFileText, FiHash, FiMail, FiPhone, FiPlus, FiTrash2, FiUser } from 'react-icons/fi';
import { patientApi } from '../../api/patient.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { usePatient, usePatientStudies } from '../../hooks/queries/usePatients';
import { queryKeys } from '../../lib/queryKeys';
import { Sex, Study } from '../../types';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Modal from '../../components/common/Modal/Modal';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import Table, { TableColumn } from '../../components/ui/Table/Table';
import PatientForm, { PatientFormValues, patientFormToPayload } from '../../components/patients/PatientForm/PatientForm';
import { useAuth } from '../../hooks/useAuth';
import { useToast } from '../../components/ui/Toast/ToastProvider';
import { formatDate } from '../../utils/formatDate';
import { MODALITY_LABELS, STUDY_STATUS_META } from '../../utils/studyMeta';
import './PatientDetail.css';

const SEX_LABEL: Record<Sex, string> = {
  male: 'Male',
  female: 'Female',
  other: 'Other',
  unspecified: 'Unspecified',
};

export default function PatientDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  // RBAC (CONTRACTS.md §3): org_admin/doctor can all edit+delete patients.
  const canDelete = user?.role === 'org_admin' || user?.role === 'doctor';

  // Same cache entry the Patients list's row navigation and StudyDetail's patient
  // fallback read (queryKeys.patients.detail) -- arriving here from either place, or
  // coming back to it, often costs zero network requests.
  const { data: patient, isLoading, isError, error } = usePatient(id);
  const { data: studies = [], isLoading: studiesLoading, isError: studiesIsError, error: studiesErrorObj } = usePatientStudies(id);

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [formError, setFormError] = useState('');
  const [deleteError, setDeleteError] = useState('');

  async function handleUpdate(values: PatientFormValues) {
    if (!patient) return;
    setFormError('');
    try {
      const updated = await patientApi.update(patient.id, patientFormToPayload(values));
      queryClient.setQueryData(queryKeys.patients.detail(patient.id), updated);
      queryClient.invalidateQueries({ queryKey: queryKeys.patients.all });
      setIsEditOpen(false);
      showToast('Patient updated', 'success');
    } catch (err) {
      setFormError(apiErrorMessage(err));
    }
  }

  async function handleDelete() {
    if (!patient) return;
    if (!confirm(`Delete patient ${patient.name}? This cannot be undone.`)) return;
    try {
      await patientApi.remove(patient.id);
      queryClient.invalidateQueries({ queryKey: queryKeys.patients.all });
      showToast('Patient deleted', 'success');
      navigate('/patients');
    } catch (err) {
      setDeleteError(apiErrorMessage(err));
    }
  }

  // Study creation lives inline on the Dashboard (ChatIntake) rather than its own
  // route — `startUpload` opens it directly, `patientId` pre-selects this patient so the
  // wizard skips its own patient-picker step.
  const newStudyHref = patient ? `/dashboard?startUpload=1&patientId=${patient.id}` : '/dashboard?startUpload=1';

  const studyColumns: TableColumn<Study>[] = [
    { key: 'modality', header: 'Modality', render: (s) => MODALITY_LABELS[s.modality] },
    { key: 'bodyPart', header: 'Body part' },
    { key: 'studyDate', header: 'Study date', render: (s) => formatDate(s.studyDate) },
    {
      key: 'status',
      header: 'Status',
      render: (s) => <StatusBadge label={STUDY_STATUS_META[s.status].label} tone={STUDY_STATUS_META[s.status].tone} />,
    },
    {
      key: 'actions',
      header: '',
      width: '1%',
      render: (s) => (
        <Link to={`/studies/${s.id}`} className="patient-detail__view-link" onClick={(e) => e.stopPropagation()}>
          <FiEye size={13} /> View
        </Link>
      ),
    },
  ];

  if (isLoading) {
    return (
      <div className="patient-detail__loading">
        <Loader size="lg" />
      </div>
    );
  }

  if (isError || !patient) {
    return (
      <div className="patient-detail">
        <button type="button" className="patient-detail__back" onClick={() => navigate('/patients')}>
          <FiArrowLeft size={15} /> Back to patients
        </button>
        <EmptyState title="Couldn't load this patient" description={isError ? apiErrorMessage(error) : 'Patient not found.'} />
      </div>
    );
  }

  return (
    <div className="patient-detail">
      <button type="button" className="patient-detail__back" onClick={() => navigate('/patients')}>
        <FiArrowLeft size={15} /> Back to patients
      </button>

      <div className="patient-detail__header">
        <div>
          <h1>{patient.name}</h1>
          <p>
            MRN {patient.mrn} · Added {formatDate(patient.createdAt)}
          </p>
        </div>
        <div className="patient-detail__header-actions">
          <Button
            variant="outline"
            icon={<FiEdit2 size={15} />}
            onClick={() => {
              setFormError('');
              setIsEditOpen(true);
            }}
          >
            Edit
          </Button>
          {canDelete && (
            <Button variant="danger" icon={<FiTrash2 size={15} />} onClick={handleDelete}>
              Delete
            </Button>
          )}
        </div>
      </div>

      {deleteError && <div className="patient-detail__error">{deleteError}</div>}

      <Card className="patient-detail__info">
        <div className="patient-detail__row">
          <FiHash size={16} />
          <div>
            <span className="patient-detail__label">MRN</span>
            <span>{patient.mrn}</span>
          </div>
        </div>
        <div className="patient-detail__row">
          <FiCalendar size={16} />
          <div>
            <span className="patient-detail__label">Date of birth</span>
            <span>{patient.dateOfBirth ? formatDate(patient.dateOfBirth) : '—'}</span>
          </div>
        </div>
        <div className="patient-detail__row">
          <FiUser size={16} />
          <div>
            <span className="patient-detail__label">Sex</span>
            <span>{SEX_LABEL[patient.sex ?? 'unspecified']}</span>
          </div>
        </div>
        <div className="patient-detail__row">
          <FiPhone size={16} />
          <div>
            <span className="patient-detail__label">Contact phone</span>
            <span>{patient.contactPhone || '—'}</span>
          </div>
        </div>
        <div className="patient-detail__row">
          <FiMail size={16} />
          <div>
            <span className="patient-detail__label">Contact email</span>
            <span>{patient.contactEmail || '—'}</span>
          </div>
        </div>
      </Card>

      <div className="patient-detail__section-header">
        <h2>Studies</h2>
        <Link to={newStudyHref}>
          <Button icon={<FiPlus size={15} />} size="sm">
            New study
          </Button>
        </Link>
      </div>

      {studiesIsError && <div className="patient-detail__error">{apiErrorMessage(studiesErrorObj)}</div>}

      {studiesLoading ? (
        <div className="patient-detail__loading">
          <Loader size="lg" />
        </div>
      ) : studies.length === 0 ? (
        <EmptyState
          icon={<FiFileText />}
          title="No studies yet"
          description="Create the first imaging study for this patient."
          action={
            <Link to={newStudyHref}>
              <Button icon={<FiPlus size={15} />}>New study</Button>
            </Link>
          }
        />
      ) : (
        <Table columns={studyColumns} rows={studies} rowKey={(s) => s.id} onRowClick={(s) => navigate(`/studies/${s.id}`)} />
      )}

      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title={`Edit ${patient.name}`}>
        {formError && <div className="patient-detail__form-error">{formError}</div>}
        <PatientForm initial={patient} onSubmit={handleUpdate} submitLabel="Save changes" />
      </Modal>
    </div>
  );
}
