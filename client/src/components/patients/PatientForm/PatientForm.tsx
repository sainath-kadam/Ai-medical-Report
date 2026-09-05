import { FormEvent, useEffect, useState } from 'react';
import Button from '../../common/Button/Button';
import { TextField } from '../../common/TextField/TextField';
import Select from '../../ui/Select/Select';
import { Patient, Sex } from '../../../types';
import { PatientPayload } from '../../../api/patient.api';
import './PatientForm.css';

export interface PatientFormValues {
  mrn: string;
  name: string;
  dateOfBirth: string;
  sex: Sex;
  contactPhone: string;
  contactEmail: string;
}

interface PatientFormProps {
  initial?: Patient;
  onSubmit: (values: PatientFormValues) => Promise<void>;
  submitLabel?: string;
}

const SEX_OPTIONS = [
  { value: 'unspecified', label: 'Unspecified' },
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
];

function defaultValues(): PatientFormValues {
  return { mrn: '', name: '', dateOfBirth: '', sex: 'unspecified', contactPhone: '', contactEmail: '' };
}

/** Converts form state (all-string, HTML-input-friendly) into the payload shape
 *  patientApi.create/update expect, dropping optional fields left blank rather than
 *  sending empty strings. */
export function patientFormToPayload(values: PatientFormValues): PatientPayload {
  return {
    mrn: values.mrn.trim() || undefined,
    name: values.name.trim(),
    dateOfBirth: values.dateOfBirth || undefined,
    sex: values.sex,
    contactPhone: values.contactPhone.trim() || undefined,
    contactEmail: values.contactEmail.trim() || undefined,
  };
}

export default function PatientForm({ initial, onSubmit, submitLabel = 'Save patient' }: PatientFormProps) {
  const [values, setValues] = useState<PatientFormValues>(defaultValues());
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (initial) {
      setValues({
        mrn: initial.mrn,
        name: initial.name,
        dateOfBirth: initial.dateOfBirth ? initial.dateOfBirth.slice(0, 10) : '',
        sex: initial.sex ?? 'unspecified',
        contactPhone: initial.contactPhone ?? '',
        contactEmail: initial.contactEmail ?? '',
      });
    }
  }, [initial]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit(values);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="patient-form">
      <div className="patient-form__grid">
        <TextField
          label="Hospital MRN (optional)"
          value={values.mrn}
          onChange={(e) => setValues((p) => ({ ...p, mrn: e.target.value }))}
          placeholder="Leave blank to assign one automatically"
          hint="Only if your hospital already has a medical record number for this patient."
        />
        <TextField
          label="Full name"
          value={values.name}
          onChange={(e) => setValues((p) => ({ ...p, name: e.target.value }))}
          placeholder="Patient's full name"
          required
        />
      </div>

      <div className="patient-form__grid">
        <TextField
          label="Date of birth"
          type="date"
          value={values.dateOfBirth}
          onChange={(e) => setValues((p) => ({ ...p, dateOfBirth: e.target.value }))}
          max={new Date().toISOString().slice(0, 10)}
        />
        <Select
          label="Sex"
          options={SEX_OPTIONS}
          value={values.sex}
          onChange={(e) => setValues((p) => ({ ...p, sex: e.target.value as Sex }))}
        />
      </div>

      <div className="patient-form__grid">
        <TextField
          label="Contact phone"
          type="tel"
          value={values.contactPhone}
          onChange={(e) => setValues((p) => ({ ...p, contactPhone: e.target.value }))}
          placeholder="Optional"
        />
        <TextField
          label="Contact email"
          type="email"
          value={values.contactEmail}
          onChange={(e) => setValues((p) => ({ ...p, contactEmail: e.target.value }))}
          placeholder="Optional"
        />
      </div>

      <Button type="submit" isLoading={isSubmitting} size="lg" fullWidth>
        {submitLabel}
      </Button>
    </form>
  );
}
