import { Patient } from '../types';

/** A patient's age in years: the age entered when the patient was added, or — for older
 *  patients created with a date of birth — the age derived from it. */
export function patientAge(patient?: Pick<Patient, 'age' | 'dateOfBirth'> | null): number | null {
  if (!patient) return null;
  if (patient.age !== undefined && patient.age !== null) return patient.age;
  if (!patient.dateOfBirth) return null;
  const born = new Date(patient.dateOfBirth);
  if (Number.isNaN(born.getTime())) return null;
  const today = new Date();
  let age = today.getFullYear() - born.getFullYear();
  const beforeBirthday =
    today.getMonth() < born.getMonth() || (today.getMonth() === born.getMonth() && today.getDate() < born.getDate());
  if (beforeBirthday) age -= 1;
  return age;
}

/** "58 Years", or an em dash when the age isn't known. */
export function formatPatientAge(patient?: Pick<Patient, 'age' | 'dateOfBirth'> | null): string {
  const age = patientAge(patient);
  return age === null ? '—' : `${age} Years`;
}
