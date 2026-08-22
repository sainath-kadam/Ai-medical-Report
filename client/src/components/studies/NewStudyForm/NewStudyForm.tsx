import { FormEvent, useEffect, useState } from 'react';
import { FiUserPlus } from 'react-icons/fi';
import { patientApi } from '../../../api/patient.api';
import { studyApi } from '../../../api/study.api';
import { templateApi } from '../../../api/template.api';
import { apiErrorMessage } from '../../../api/axiosInstance';
import { Modality, Patient, ReportTemplate, Sex, StudyIntakeResult } from '../../../types';
import { MODALITY_OPTIONS } from '../../../utils/studyMeta';
import Card from '../../common/Card/Card';
import Button from '../../common/Button/Button';
import Loader from '../../common/Loader/Loader';
import { TextField, TextArea } from '../../common/TextField/TextField';
import Select from '../../ui/Select/Select';
import FileDropzone from '../../upload/FileDropzone/FileDropzone';
import { formatDate } from '../../../utils/formatDate';
import './NewStudyForm.css';

const SEX_OPTIONS = [
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
  { value: 'unspecified', label: 'Unspecified' },
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

interface NewStudyFormProps {
  initialPatientId?: string;
  onComplete: (result: StudyIntakeResult) => void;
}

/** The one "new study" form used everywhere in the app (Dashboard's inline upload flow and
 *  the Studies list's "New study" action both route here) -- collects patient + scan
 *  details + the imaging file up front and submits everything in a single
 *  `studyApi.intake` call, instead of the old separate create/upload/analyze requests. */
export default function NewStudyForm({ initialPatientId, onComplete }: NewStudyFormProps) {
  const [patientMode, setPatientMode] = useState<'existing' | 'new'>('existing');
  const [patientResults, setPatientResults] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);

  const [newMrn, setNewMrn] = useState('');
  const [newName, setNewName] = useState('');
  const [newDob, setNewDob] = useState('');
  const [newSex, setNewSex] = useState<Sex>('unspecified');
  const [newPhone, setNewPhone] = useState('');
  const [newEmail, setNewEmail] = useState('');
  // Phone/email are optional and rarely needed at intake time -- keep them out of the
  // way behind a link instead of always showing two more fields.
  const [showContactFields, setShowContactFields] = useState(false);

  const [modality, setModality] = useState<Modality>('x_ray');
  const [bodyPart, setBodyPart] = useState('');
  const [clinicalHistory, setClinicalHistory] = useState('');
  const [studyDate, setStudyDate] = useState(todayIso());
  // Defaults to today and isn't required to submit -- show it as a plain fact with a
  // "Change" link rather than an editable field everyone has to look past.
  const [isEditingDate, setIsEditingDate] = useState(false);

  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string | undefined>(undefined);
  const selectedTemplate = templates.find((t) => t.id === templateId);
  const [file, setFile] = useState<File | null>(null);
  const [runAnalysis, setRunAnalysis] = useState(true);

  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    templateApi
      .list()
      .then((items) => {
        setTemplates(items);
        setTemplateId(items.find((t) => t.isDefault)?.id ?? items[0]?.id);
      })
      .catch(() => setTemplates([]));
  }, []);

  useEffect(() => {
    if (!initialPatientId) return;
    patientApi.getById(initialPatientId).then(setSelectedPatient).catch(() => { });
  }, [initialPatientId]);

  useEffect(() => {
    if (patientMode !== 'existing') return;
    patientApi.list({ pageSize: 100 }).then((data) => setPatientResults(data.items)).catch(() => setPatientResults([]));
  }, [patientMode]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');

    if (patientMode === 'existing' && !selectedPatient) {
      setError('Select a patient for this study.');
      return;
    }
    if (patientMode === 'new' && (!newMrn.trim() || !newName.trim() || !newDob)) {
      setError("The new patient's MRN, name, and date of birth are required.");
      return;
    }
    if (!bodyPart.trim()) {
      setError('Body part is required.');
      return;
    }
    if (!file) {
      setError('Attach the imaging file (image, video, or DICOM) for this study.');
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await studyApi.intake(
        {
          patientId: patientMode === 'existing' ? selectedPatient?.id : undefined,
          newPatient:
            patientMode === 'new'
              ? {
                mrn: newMrn.trim(),
                name: newName.trim(),
                dateOfBirth: newDob,
                sex: newSex,
                contactPhone: newPhone.trim() || undefined,
                contactEmail: newEmail.trim() || undefined,
              }
              : undefined,
          modality,
          bodyPart: bodyPart.trim(),
          clinicalHistory: clinicalHistory.trim() || undefined,
          studyDate,
          templateId,
          runAnalysis,
        },
        file
      );
      onComplete(result);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="study-intake-form" onSubmit={handleSubmit}>
      <div className="study-intake-form__grid">
        <div className="study-intake-form__main">
          <Card>
            <div className="study-intake-form__section-header">
              <h3>Patient</h3>
              {!selectedPatient && (
                <div className="study-intake-form__mode-toggle">
                  <button
                    type="button"
                    className={patientMode === 'existing' ? 'is-active' : ''}
                    onClick={() => setPatientMode('existing')}
                  >
                    Existing patient
                  </button>
                  <button
                    type="button"
                    className={patientMode === 'new' ? 'is-active' : ''}
                    onClick={() => setPatientMode('new')}
                  >
                    <FiUserPlus size={13} /> New patient
                  </button>
                </div>
              )}
            </div>

            {patientMode === 'existing' ? (
              <Select
                label="Patient"
                value={selectedPatient?.id ?? ''}
                onChange={(e) => setSelectedPatient(patientResults.find((patient) => patient.id === e.target.value) ?? null)}
                placeholder="Select a patient"
                options={patientResults.map((patient) => ({ value: patient.id, label: `${patient.name} · MRN ${patient.mrn}` }))}
              />
            ) : (
              <div className="study-intake-form__new-patient">
                <div className="study-intake-form__row">
                  <TextField label="Full name" value={newName} onChange={(e) => setNewName(e.target.value)} required />
                  <TextField label="MRN" value={newMrn} onChange={(e) => setNewMrn(e.target.value)} required />
                </div>
                <div className="study-intake-form__row">
                  <TextField
                    label="Date of birth"
                    type="date"
                    value={newDob}
                    onChange={(e) => setNewDob(e.target.value)}
                    required
                  />
                  <Select label="Sex" value={newSex} onChange={(e) => setNewSex(e.target.value as Sex)} options={SEX_OPTIONS} />
                </div>
                {showContactFields ? (
                  <div className="study-intake-form__row">
                    <TextField label="Phone (optional)" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} />
                    <TextField label="Email (optional)" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
                  </div>
                ) : (
                  <button type="button" className="study-intake-form__link-btn" onClick={() => setShowContactFields(true)}>
                    + Add phone or email (optional)
                  </button>
                )}
              </div>
            )}
          </Card>

          <Card>
            <h3 className="study-intake-form__section-title">Scan details</h3>
            <div className="study-intake-form__row">
              <Select
                label="Modality"
                value={modality}
                onChange={(e) => setModality(e.target.value as Modality)}
                options={MODALITY_OPTIONS}
              />
              <TextField
                label="Body part"
                placeholder="e.g. Chest, Left knee"
                value={bodyPart}
                onChange={(e) => setBodyPart(e.target.value)}
                required
              />
            </div>
            {isEditingDate ? (
              <TextField
                label="Study date"
                type="date"
                value={studyDate}
                onChange={(e) => setStudyDate(e.target.value)}
                required
                autoFocus
              />
            ) : (
              <p className="study-intake-form__inline-fact">
                Study date: <strong>{formatDate(studyDate)}</strong>
                <button type="button" className="study-intake-form__link-btn" onClick={() => setIsEditingDate(true)}>
                  Change
                </button>
              </p>
            )}
            <TextArea
              label="Clinical history (optional)"
              placeholder="Relevant history, symptoms, or reason for the study…"
              value={clinicalHistory}
              onChange={(e) => setClinicalHistory(e.target.value)}
              rows={3}
            />
          </Card>

          <Card>
            <h3 className="study-intake-form__section-title">Imaging file</h3>
            <FileDropzone file={file} onSelect={setFile} />
          </Card>

          <Card>
            <label className="study-intake-form__toggle">
              <input type="checkbox" checked={runAnalysis} onChange={(e) => setRunAnalysis(e.target.checked)} />
              <span>Generate an AI draft report immediately</span>
            </label>
            {!runAnalysis && (
              <p className="study-intake-form__hint">Saves the study only — you can run AI analysis for it later.</p>
            )}

            {error && <p className="study-intake-form__error">{error}</p>}

            <Button type="submit" isLoading={isSubmitting} fullWidth>
              {runAnalysis ? 'Generate report' : 'Create study'}
            </Button>
          </Card>
        </div>

        <aside className="study-intake-form__sidebar">
          <Card>
            <h3 className="study-intake-form__section-title">Report format</h3>
            {templates.length === 0 ? (
              <p className="study-intake-form__hint">The organization default will be used.</p>
            ) : (
              <Select
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                options={templates.map((t) => ({ value: t.id, label: t.isDefault ? `${t.name} (default)` : t.name }))}
              />
            )}
          </Card>
        </aside>
      </div>
    </form>
  );
}
